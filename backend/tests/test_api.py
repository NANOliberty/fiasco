"""REST / WebSocket 레이어 테스트."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rooms import registry


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make_room(client) -> str:
    return client.post("/api/rooms").json()["roomCode"]


def join(client, code: str, name: str) -> dict:
    response = client.post(f"/api/rooms/{code}/join", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def ws_url(code: str, creds: dict) -> str:
    return f"/ws/{code}?playerId={creds['playerId']}&token={creds['token']}"


def read_until(socket, predicate, limit: int = 30) -> dict:
    """조건에 맞는 메시지가 나올 때까지 읽는다.

    접속할 때마다 전원에게 상태가 브로드캐스트되므로 소켓에는 이미 여러 개의
    상태 메시지가 쌓여 있다. 클라이언트도 마지막 상태만 쓰면 되지만,
    테스트에서는 원하는 상태가 올 때까지 흘려보내야 한다.
    """
    last = None
    for _ in range(limit):
        message = json.loads(socket.receive_text())
        if message["type"] == "fatal":
            raise AssertionError(message["message"])
        if predicate(message):
            return message
        last = message
    raise AssertionError(f"조건에 맞는 메시지를 받지 못했습니다. 마지막: {last}")


def read_state(socket) -> dict:
    return read_until(socket, lambda m: m["type"] == "state")["state"]


def read_state_where(socket, predicate) -> dict:
    return read_until(socket, lambda m: m["type"] == "state" and predicate(m["state"]))["state"]


def act(socket, action: str, payload: dict | None = None) -> None:
    socket.send_text(json.dumps({"type": "action", "action": action, "payload": payload or {}}))


# ---------------------------------------------------------------------------


def test_health_and_playsets(client):
    assert client.get("/api/health").json()["ok"] is True
    listing = client.get("/api/playsets").json()["playsets"]
    assert {p["id"] for p in listing} >= {
        "pretty_southern_town",
        "boomtown",
        "suburbia",
        "the_ice",
    }
    assert all(p["hasQuickSetup"] for p in listing)


def test_playset_detail_and_404(client):
    detail = client.get("/api/playsets/boomtown").json()
    assert len(detail["lists"]["relationship"]) == 6
    assert client.get("/api/playsets/nope").status_code == 404


def test_reference_tables(client):
    data = client.get("/api/reference").json()
    assert len(data["twistTable"]) == 6
    assert all(len(c["elements"]) == 6 for c in data["twistTable"])
    assert data["rules"]


def test_room_lifecycle(client):
    code = make_room(client)
    info = client.get(f"/api/rooms/{code}").json()
    assert info["playerCount"] == 0 and info["joinable"]

    creds = join(client, code, "나노")
    assert creds["playerId"] and creds["token"]
    assert client.get(f"/api/rooms/{code}").json()["playerCount"] == 1


def test_unknown_room_is_404(client):
    assert client.get("/api/rooms/ZZZZZZ").status_code == 404
    assert client.post("/api/rooms/ZZZZZZ/join", json={"name": "x"}).status_code == 404


def test_join_rejects_sixth_player(client):
    code = make_room(client)
    for i in range(5):
        join(client, code, f"P{i}")
    response = client.post(f"/api/rooms/{code}/join", json={"name": "여섯"})
    assert response.status_code == 409
    assert "정원" in response.json()["detail"]


def test_websocket_rejects_bad_token(client):
    code = make_room(client)
    creds = join(client, code, "나노")
    with client.websocket_connect(f"/ws/{code}?playerId={creds['playerId']}&token=틀림") as socket:
        message = json.loads(socket.receive_text())
        assert message["type"] == "fatal"


def test_state_broadcasts_to_everyone(client):
    code = make_room(client)
    a = join(client, code, "A")
    b = join(client, code, "B")

    with client.websocket_connect(ws_url(code, a)) as sa, client.websocket_connect(ws_url(code, b)) as sb:
        read_state(sa)
        read_state(sb)
        act(sa, "set_playset", {"playsetId": "the_ice"})
        # 방장(A)의 변경이 B 화면에도 반영된다
        assert read_state_where(sb, lambda s: s["playsetId"] == "the_ice")


def test_error_goes_only_to_the_sender(client):
    code = make_room(client)
    a = join(client, code, "A")
    b = join(client, code, "B")
    with client.websocket_connect(ws_url(code, a)) as sa, client.websocket_connect(ws_url(code, b)) as sb:
        read_state(sa)
        read_state(sb)
        act(sb, "set_playset", {"playsetId": "the_ice"})  # B는 방장이 아니다
        message = read_until(sb, lambda m: m["type"] == "error")
        assert "방장" in message["message"]
        # 상태는 바뀌지 않았고, A에게는 오류가 가지 않는다
        act(sa, "set_playset", {"playsetId": "boomtown"})
        assert read_state_where(sa, lambda s: s["playsetId"] == "boomtown")


def test_full_setup_over_the_socket(client):
    code = make_room(client)
    creds = [join(client, code, f"P{i}") for i in range(3)]
    sockets = []
    try:
        for c in creds:
            socket = client.websocket_connect(ws_url(code, c)).__enter__()
            sockets.append(socket)
        for socket in sockets:
            read_state(socket)

        host = sockets[0]
        act(host, "set_playset", {"playsetId": "suburbia"})
        act(host, "start_game")
        act(host, "quick_setup")
        for i, socket in enumerate(sockets):
            act(socket, "set_character_name", {"name": f"캐릭터{i}"})
        act(host, "finish_setup")

        state = read_state_where(host, lambda s: s["phase"] == "act1")
        assert state["scene"]["number"] == 1
        assert len(state["central"]) == 12
    finally:
        for socket in sockets:
            socket.__exit__(None, None, None)


def test_disconnect_frees_the_seat_in_lobby(client):
    code = make_room(client)
    creds = join(client, code, "잠깐")
    with client.websocket_connect(ws_url(code, creds)):
        pass
    assert client.get(f"/api/rooms/{code}").json()["playerCount"] == 0


def test_host_moves_on_when_the_host_disconnects_mid_game(client):
    code = make_room(client)
    creds = [join(client, code, f"P{i}") for i in range(3)]
    sockets = [client.websocket_connect(ws_url(code, c)).__enter__() for c in creds]
    try:
        host = sockets[0]
        act(host, "set_playset", {"playsetId": "boomtown"})
        act(host, "start_game")
        state = read_state_where(host, lambda s: s["phase"] == "setup")
        assert state["hostId"] == creds[0]["playerId"]
    finally:
        sockets[0].__exit__(None, None, None)  # 방장이 창을 닫는다

    try:
        # 자리는 남지만 방장은 남은 사람에게 넘어간다
        state = read_state_where(sockets[1], lambda s: s["hostId"] != creds[0]["playerId"])
        assert state["hostId"] in {creds[1]["playerId"], creds[2]["playerId"]}
        assert len(state["players"]) == 3
        gone = next(p for p in state["players"] if p["id"] == creds[0]["playerId"])
        assert gone["connected"] is False
    finally:
        for socket in sockets[1:]:
            socket.__exit__(None, None, None)


def test_kicked_player_cannot_reuse_stale_credentials(client):
    """로비에서 나가면 자리가 사라지고, 옛 토큰으로는 다시 들어올 수 없다."""
    code = make_room(client)
    creds = join(client, code, "잠깐")
    with client.websocket_connect(ws_url(code, creds)) as socket:
        read_state(socket)
    with client.websocket_connect(ws_url(code, creds)) as socket:
        message = json.loads(socket.receive_text())
        assert message["type"] == "fatal"


def test_custom_playset_upload(client):
    def table(prefix: str) -> dict:
        return {f"{prefix}분류{c}": [f"{prefix}요소{c}-{e}" for e in range(1, 7)] for c in range(1, 7)}

    body = {
        "playset": {
            "name": "우리 동네",
            "relationships": table("관"),
            "desires": table("욕"),
            "objects": table("물"),
            "places": table("장"),
        }
    }
    created = client.post("/api/playsets", json=body).json()
    assert created["custom"] is True
    assert client.get(f"/api/playsets/{created['id']}").status_code == 200
    assert any(p["id"] == created["id"] for p in client.get("/api/playsets").json()["playsets"])


def test_custom_playset_validation(client):
    bad = {"playset": {"name": "부족한 세트", "relationships": {"하나": ["a"] * 6}}}
    response = client.post("/api/playsets", json=bad)
    assert response.status_code == 400
    assert "빠졌" in response.json()["detail"]


def test_room_sweeper_keeps_active_rooms():
    code = registry.create().code
    assert registry.sweep() == 0
    assert registry.exists(code)
