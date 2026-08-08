"""FastAPI 서버 — REST 로 방을 만들고, WebSocket 으로 상태를 동기화한다.

상태가 작아서(플레이어 5명 × 주사위 20개 남짓) 변경이 있을 때마다 전체 상태를
브로드캐스트한다. 델타 계산을 할 이유가 없다.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import game, playsets
from .rooms import Room, RoomError, registry
from .tables import RULES_SUMMARY, TWIST_TABLE

log = logging.getLogger("fiasco")

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.start_sweeper()
    yield
    await registry.stop_sweeper()


app = FastAPI(title="피아스코 온라인", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 방 코드로만 접근하는 공개 보드라 별도 오리진 제한이 없다
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


class JoinRequest(BaseModel):
    name: str = Field(default="", max_length=20)


class CustomPlaysetRequest(BaseModel):
    playset: dict[str, Any]


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "rooms": registry.count}


@app.get("/api/playsets")
async def list_playsets() -> dict[str, Any]:
    return {"playsets": playsets.summaries()}


@app.get("/api/playsets/{playset_id}")
async def get_playset(playset_id: str) -> dict[str, Any]:
    try:
        return playsets.get(playset_id)
    except playsets.PlaysetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/playsets")
async def create_playset(body: CustomPlaysetRequest) -> dict[str, Any]:
    try:
        return playsets.register_custom(body.playset)
    except playsets.PlaysetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/reference")
async def reference() -> dict[str, Any]:
    """비틀기 표와 규칙 요약 — 게임 중 참고용."""
    return {"twistTable": TWIST_TABLE, "rules": RULES_SUMMARY}


@app.post("/api/rooms")
async def create_room() -> dict[str, Any]:
    room = registry.create()
    return {"roomCode": room.code}


@app.get("/api/rooms/{code}")
async def room_info(code: str) -> dict[str, Any]:
    try:
        room = registry.get(code)
    except RoomError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "roomCode": room.code,
        "phase": room.state["phase"],
        "playerCount": len(room.state["players"]),
        "maxPlayers": game.MAX_PLAYERS,
        "playsetId": room.state["playsetId"],
        "joinable": room.state["phase"] == "lobby" and len(room.state["players"]) < game.MAX_PLAYERS,
    }


@app.post("/api/rooms/{code}/join")
async def join_room(code: str, body: JoinRequest) -> dict[str, Any]:
    try:
        room = registry.get(code)
    except RoomError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    async with room.lock:
        try:
            credentials = room.join(body.name)
        except game.GameError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    await broadcast(room)
    return credentials


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


async def _send(websocket: WebSocket, message: dict[str, Any]) -> bool:
    try:
        await websocket.send_text(json.dumps(message, ensure_ascii=False))
        return True
    except Exception:  # 이미 끊긴 소켓 — 다음 sweep 에서 정리된다
        return False


async def broadcast(room: Room) -> None:
    snapshot = room.snapshot()
    dead: list[tuple[str, WebSocket]] = []
    for player_id, sockets in list(room.connections.items()):
        for socket in list(sockets):
            ok = await _send(socket, {"type": "state", "you": player_id, "state": snapshot})
            if not ok:
                dead.append((player_id, socket))
    for player_id, socket in dead:
        room.detach(player_id, socket)


@app.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str, playerId: str = "", token: str = "") -> None:
    await websocket.accept()
    try:
        room = registry.get(code)
        player = room.authenticate(playerId, token)
    except RoomError as exc:
        await _send(websocket, {"type": "fatal", "message": str(exc)})
        await websocket.close()
        return

    player_id = player["id"]
    room.attach(player_id, websocket)
    await _send(websocket, {"type": "state", "you": player_id, "state": room.snapshot()})
    await broadcast(room)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {"type": "error", "message": "잘못된 요청 형식입니다."})
                continue

            kind = message.get("type")
            if kind == "ping":
                await _send(websocket, {"type": "pong"})
                continue
            if kind != "action":
                await _send(websocket, {"type": "error", "message": "알 수 없는 메시지입니다."})
                continue

            async with room.lock:
                try:
                    game.apply_action(room.state, player_id, message.get("action", ""), message.get("payload"))
                    room.touch()
                    ok = True
                except game.GameError as exc:
                    await _send(websocket, {"type": "error", "message": str(exc)})
                    ok = False
                except Exception:  # 예상 못 한 오류로 방 전체가 죽지 않게
                    log.exception("action failed: %s", message.get("action"))
                    await _send(websocket, {"type": "error", "message": "처리 중 문제가 생겼습니다."})
                    ok = False
            if ok:
                await broadcast(room)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("websocket loop failed")
    finally:
        room.detach(player_id, websocket)
        async with room.lock:
            # 로비에서 나간 사람은 자리를 비워 준다. 게임 중이라면 자리는 남겨
            # 두고(토큰으로 돌아올 수 있다) 방장만 남은 사람에게 넘긴다.
            if room.state["phase"] == "lobby":
                game.remove_player(room.state, player_id)
            game.transfer_host_if_gone(room.state)
        await broadcast(room)


# ---------------------------------------------------------------------------
# 정적 파일 (빌드된 프론트를 같은 서버에서 서빙)
# ---------------------------------------------------------------------------

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
