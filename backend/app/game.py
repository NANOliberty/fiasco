"""피아스코 게임 상태 기계.

앱은 승패를 판정하지 않는다. 여기서 하는 일은 딱 네 가지다.

* 지금 누구 차례이고 어느 단계인지 추적한다.
* 주사위가 중앙에 몇 개, 누구 앞에 몇 개 있는지 센다.
* 막의 시작과 끝을 자동으로 감지한다.
* 비틀기와 후기의 합산을 대신 해 준다.

장면의 내용, 설정/해결 선택, 결과가 좋은지 나쁜지는 전부 사람이 정한다.
"""

from __future__ import annotations

import random
import time
import uuid
from typing import Any

from . import playsets
from .tables import lookup_aftermath, twist_text

MIN_PLAYERS = 3
MAX_PLAYERS = 5

PHASES = ("lobby", "setup", "act1", "twist", "act2", "aftermath", "finished")

DEFAULT_OPTIONS: dict[str, Any] = {
    # 인당 주사위 수. 기본 4개(흑2/백2). 줄이면 짧게, 늘리면 길게 논다.
    "dicePerPlayer": 4,
    # 흑백 불균형: 검은 주사위가 차지하는 비율. 0.5 가 균형.
    "blackRatio": 0.5,
    # 준비 마지막 주사위의 눈을 임의로 정할 수 있게 한다.
    "freeLastSetupDie": True,
    # 액셀 밟기: 2막을 인당 1장면으로 줄이고 남은 주사위는 후기용으로 나눈다.
    "accelerator": False,
    # 좋은 주사위/나쁜 주사위: 몽타주에서 흰색은 긍정, 검은색은 부정으로 선언.
    "goodBadDice": False,
}


class GameError(Exception):
    """규칙에 어긋나는 행동. 클라이언트에 그대로 보여 준다."""


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# 주사위
# ---------------------------------------------------------------------------


def _make_die(color: str) -> dict[str, Any]:
    return {"id": _uid(), "color": color, "value": random.randint(1, 6)}


def roll(dice: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for die in dice:
        die["value"] = random.randint(1, 6)
    return dice


def tally(dice: list[dict[str, Any]]) -> dict[str, Any]:
    """흑합/백합과 그 차이. 동점이거나 주사위가 없으면 색은 없다."""
    black = sum(d["value"] for d in dice if d["color"] == "black")
    white = sum(d["value"] for d in dice if d["color"] == "white")
    if black == white:
        color = None
    else:
        color = "black" if black > white else "white"
    return {"black": black, "white": white, "value": abs(black - white), "color": color}


# ---------------------------------------------------------------------------
# 방 생성 / 참가
# ---------------------------------------------------------------------------


def new_state(room_code: str) -> dict[str, Any]:
    return {
        "roomCode": room_code,
        "phase": "lobby",
        "hostId": None,
        "options": dict(DEFAULT_OPTIONS),
        "playsetId": None,
        "players": [],
        "startingSeat": 0,
        "turnSeat": 0,
        "central": [],
        "totalDice": 0,
        "act": 0,
        "setup": None,
        "scene": None,
        "twist": None,
        "twistDetails": [],
        "aftermath": None,
        "log": [],
        "createdAt": _now(),
    }


def _log(state: dict[str, Any], text: str, kind: str = "info", player_id: str | None = None) -> None:
    state["log"].append(
        {
            "id": _uid(),
            "ts": _now(),
            "kind": kind,
            "text": text,
            "playerId": player_id,
            "phase": state["phase"],
        }
    )
    # 로그가 무한정 자라지 않게 최근 500 개만 남긴다.
    if len(state["log"]) > 500:
        del state["log"][:-500]


def player_by_id(state: dict[str, Any], player_id: str | None) -> dict[str, Any] | None:
    for p in state["players"]:
        if p["id"] == player_id:
            return p
    return None


def _require_player(state: dict[str, Any], player_id: str) -> dict[str, Any]:
    p = player_by_id(state, player_id)
    if p is None:
        raise GameError("이 방에 참가한 플레이어가 아닙니다.")
    return p


def player_by_seat(state: dict[str, Any], seat: int) -> dict[str, Any]:
    for p in state["players"]:
        if p["seat"] == seat:
            return p
    raise GameError(f"{seat}번 자리에 플레이어가 없습니다.")


def display_name(state: dict[str, Any], player_id: str | None) -> str:
    p = player_by_id(state, player_id)
    if p is None:
        return "???"
    return p["characterName"] or p["name"]


def turn_order(state: dict[str, Any]) -> list[int]:
    """시작 플레이어부터 시계방향 자리 번호."""
    n = len(state["players"])
    start = state["startingSeat"]
    return [(start + k) % n for k in range(n)]


def add_player(state: dict[str, Any], name: str) -> dict[str, Any]:
    if state["phase"] != "lobby":
        raise GameError("이미 시작한 게임에는 새로 참가할 수 없습니다.")
    if len(state["players"]) >= MAX_PLAYERS:
        raise GameError(f"정원({MAX_PLAYERS}명)이 찼습니다.")
    name = (name or "").strip()[:20] or f"플레이어{len(state['players']) + 1}"
    player = {
        "id": _uid(),
        "token": uuid.uuid4().hex,
        "name": name,
        "characterName": "",
        "seat": len(state["players"]),
        "connected": True,
        "dice": [],
    }
    state["players"].append(player)
    if state["hostId"] is None:
        state["hostId"] = player["id"]
    _log(state, f"{name} 님이 입장했습니다.", "join", player["id"])
    return player


def remove_player(state: dict[str, Any], player_id: str) -> None:
    """로비에서만 실제로 제거한다. 게임 중 이탈은 connected=False 로만 표시."""
    if state["phase"] != "lobby":
        return
    player = player_by_id(state, player_id)
    if player is None:
        return
    state["players"].remove(player)
    for i, p in enumerate(state["players"]):
        p["seat"] = i
    if state["hostId"] == player_id:
        state["hostId"] = state["players"][0]["id"] if state["players"] else None
    state["startingSeat"] = min(state["startingSeat"], max(len(state["players"]) - 1, 0))
    _log(state, f"{player['name']} 님이 나갔습니다.", "leave")


def _require_host(state: dict[str, Any], player_id: str) -> None:
    if state["hostId"] != player_id:
        raise GameError("방장만 할 수 있습니다.")


def _require_phase(state: dict[str, Any], *phases: str) -> None:
    if state["phase"] not in phases:
        raise GameError(f"지금 단계({state['phase']})에서는 할 수 없습니다.")


# ---------------------------------------------------------------------------
# 게임 시작 / 준비 단계
# ---------------------------------------------------------------------------


def _build_pool(state: dict[str, Any]) -> list[dict[str, Any]]:
    n = len(state["players"])
    per = int(state["options"]["dicePerPlayer"])
    total = n * per
    black = max(1, min(total - 1, round(total * float(state["options"]["blackRatio"]))))
    white = total - black
    pool = [_make_die("black") for _ in range(black)] + [_make_die("white") for _ in range(white)]
    random.shuffle(pool)
    return pool


def start_game(state: dict[str, Any], player_id: str) -> None:
    _require_host(state, player_id)
    _require_phase(state, "lobby")
    n = len(state["players"])
    if not (MIN_PLAYERS <= n <= MAX_PLAYERS):
        raise GameError(f"{MIN_PLAYERS}~{MAX_PLAYERS}명이어야 시작할 수 있습니다. (현재 {n}명)")
    if not state["playsetId"]:
        raise GameError("플레이세트를 먼저 선택하세요.")

    state["central"] = _build_pool(state)
    state["totalDice"] = len(state["central"])
    state["phase"] = "setup"
    state["turnSeat"] = state["startingSeat"]
    state["setup"] = {"slots": [], "history": []}
    playset = playsets.get(state["playsetId"])
    _log(
        state,
        f"준비 시작 — 플레이세트 '{playset['name']}', 주사위 {state['totalDice']}개를 중앙에 굴렸습니다.",
        "phase",
    )
    _log(state, f"{display_name(state, player_by_seat(state, state['turnSeat'])['id'])} 님부터 시작합니다.", "turn")


def pairs(state: dict[str, Any]) -> list[dict[str, Any]]:
    """인접한 두 자리로 이루어진 관계 자리. 인원수만큼 있고 원형으로 이어진다."""
    n = len(state["players"])
    out = []
    for i in range(n):
        a = player_by_seat(state, i)
        b = player_by_seat(state, (i + 1) % n)
        out.append({"index": i, "seatA": i, "seatB": (i + 1) % n, "playerA": a["id"], "playerB": b["id"]})
    return out


def _slot_by_id(state: dict[str, Any], slot_id: str) -> dict[str, Any]:
    for s in state["setup"]["slots"]:
        if s["id"] == slot_id:
            return s
    raise GameError("그런 카드가 없습니다.")


def _setup_counts(state: dict[str, Any]) -> dict[str, Any]:
    n = len(state["players"])
    slots = state["setup"]["slots"]
    rel_slots = [s for s in slots if s["kind"] == "relationship"]
    detail_slots = [s for s in slots if s["kind"] == "detail"]
    filled_pairs = {s["pairIndex"] for s in rel_slots}
    rels_with_detail = {s["relationshipSlotId"] for s in detail_slots}
    return {
        "pairsMissing": n - len(filled_pairs),
        "relOpen": sum(1 for s in rel_slots if s["element"] is None),
        "relNeedingDetail": sum(1 for s in rel_slots if s["id"] not in rels_with_detail),
        "detailOpen": sum(1 for s in detail_slots if s["element"] is None),
        "detailTypes": {s["listType"] for s in detail_slots},
    }


def setup_dice_required(state: dict[str, Any]) -> int:
    """준비를 규칙대로 끝내려면 앞으로 최소 몇 개의 주사위가 더 필요한가."""
    c = _setup_counts(state)
    return (
        2 * c["pairsMissing"]  # 아직 없는 관계: 분류 + 요소
        + c["relOpen"]  # 분류만 정해진 관계: 요소
        + 2 * (c["pairsMissing"] + c["relNeedingDetail"])  # 세부사항이 없는 관계마다: 분류 + 요소
        + c["detailOpen"]  # 분류만 정해진 세부사항: 요소
    )


def _feasibility_errors(state: dict[str, Any]) -> list[str]:
    """이 상태에서 준비를 규칙대로 마칠 수 있는지 확인한다."""
    errors = []
    remaining = len(state["central"])
    required = setup_dice_required(state)
    if remaining < required:
        errors.append(
            f"남은 주사위 {remaining}개로는 부족합니다. 관계와 세부사항을 채우려면 {required}개가 필요합니다."
        )
    c = _setup_counts(state)
    missing_types = [t for t in playsets.DETAIL_TYPES if t not in c["detailTypes"]]
    room_for_more = c["pairsMissing"] + c["relNeedingDetail"]
    if len(missing_types) > room_for_more:
        labels = ", ".join(playsets.LIST_LABELS[t] for t in missing_types)
        errors.append(f"{labels} 유형을 넣을 자리가 없어집니다. 세부사항 유형을 섞어 주세요.")
    return errors


def _take_die(state: dict[str, Any], die_id: str) -> dict[str, Any]:
    for i, die in enumerate(state["central"]):
        if die["id"] == die_id:
            return state["central"].pop(i)
    raise GameError("중앙에 그런 주사위가 없습니다.")


def _setup_die_value(state: dict[str, Any], die: dict[str, Any], override: int | None) -> int:
    """마지막 한 개(옵션 켜져 있을 때)만 눈을 임의로 정할 수 있다."""
    if override is None:
        return die["value"]
    if not state["options"]["freeLastSetupDie"]:
        raise GameError("'마지막 주사위 자유화' 옵션이 꺼져 있습니다.")
    if state["central"]:
        raise GameError("마지막 한 개의 주사위만 눈을 임의로 정할 수 있습니다.")
    if not (1 <= int(override) <= 6):
        raise GameError("주사위 눈은 1~6이어야 합니다.")
    die["value"] = int(override)
    return die["value"]


def _require_setup_turn(state: dict[str, Any], player_id: str) -> dict[str, Any]:
    _require_phase(state, "setup")
    player = _require_player(state, player_id)
    if player["seat"] != state["turnSeat"]:
        raise GameError("아직 차례가 아닙니다.")
    return player


def _advance_setup_turn(state: dict[str, Any]) -> None:
    n = len(state["players"])
    state["turnSeat"] = (state["turnSeat"] + 1) % n


def setup_claim_category(
    state: dict[str, Any],
    player_id: str,
    die_id: str,
    list_type: str,
    pair_index: int | None = None,
    relationship_slot_id: str | None = None,
    value_override: int | None = None,
) -> None:
    """주사위 하나를 써서 분류를 차지한다. 주사위 눈이 곧 분류 번호다."""
    player = _require_setup_turn(state, player_id)
    if list_type not in playsets.LIST_KEYS:
        raise GameError(f"알 수 없는 목록입니다: {list_type}")
    playset = playsets.get(state["playsetId"])

    die = _take_die(state, die_id)
    prev_value = die["value"]
    prev_seat = state["turnSeat"]
    try:
        category = _setup_die_value(state, die, value_override)
        if list_type == "relationship":
            if pair_index is None:
                raise GameError("어느 두 사람 사이의 관계인지 정해야 합니다.")
            pair_index = int(pair_index)
            if not (0 <= pair_index < len(state["players"])):
                raise GameError("그런 관계 자리가 없습니다.")
            if any(
                s["kind"] == "relationship" and s["pairIndex"] == pair_index
                for s in state["setup"]["slots"]
            ):
                raise GameError("이미 관계가 정해진 자리입니다.")
            parent = None
        else:
            if not relationship_slot_id:
                raise GameError("세부사항은 관계 하나에 붙어야 합니다.")
            parent = _slot_by_id(state, relationship_slot_id)
            if parent["kind"] != "relationship":
                raise GameError("세부사항은 관계 카드에만 붙일 수 있습니다.")

        slot = {
            "id": _uid(),
            "kind": "relationship" if list_type == "relationship" else "detail",
            "listType": list_type,
            "pairIndex": pair_index if list_type == "relationship" else None,
            "relationshipSlotId": parent["id"] if parent else None,
            "category": category,
            "categoryName": playsets.category_name(playset, list_type, category),
            "element": None,
            "text": None,
            "claimedBy": player_id,
            "resolvedBy": None,
            "dice": [dict(die)],
        }
        state["setup"]["slots"].append(slot)

        errors = _feasibility_errors(state)
        if errors:
            state["setup"]["slots"].remove(slot)
            raise GameError(errors[0])
    except GameError:
        die["value"] = prev_value
        state["central"].append(die)
        raise

    state["setup"]["history"].append({"type": "claim", "slotId": slot["id"], "die": dict(die), "turnSeat": prev_seat})
    label = playsets.LIST_LABELS[list_type]
    _log(
        state,
        f"{display_name(state, player_id)} 님이 {die['value']}({'검' if die['color'] == 'black' else '흰'})을 써서 "
        f"[{label}] {slot['categoryName']} 분류를 차지했습니다.",
        "setup",
        player_id,
    )
    _advance_setup_turn(state)


def setup_assign_element(
    state: dict[str, Any],
    player_id: str,
    die_id: str,
    slot_id: str,
    value_override: int | None = None,
) -> None:
    """이미 차지한 분류 안에서 구체적인 요소를 정한다. 주사위 눈이 곧 요소 번호다."""
    _require_setup_turn(state, player_id)
    slot = _slot_by_id(state, slot_id)
    if slot["element"] is not None:
        raise GameError("이미 요소가 정해진 카드입니다.")
    playset = playsets.get(state["playsetId"])

    die = _take_die(state, die_id)
    prev_value = die["value"]
    prev_seat = state["turnSeat"]
    try:
        element = _setup_die_value(state, die, value_override)
        _, text = playsets.element_text(playset, slot["listType"], slot["category"], element)
        slot["element"] = element
        slot["text"] = text
        slot["resolvedBy"] = player_id
        slot["dice"].append(dict(die))

        errors = _feasibility_errors(state)
        if errors:
            slot["element"] = None
            slot["text"] = None
            slot["resolvedBy"] = None
            slot["dice"].pop()
            raise GameError(errors[0])
    except GameError:
        die["value"] = prev_value
        state["central"].append(die)
        raise

    state["setup"]["history"].append({"type": "assign", "slotId": slot_id, "die": dict(die), "turnSeat": prev_seat})
    label = playsets.LIST_LABELS[slot["listType"]]
    _log(
        state,
        f"{display_name(state, player_id)} 님이 {die['value']}을 써서 [{label}] "
        f"{slot['categoryName']} → {text} 로 정했습니다.",
        "setup",
        player_id,
    )
    _advance_setup_turn(state)


def setup_undo(state: dict[str, Any], player_id: str) -> None:
    _require_host(state, player_id)
    _require_phase(state, "setup")
    history = state["setup"]["history"]
    if not history:
        raise GameError("되돌릴 것이 없습니다.")
    entry = history.pop()
    slot = _slot_by_id(state, entry["slotId"])
    if entry["type"] == "claim":
        state["setup"]["slots"].remove(slot)
    else:
        slot["element"] = None
        slot["text"] = None
        slot["resolvedBy"] = None
        if slot["dice"]:
            slot["dice"].pop()
    state["central"].append(entry["die"])
    state["turnSeat"] = entry["turnSeat"]
    _log(state, "방장이 직전 준비 행동을 되돌렸습니다.", "setup", player_id)


def setup_validation(state: dict[str, Any]) -> dict[str, Any]:
    """준비를 마칠 수 있는지, 권장 사항은 지켜졌는지."""
    if state["phase"] != "setup":
        return {"errors": [], "warnings": [], "canFinish": False}
    n = len(state["players"])
    slots = state["setup"]["slots"]
    rel_slots = [s for s in slots if s["kind"] == "relationship"]
    detail_slots = [s for s in slots if s["kind"] == "detail"]

    errors: list[str] = []
    if state["central"]:
        errors.append(f"중앙에 주사위가 {len(state['central'])}개 남았습니다. 전부 써야 합니다.")

    filled = {s["pairIndex"] for s in rel_slots if s["element"] is not None}
    if len(filled) < n:
        errors.append(f"관계가 아직 다 정해지지 않았습니다. ({len(filled)}/{n})")

    resolved_details = [s for s in detail_slots if s["element"] is not None]
    with_detail = {s["relationshipSlotId"] for s in resolved_details}
    lacking = [s for s in rel_slots if s["id"] not in with_detail]
    if lacking:
        errors.append(f"세부사항이 없는 관계가 {len(lacking)}개 있습니다.")

    present = {s["listType"] for s in resolved_details}
    missing = [playsets.LIST_LABELS[t] for t in playsets.DETAIL_TYPES if t not in present]
    if missing:
        errors.append(f"{', '.join(missing)} 유형이 하나도 없습니다.")

    warnings: list[str] = []
    counts = {t: sum(1 for s in resolved_details if s["listType"] == t) for t in playsets.DETAIL_TYPES}
    if n == 4 and counts["desire"] < 2:
        warnings.append("4인 플레이에서는 욕망을 하나 더 넣기를 권합니다.")
    if n == 5 and counts["place"] + counts["object"] < 3:
        warnings.append("5인 플레이에서는 장소나 물건을 하나 더 넣기를 권합니다.")
    if any(not p["characterName"] for p in state["players"]):
        warnings.append("아직 이름을 정하지 않은 캐릭터가 있습니다.")

    return {"errors": errors, "warnings": warnings, "canFinish": not errors}


def quick_setup(state: dict[str, Any], player_id: str) -> None:
    """간편 준비 — 인원수별로 미리 정해진 세트를 그대로 깔아 준다."""
    _require_host(state, player_id)
    _require_phase(state, "setup")
    if state["setup"]["slots"]:
        raise GameError("이미 진행 중인 준비가 있습니다. 처음부터 다시 하려면 되돌리기를 쓰세요.")
    playset = playsets.get(state["playsetId"])
    n = len(state["players"])
    entries = playsets.quick_setup_entries(playset, n)

    rels = entries["relationship"]
    details = [e for kind in ("desire", "object", "place") for e in entries[kind]]
    if len(rels) != n:
        raise GameError(f"간편 준비 관계 수({len(rels)})가 인원수({n})와 맞지 않습니다.")
    if len(details) != n:
        raise GameError(f"간편 준비 세부사항 수({len(details)})가 인원수({n})와 맞지 않습니다.")

    rel_slots = []
    for i, entry in enumerate(rels):
        slot = {
            "id": _uid(),
            "kind": "relationship",
            "listType": "relationship",
            "pairIndex": i,
            "relationshipSlotId": None,
            "category": entry["category"],
            "categoryName": entry["categoryName"],
            "element": entry["element"],
            "text": entry["text"],
            "claimedBy": None,
            "resolvedBy": None,
            "dice": [],
        }
        state["setup"]["slots"].append(slot)
        rel_slots.append(slot)

    for i, entry in enumerate(details):
        state["setup"]["slots"].append(
            {
                "id": _uid(),
                "kind": "detail",
                "listType": entry["kind"],
                "pairIndex": None,
                "relationshipSlotId": rel_slots[i % n]["id"],
                "category": entry["category"],
                "categoryName": entry["categoryName"],
                "element": entry["element"],
                "text": entry["text"],
                "claimedBy": None,
                "resolvedBy": None,
                "dice": [],
            }
        )

    state["central"] = []
    state["setup"]["history"] = []
    _log(state, f"방장이 간편 준비({n}인용)를 적용했습니다. 캐릭터 이름만 정하면 됩니다.", "setup", player_id)


def finish_setup(state: dict[str, Any], player_id: str) -> None:
    _require_host(state, player_id)
    _require_phase(state, "setup")
    check = setup_validation(state)
    if not check["canFinish"]:
        raise GameError(check["errors"][0])

    # 준비에 쓴 주사위는 전부 중앙으로 돌아가 다시 굴려진다.
    state["central"] = _build_pool(state)
    state["totalDice"] = len(state["central"])
    state["phase"] = "act1"
    state["act"] = 1
    state["turnSeat"] = state["startingSeat"]
    _log(state, "준비 완료. 주사위를 전부 중앙으로 되돌리고 1막을 시작합니다.", "phase")
    _open_scene(state, 1, 1)


# ---------------------------------------------------------------------------
# 장면
# ---------------------------------------------------------------------------


def _open_scene(state: dict[str, Any], act: int, number: int) -> None:
    spotlight = player_by_seat(state, state["turnSeat"])
    state["scene"] = {
        "act": act,
        "number": number,
        "spotlightId": spotlight["id"],
        "type": None,
        "notes": "",
        "status": "choosing",
        "award": None,
        "handoffTo": None,
    }
    _log(
        state,
        f"{act}막 {number}번째 장면 — {display_name(state, spotlight['id'])} 님에게 조명이 갑니다.",
        "scene",
    )


def _require_spotlight(state: dict[str, Any], player_id: str) -> dict[str, Any]:
    _require_phase(state, "act1", "act2")
    scene = state["scene"]
    if scene is None:
        raise GameError("진행 중인 장면이 없습니다.")
    if scene["spotlightId"] != player_id:
        raise GameError("조명 받은 사람만 할 수 있습니다.")
    return scene


def scene_choose_type(state: dict[str, Any], player_id: str, scene_type: str) -> None:
    scene = _require_spotlight(state, player_id)
    if scene["status"] != "choosing":
        raise GameError("이미 설정/해결을 골랐습니다.")
    if scene_type not in ("establish", "resolve"):
        raise GameError("설정 또는 해결 중 하나여야 합니다.")
    scene["type"] = scene_type
    scene["status"] = "playing"
    if scene_type == "establish":
        text = "설정을 골랐습니다 — 장면을 직접 열고, 결말의 색은 다른 사람들이 정해 줍니다."
    else:
        text = "해결을 골랐습니다 — 다른 사람들이 장면을 열고, 결말의 색은 본인이 중앙에서 고릅니다."
    _log(state, f"{display_name(state, player_id)} 님이 {text}", "scene", player_id)


def scene_set_notes(state: dict[str, Any], player_id: str, notes: str) -> None:
    _require_phase(state, "act1", "act2")
    scene = state["scene"]
    if scene is None:
        raise GameError("진행 중인 장면이 없습니다.")
    if player_id not in (scene["spotlightId"], state["hostId"]):
        raise GameError("조명 받은 사람이나 방장만 메모를 고칠 수 있습니다.")
    scene["notes"] = (notes or "")[:2000]


def _pick_central_die(state: dict[str, Any], color: str) -> dict[str, Any]:
    for i, die in enumerate(state["central"]):
        if die["color"] == color:
            return state["central"].pop(i)
    label = "검은" if color == "black" else "흰"
    raise GameError(f"중앙에 {label} 주사위가 남아 있지 않습니다.")


def scene_award_die(
    state: dict[str, Any],
    player_id: str,
    color: str,
    free_outcome: str | None = None,
) -> None:
    """장면의 결말로 주사위 한 개를 조명 받은 사람에게 준다."""
    _require_phase(state, "act1", "act2")
    scene = state["scene"]
    if scene is None:
        raise GameError("진행 중인 장면이 없습니다.")
    if scene["status"] != "playing":
        raise GameError("아직 설정/해결을 고르지 않았거나, 이미 결말이 정해졌습니다.")
    if color not in ("black", "white"):
        raise GameError("검은색 또는 흰색이어야 합니다.")

    if scene["type"] == "resolve":
        if player_id != scene["spotlightId"]:
            raise GameError("해결 장면의 색은 조명 받은 사람이 직접 고릅니다.")
    else:
        if player_id == scene["spotlightId"]:
            raise GameError("설정 장면의 색은 다른 사람들이 상의해서 정합니다.")

    is_last_die = len(state["central"]) == 1
    # 2막 마지막 주사위만, 색과 무관하게 결과를 원하는 쪽으로 지정할 수 있다.
    if free_outcome is not None:
        if not (state["phase"] == "act2" and is_last_die):
            raise GameError("2막의 마지막 주사위만 결과를 임의로 정할 수 있습니다.")
        if free_outcome not in ("good", "bad"):
            raise GameError("좋은 결말 또는 나쁜 결말이어야 합니다.")

    die = _pick_central_die(state, color)
    outcome = free_outcome or ("good" if color == "white" else "bad")
    scene["award"] = {
        "die": dict(die),
        "color": color,
        "outcome": outcome,
        "free": free_outcome is not None,
        "chosenBy": player_id,
    }

    spotlight = player_by_id(state, scene["spotlightId"])
    assert spotlight is not None
    if state["phase"] == "act1":
        # 1막에서는 받은 주사위를 반드시 다른 사람에게 넘긴다.
        scene["status"] = "handoff"
        scene["pendingDie"] = dict(die)
    else:
        spotlight["dice"].append(die)
        scene["status"] = "resolved"

    color_label = "검은" if color == "black" else "흰"
    outcome_label = "좋은 결말" if outcome == "good" else "나쁜 결말"
    suffix = " (마지막 주사위 — 색과 무관하게 지정)" if free_outcome else ""
    _log(
        state,
        f"{display_name(state, scene['spotlightId'])} 님의 장면이 {color_label} 주사위 "
        f"{die['value']}, {outcome_label}으로 끝났습니다.{suffix}",
        "scene",
        scene["spotlightId"],
    )


def scene_set_free_outcome(state: dict[str, Any], player_id: str, outcome: str) -> None:
    """2막의 마지막 주사위를 가져간 사람이 결과를 원하는 쪽으로 지정한다.

    주사위의 실제 색은 바뀌지 않는다. 후기 계산에는 색 그대로 들어간다.
    """
    scene = _require_spotlight(state, player_id)
    if state["phase"] != "act2":
        raise GameError("2막에서만 할 수 있습니다.")
    if not scene["award"]:
        raise GameError("아직 결말 주사위가 정해지지 않았습니다.")
    if state["central"]:
        raise GameError("마지막 주사위일 때만 결과를 임의로 정할 수 있습니다.")
    if outcome not in ("good", "bad"):
        raise GameError("좋은 결말 또는 나쁜 결말이어야 합니다.")
    scene["award"]["outcome"] = outcome
    scene["award"]["free"] = True
    label = "좋은 결말" if outcome == "good" else "나쁜 결말"
    _log(
        state,
        f"마지막 주사위 — {display_name(state, player_id)} 님이 결과를 {label}으로 정했습니다. "
        "(주사위의 실제 색은 후기 계산에 그대로 쓰입니다)",
        "scene",
        player_id,
    )


def scene_hand_off(state: dict[str, Any], player_id: str, target_id: str) -> None:
    """1막 전용 — 방금 받은 주사위를 다른 플레이어에게 넘긴다."""
    scene = _require_spotlight(state, player_id)
    if scene["status"] != "handoff":
        raise GameError("지금은 주사위를 넘길 때가 아닙니다.")
    if target_id == player_id:
        raise GameError("1막에서는 받은 주사위를 자기가 가질 수 없습니다.")
    target = _require_player(state, target_id)
    die = scene.pop("pendingDie")
    target["dice"].append(die)
    scene["handoffTo"] = target_id
    scene["status"] = "resolved"
    _log(
        state,
        f"{display_name(state, player_id)} 님이 그 주사위를 {display_name(state, target_id)} 님에게 넘겼습니다.",
        "scene",
        player_id,
    )


def scene_end(state: dict[str, Any], player_id: str) -> None:
    _require_phase(state, "act1", "act2")
    scene = state["scene"]
    if scene is None:
        raise GameError("진행 중인 장면이 없습니다.")
    if player_id not in (scene["spotlightId"], state["hostId"]):
        raise GameError("조명 받은 사람이나 방장만 장면을 마칠 수 있습니다.")
    if scene["status"] != "resolved":
        raise GameError("아직 결말이 정해지지 않았습니다.")
    _finish_scene(state)


def _finish_scene(state: dict[str, Any]) -> None:
    scene = state["scene"]
    state["scene"] = None
    n = len(state["players"])
    state["turnSeat"] = (state["turnSeat"] + 1) % n

    halfway = state["totalDice"] // 2
    if state["act"] == 1 and len(state["central"]) <= halfway:
        _log(state, f"중앙 주사위가 절반({halfway}개)이 되었습니다. 1막 종료.", "phase")
        _enter_twist(state)
        return
    if state["act"] == 2 and not state["central"]:
        _log(state, "중앙 주사위가 떨어졌습니다. 2막 종료.", "phase")
        _enter_aftermath(state)
        return
    _open_scene(state, state["act"], scene["number"] + 1)


# ---------------------------------------------------------------------------
# 비틀기
# ---------------------------------------------------------------------------


def _tiebreak(state: dict[str, Any], candidates: list[str], want_high: bool) -> str:
    """동점자끼리 자기 주사위를 전부 다시 굴려 승자를 가린다.

    실제 주사위 값은 건드리지 않는다. 표시된 합계가 바뀌면 헷갈리기 때문에
    재굴림은 판정용으로만 쓴다.
    """
    pool = list(candidates)
    for _ in range(20):
        scores = {}
        for pid in pool:
            player = player_by_id(state, pid)
            assert player is not None
            scores[pid] = sum(random.randint(1, 6) for _ in player["dice"])
        detail = ", ".join(f"{display_name(state, pid)} {scores[pid]}" for pid in pool)
        best = max(scores.values()) if want_high else min(scores.values())
        winners = [pid for pid, s in scores.items() if s == best]
        _log(state, f"동점 재굴림 — {detail}", "twist")
        if len(winners) == 1:
            return winners[0]
        pool = winners
    return pool[0]


def _extreme(state: dict[str, Any], candidates: list[str], tallies: dict[str, Any], want_high: bool) -> str:
    values = {pid: tallies[pid]["value"] for pid in candidates}
    target = max(values.values()) if want_high else min(values.values())
    tied = [pid for pid, v in values.items() if v == target]
    if len(tied) == 1:
        return tied[0]
    return _tiebreak(state, tied, want_high)


def _pick_twist_choosers(state: dict[str, Any], tallies: dict[str, Any]) -> list[str]:
    blacks = [pid for pid, t in tallies.items() if t["color"] == "black"]
    whites = [pid for pid, t in tallies.items() if t["color"] == "white"]

    if blacks and whites:
        return [_extreme(state, blacks, tallies, True), _extreme(state, whites, tallies, True)]

    single = blacks or whites
    if single:
        # 한 색만 나온 경우 그 색의 최고점자와 최저점자가 하나씩 고른다.
        if len(single) == 1:
            return [single[0], single[0]]
        high = _extreme(state, single, tallies, True)
        rest = [pid for pid in single if pid != high]
        low = _extreme(state, rest, tallies, False)
        return [high, low]

    # 아무도 색이 없다(전원 동점이거나 주사위가 없음) — 차례 순서로 두 사람.
    order = [player_by_seat(state, seat)["id"] for seat in turn_order(state)]
    return order[:2]


def _enter_twist(state: dict[str, Any]) -> None:
    state["phase"] = "twist"
    tallies: dict[str, Any] = {}
    for player in state["players"]:
        roll(player["dice"])
        tallies[player["id"]] = tally(player["dice"])
        t = tallies[player["id"]]
        _log(
            state,
            f"{display_name(state, player['id'])}: 검 {t['black']} / 흰 {t['white']} → "
            f"{t['value']}{'(' + ('검은색' if t['color'] == 'black' else '흰색') + ')' if t['color'] else ' (동점)'}",
            "twist",
            player["id"],
        )
    choosers = _pick_twist_choosers(state, tallies)
    state["twist"] = {
        "tallies": tallies,
        "choosers": choosers,
        "picks": [],
        "reference": {},
    }
    names = " / ".join(display_name(state, pid) for pid in choosers)
    _log(state, f"비틀기 — {names} 님이 비틀기 표에서 하나씩 고릅니다.", "phase")


def twist_reference_roll(state: dict[str, Any], player_id: str) -> None:
    """표를 고를 때 참고할 난수. 최종 선택은 어디까지나 자유다."""
    _require_phase(state, "twist")
    twist = state["twist"]
    if player_id not in twist["choosers"]:
        raise GameError("비틀기를 고를 사람만 굴릴 수 있습니다.")
    values = [random.randint(1, 6), random.randint(1, 6)]
    twist["reference"][player_id] = values
    _log(
        state,
        f"{display_name(state, player_id)} 님이 참고용으로 굴렸습니다 — 분류 {values[0]}, 요소 {values[1]}",
        "twist",
        player_id,
    )


def _twist_quota(twist: dict[str, Any], player_id: str) -> int:
    return twist["choosers"].count(player_id)


def twist_choose(state: dict[str, Any], player_id: str, category: int, element: int) -> None:
    _require_phase(state, "twist")
    twist = state["twist"]
    quota = _twist_quota(twist, player_id)
    if quota == 0:
        raise GameError("비틀기를 고를 사람이 아닙니다.")
    used = sum(1 for p in twist["picks"] if p["chooserId"] == player_id)
    if used >= quota:
        raise GameError("이미 고르셨습니다.")
    cat_name, text = twist_text(int(category), int(element))
    twist["picks"].append(
        {
            "id": _uid(),
            "chooserId": player_id,
            "category": int(category),
            "element": int(element),
            "categoryName": cat_name,
            "text": text,
        }
    )
    _log(state, f"{display_name(state, player_id)} 님의 비틀기 — {cat_name}: {text}", "twist", player_id)
    if len(twist["picks"]) >= len(twist["choosers"]):
        _start_act2(state)


def _start_act2(state: dict[str, Any]) -> None:
    for pick in state["twist"]["picks"]:
        state["twistDetails"].append(
            {
                "id": pick["id"],
                "categoryName": pick["categoryName"],
                "text": pick["text"],
                "chosenBy": pick["chooserId"],
            }
        )
    # 남은 중앙 주사위(처음의 절반)를 다시 굴린다. 플레이어가 가진 주사위는 그대로.
    roll(state["central"])
    state["phase"] = "act2"
    state["act"] = 2
    _log(
        state,
        f"2막 시작 — 중앙에 주사위 {len(state['central'])}개가 남았습니다. "
        "비틀기 요소는 누구나 어느 장면에서든 쓸 수 있습니다.",
        "phase",
    )
    _open_scene(state, 2, 1)


# ---------------------------------------------------------------------------
# 후기
# ---------------------------------------------------------------------------


def _enter_aftermath(state: dict[str, Any]) -> None:
    state["phase"] = "aftermath"
    state["scene"] = None
    results: dict[str, Any] = {}
    for player in state["players"]:
        roll(player["dice"])
        t = tally(player["dice"])
        results[player["id"]] = {
            **t,
            "diceCount": len(player["dice"]),
            "outcome": lookup_aftermath(t["color"], t["value"]),
        }
        _log(
            state,
            f"{display_name(state, player['id'])}: 검 {t['black']} / 흰 {t['white']} → "
            f"{results[player['id']]['outcome']['title']}",
            "aftermath",
            player["id"],
        )
    order = [player_by_seat(state, seat)["id"] for seat in turn_order(state)]
    state["aftermath"] = {"results": results, "order": order, "turnIdx": 0, "entries": []}
    _advance_montage(state, initial=True)
    _log(state, "후기 — 주사위를 하나씩 내려놓으며 마지막 모습을 그립니다.", "phase")


def _has_dice(state: dict[str, Any], player_id: str) -> bool:
    player = player_by_id(state, player_id)
    return bool(player and player["dice"])


def _advance_montage(state: dict[str, Any], initial: bool = False) -> None:
    after = state["aftermath"]
    order = after["order"]
    if not any(_has_dice(state, pid) for pid in order):
        state["phase"] = "finished"
        _log(state, "모든 주사위가 중앙으로 돌아갔습니다. 게임 종료.", "phase")
        return
    start = after["turnIdx"] if initial else after["turnIdx"] + 1
    for k in range(len(order) + 1):
        idx = (start + k) % len(order)
        if _has_dice(state, order[idx]):
            after["turnIdx"] = idx
            return


def _current_montage_player(state: dict[str, Any]) -> str:
    after = state["aftermath"]
    return after["order"][after["turnIdx"]]


def montage_place(state: dict[str, Any], player_id: str, text: str, die_id: str | None = None) -> None:
    _require_phase(state, "aftermath")
    if player_id != _current_montage_player(state):
        raise GameError("아직 차례가 아닙니다.")
    player = _require_player(state, player_id)
    if not player["dice"]:
        raise GameError("내려놓을 주사위가 없습니다.")
    if die_id:
        die = next((d for d in player["dice"] if d["id"] == die_id), None)
        if die is None:
            raise GameError("그런 주사위를 가지고 있지 않습니다.")
    else:
        die = player["dice"][0]
    player["dice"].remove(die)
    state["central"].append(die)
    entry = {
        "id": _uid(),
        "playerId": player_id,
        "text": (text or "").strip()[:500],
        "color": die["color"],
        "value": die["value"],
    }
    state["aftermath"]["entries"].append(entry)
    tone = ""
    if state["options"]["goodBadDice"]:
        tone = "(긍정) " if die["color"] == "white" else "(부정) "
    _log(
        state,
        f"몽타주 {tone}— 이것은 {display_name(state, player_id)}입니다. {entry['text']}".rstrip(),
        "aftermath",
        player_id,
    )
    _advance_montage(state)


def montage_pass(state: dict[str, Any], player_id: str) -> None:
    _require_phase(state, "aftermath")
    if player_id != _current_montage_player(state):
        raise GameError("아직 차례가 아닙니다.")
    _log(state, f"{display_name(state, player_id)} 님이 차례를 넘겼습니다.", "aftermath", player_id)
    _advance_montage(state)


def montage_gift(state: dict[str, Any], player_id: str, target_id: str, die_id: str | None = None) -> None:
    """주사위가 남는 사람이 부족한 사람에게 하나 넘겨 준다."""
    _require_phase(state, "aftermath")
    player = _require_player(state, player_id)
    target = _require_player(state, target_id)
    if target_id == player_id:
        raise GameError("자기 자신에게는 줄 수 없습니다.")
    if not player["dice"]:
        raise GameError("넘길 주사위가 없습니다.")
    if die_id:
        die = next((d for d in player["dice"] if d["id"] == die_id), None)
        if die is None:
            raise GameError("그런 주사위를 가지고 있지 않습니다.")
    else:
        die = player["dice"][0]
    player["dice"].remove(die)
    target["dice"].append(die)
    _log(
        state,
        f"{display_name(state, player_id)} 님이 {display_name(state, target_id)} 님에게 주사위를 넘겼습니다.",
        "aftermath",
        player_id,
    )
    if not _has_dice(state, _current_montage_player(state)):
        _advance_montage(state)


# ---------------------------------------------------------------------------
# 방장 진행 보조
# ---------------------------------------------------------------------------


def host_force_advance(state: dict[str, Any], player_id: str) -> None:
    """막혔을 때 방장이 한 칸 밀어 준다."""
    _require_host(state, player_id)
    phase = state["phase"]
    if phase in ("act1", "act2") and state["scene"]:
        scene = state["scene"]
        if scene["status"] == "resolved":
            _log(state, "방장이 장면을 마쳤습니다.", "info", player_id)
            _finish_scene(state)
            return
        if scene["status"] == "handoff":
            raise GameError("먼저 주사위를 넘길 사람을 정해야 합니다.")
        raise GameError("아직 장면의 결말이 정해지지 않았습니다.")
    if phase == "aftermath":
        _log(state, "방장이 몽타주 차례를 넘겼습니다.", "info", player_id)
        _advance_montage(state)
        return
    raise GameError("지금 단계에서는 강제 진행할 것이 없습니다.")


def host_end_act2(state: dict[str, Any], player_id: str) -> None:
    """액셀 밟기 — 2막을 일찍 끝내고 남은 중앙 주사위를 후기용으로 나눈다."""
    _require_host(state, player_id)
    _require_phase(state, "act2")
    if not state["options"]["accelerator"]:
        raise GameError("'액셀 밟기' 옵션이 켜져 있어야 합니다.")
    if state["scene"] and state["scene"]["status"] not in ("choosing", "resolved"):
        raise GameError("진행 중인 장면을 먼저 마치세요.")
    order = [player_by_seat(state, seat)["id"] for seat in turn_order(state)]
    i = 0
    while state["central"]:
        die = state["central"].pop()
        player = player_by_id(state, order[i % len(order)])
        assert player is not None
        player["dice"].append(die)
        i += 1
    state["scene"] = None
    _log(state, "액셀 밟기 — 남은 중앙 주사위를 후기용으로 나눴습니다.", "phase", player_id)
    _enter_aftermath(state)


def new_game(state: dict[str, Any], player_id: str) -> None:
    _require_host(state, player_id)
    _require_phase(state, "finished")
    for player in state["players"]:
        player["dice"] = []
        player["characterName"] = ""
    state.update(
        {
            "phase": "lobby",
            "central": [],
            "totalDice": 0,
            "act": 0,
            "setup": None,
            "scene": None,
            "twist": None,
            "twistDetails": [],
            "aftermath": None,
            "turnSeat": state["startingSeat"],
        }
    )
    _log(state, "새 게임을 위해 로비로 돌아갑니다.", "phase", player_id)


# ---------------------------------------------------------------------------
# 로비 설정
# ---------------------------------------------------------------------------


def set_playset(state: dict[str, Any], player_id: str, playset_id: str) -> None:
    _require_host(state, player_id)
    _require_phase(state, "lobby")
    playset = playsets.get(playset_id)
    state["playsetId"] = playset_id
    _log(state, f"플레이세트를 '{playset['name']}'(으)로 정했습니다.", "info", player_id)


def set_options(state: dict[str, Any], player_id: str, options: dict[str, Any]) -> None:
    _require_host(state, player_id)
    _require_phase(state, "lobby")
    current = state["options"]
    for key, value in (options or {}).items():
        if key not in DEFAULT_OPTIONS:
            continue
        if key == "dicePerPlayer":
            value = int(value)
            if not (2 <= value <= 8) or value % 2 != 0:
                raise GameError("인당 주사위는 2~8개 사이의 짝수여야 합니다.")
        elif key == "blackRatio":
            value = float(value)
            if not (0.2 <= value <= 0.8):
                raise GameError("검은 주사위 비율은 0.2~0.8 사이여야 합니다.")
        else:
            value = bool(value)
        current[key] = value
    _log(state, "방장이 선택 규칙을 바꿨습니다.", "info", player_id)


def set_starting_player(state: dict[str, Any], player_id: str, target_id: str) -> None:
    _require_host(state, player_id)
    _require_phase(state, "lobby")
    target = _require_player(state, target_id)
    state["startingSeat"] = target["seat"]
    state["turnSeat"] = target["seat"]
    _log(state, f"{target['name']} 님(가장 작은 동네 출신)부터 시작합니다.", "info", player_id)


def set_seat_order(state: dict[str, Any], player_id: str, order: list[str]) -> None:
    """자리 순서를 바꾼다. 관계는 인접한 사람끼리 맺으므로 자리가 중요하다."""
    _require_host(state, player_id)
    _require_phase(state, "lobby")
    ids = [p["id"] for p in state["players"]]
    if sorted(order) != sorted(ids):
        raise GameError("자리 순서 목록이 참가자 목록과 맞지 않습니다.")
    start_id = player_by_seat(state, state["startingSeat"])["id"]
    for seat, pid in enumerate(order):
        player = player_by_id(state, pid)
        assert player is not None
        player["seat"] = seat
    state["players"].sort(key=lambda p: p["seat"])
    state["startingSeat"] = player_by_id(state, start_id)["seat"]  # type: ignore[index]
    state["turnSeat"] = state["startingSeat"]
    _log(state, "방장이 자리 순서를 바꿨습니다.", "info", player_id)


def set_name(state: dict[str, Any], player_id: str, name: str) -> None:
    player = _require_player(state, player_id)
    player["name"] = (name or "").strip()[:20] or player["name"]


def set_character_name(state: dict[str, Any], player_id: str, name: str) -> None:
    player = _require_player(state, player_id)
    old = player["characterName"]
    player["characterName"] = (name or "").strip()[:30]
    if player["characterName"] and player["characterName"] != old:
        _log(state, f"{player['name']} 님의 캐릭터 이름: {player['characterName']}", "info", player_id)


# ---------------------------------------------------------------------------
# 파생 정보 (클라이언트 편의용)
# ---------------------------------------------------------------------------


def derived(state: dict[str, Any]) -> dict[str, Any]:
    n = len(state["players"])
    info: dict[str, Any] = {
        "pairs": pairs(state) if n else [],
        "turnOrder": turn_order(state) if n else [],
        "centralCount": len(state["central"]),
        "centralByColor": {
            "black": sum(1 for d in state["central"] if d["color"] == "black"),
            "white": sum(1 for d in state["central"] if d["color"] == "white"),
        },
        "halfway": state["totalDice"] // 2,
        "currentPlayerId": None,
    }
    if state["phase"] == "setup":
        info["currentPlayerId"] = player_by_seat(state, state["turnSeat"])["id"]
        info["setupValidation"] = setup_validation(state)
        info["setupDiceRequired"] = setup_dice_required(state)
    elif state["phase"] in ("act1", "act2") and state["scene"]:
        info["currentPlayerId"] = state["scene"]["spotlightId"]
    elif state["phase"] == "aftermath" and state["aftermath"]:
        info["currentPlayerId"] = _current_montage_player(state)
    return info


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    """토큰 같은 비공개 정보를 뺀 전체 상태. 피아스코에는 숨은 정보가 없다."""
    out = {k: v for k, v in state.items() if k != "players"}
    out["players"] = [
        {
            "id": p["id"],
            "name": p["name"],
            "characterName": p["characterName"],
            "seat": p["seat"],
            "connected": p["connected"],
            "dice": p["dice"],
            "isHost": p["id"] == state["hostId"],
        }
        for p in state["players"]
    ]
    out["derived"] = derived(state)
    return out


# ---------------------------------------------------------------------------
# 액션 디스패치
# ---------------------------------------------------------------------------

ACTIONS = {
    "set_name": lambda s, p, d: set_name(s, p, d.get("name", "")),
    "set_character_name": lambda s, p, d: set_character_name(s, p, d.get("name", "")),
    "set_playset": lambda s, p, d: set_playset(s, p, d["playsetId"]),
    "set_options": lambda s, p, d: set_options(s, p, d.get("options", {})),
    "set_starting_player": lambda s, p, d: set_starting_player(s, p, d["playerId"]),
    "set_seat_order": lambda s, p, d: set_seat_order(s, p, d["order"]),
    "start_game": lambda s, p, d: start_game(s, p),
    "quick_setup": lambda s, p, d: quick_setup(s, p),
    "setup_claim_category": lambda s, p, d: setup_claim_category(
        s,
        p,
        d["dieId"],
        d["listType"],
        d.get("pairIndex"),
        d.get("relationshipSlotId"),
        d.get("valueOverride"),
    ),
    "setup_assign_element": lambda s, p, d: setup_assign_element(
        s, p, d["dieId"], d["slotId"], d.get("valueOverride")
    ),
    "setup_undo": lambda s, p, d: setup_undo(s, p),
    "finish_setup": lambda s, p, d: finish_setup(s, p),
    "scene_choose_type": lambda s, p, d: scene_choose_type(s, p, d["sceneType"]),
    "scene_set_notes": lambda s, p, d: scene_set_notes(s, p, d.get("notes", "")),
    "scene_award_die": lambda s, p, d: scene_award_die(s, p, d["color"], d.get("freeOutcome")),
    "scene_set_free_outcome": lambda s, p, d: scene_set_free_outcome(s, p, d["outcome"]),
    "scene_hand_off": lambda s, p, d: scene_hand_off(s, p, d["targetPlayerId"]),
    "scene_end": lambda s, p, d: scene_end(s, p),
    "twist_reference_roll": lambda s, p, d: twist_reference_roll(s, p),
    "twist_choose": lambda s, p, d: twist_choose(s, p, d["category"], d["element"]),
    "montage_place": lambda s, p, d: montage_place(s, p, d.get("text", ""), d.get("dieId")),
    "montage_pass": lambda s, p, d: montage_pass(s, p),
    "montage_gift": lambda s, p, d: montage_gift(s, p, d["targetPlayerId"], d.get("dieId")),
    "host_force_advance": lambda s, p, d: host_force_advance(s, p),
    "host_end_act2": lambda s, p, d: host_end_act2(s, p),
    "new_game": lambda s, p, d: new_game(s, p),
}


def apply_action(state: dict[str, Any], player_id: str, action: str, payload: dict[str, Any] | None) -> None:
    handler = ACTIONS.get(action)
    if handler is None:
        raise GameError(f"알 수 없는 동작입니다: {action}")
    try:
        handler(state, player_id, payload or {})
    except KeyError as exc:
        raise GameError(f"필수 항목이 빠졌습니다: {exc.args[0]}") from exc
    except playsets.PlaysetError as exc:
        raise GameError(str(exc)) from exc
