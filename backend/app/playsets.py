"""플레이세트 데이터 적재와 조회.

원본 JSON 은 목록별로 `{분류명: [요소 6개]}` 모양이라 순서에 의존한다.
게임 로직은 "주사위 눈 = 분류 번호 = 요소 번호"를 쓰므로, 적재 시점에
1~6 번호가 붙은 배열로 정규화해 둔다.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent / "data" / "playsets.json"

# 내부에서 쓰는 목록 종류 → 원본 JSON 키
LIST_KEYS: dict[str, str] = {
    "relationship": "relationships",
    "desire": "desires",
    "object": "objects",
    "place": "places",
}

LIST_LABELS: dict[str, str] = {
    "relationship": "관계",
    "desire": "욕망",
    "object": "물건",
    "place": "장소",
}

DETAIL_TYPES = ("desire", "object", "place")


class PlaysetError(ValueError):
    """플레이세트 데이터나 조회 요청이 잘못된 경우."""


def _normalize_list(raw: dict[str, list[str]], where: str) -> list[dict[str, Any]]:
    categories = list(raw.items())
    if len(categories) != 6:
        raise PlaysetError(f"{where}: 분류는 6개여야 하는데 {len(categories)}개입니다.")
    out = []
    for ci, (name, elements) in enumerate(categories, start=1):
        if len(elements) != 6:
            raise PlaysetError(f"{where}/{name}: 요소는 6개여야 하는데 {len(elements)}개입니다.")
        out.append(
            {
                "number": ci,
                "name": name,
                "elements": [{"number": ei, "text": t} for ei, t in enumerate(elements, start=1)],
            }
        )
    return out


def _normalize_playset(raw: dict[str, Any]) -> dict[str, Any]:
    pid = raw["id"]
    lists = {
        kind: _normalize_list(raw[json_key], f"{pid}/{json_key}")
        for kind, json_key in LIST_KEYS.items()
    }
    return {
        "id": pid,
        "name": raw["name"],
        "lists": lists,
        "quickSetup": raw.get("quickSetup", {}),
        "custom": False,
    }


def _load_builtin() -> dict[str, dict[str, Any]]:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {p["id"]: _normalize_playset(p) for p in raw["playsets"]}


_BUILTIN: dict[str, dict[str, Any]] = _load_builtin()
_CUSTOM: dict[str, dict[str, Any]] = {}


def all_playsets() -> list[dict[str, Any]]:
    return list(_BUILTIN.values()) + list(_CUSTOM.values())


def summaries() -> list[dict[str, Any]]:
    """목록 화면용 요약(표 본문 제외)."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "custom": p["custom"],
            "hasQuickSetup": bool(p["quickSetup"]),
        }
        for p in all_playsets()
    ]


def get(playset_id: str) -> dict[str, Any]:
    if playset_id in _BUILTIN:
        return _BUILTIN[playset_id]
    if playset_id in _CUSTOM:
        return _CUSTOM[playset_id]
    raise PlaysetError(f"'{playset_id}' 플레이세트를 찾을 수 없습니다.")


def register_custom(raw: dict[str, Any]) -> dict[str, Any]:
    """웹 에디터/업로드로 들어온 커스텀 플레이세트를 검증하고 등록한다."""
    if not isinstance(raw, dict):
        raise PlaysetError("플레이세트는 JSON 객체여야 합니다.")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise PlaysetError("플레이세트 이름이 필요합니다.")
    missing = [k for k in LIST_KEYS.values() if k not in raw]
    if missing:
        raise PlaysetError(f"다음 목록이 빠졌습니다: {', '.join(missing)}")

    pid = re.sub(r"[^a-z0-9]+", "-", str(raw.get("id") or name).lower()).strip("-") or "custom"
    if pid in _BUILTIN:
        pid = f"{pid}-custom"
    normalized = _normalize_playset({**raw, "id": pid, "name": name})
    normalized["custom"] = True
    normalized["quickSetup"] = {}  # 커스텀은 간편 준비를 제공하지 않는다
    _CUSTOM[pid] = normalized
    return normalized


def element_text(playset: dict[str, Any], kind: str, category: int, element: int) -> tuple[str, str]:
    """(분류명, 요소 텍스트). category/element 는 1-based."""
    if kind not in LIST_KEYS:
        raise PlaysetError(f"알 수 없는 목록 종류입니다: {kind}")
    if not (1 <= category <= 6):
        raise PlaysetError("분류 번호는 1~6이어야 합니다.")
    cat = playset["lists"][kind][category - 1]
    if not (1 <= element <= 6):
        raise PlaysetError("요소 번호는 1~6이어야 합니다.")
    return cat["name"], cat["elements"][element - 1]["text"]


def category_name(playset: dict[str, Any], kind: str, category: int) -> str:
    return element_text(playset, kind, category, 1)[0]


# --------------------------------------------------------------------------
# 간편 준비
# --------------------------------------------------------------------------

_QUICK_SECTIONS = (
    ("relationships", "relationship"),
    ("desires", "desire"),
    ("places", "place"),
    ("objects", "object"),
)


def _key_min_count(key: str) -> int:
    """'3_4_5' 처럼 인원수를 이어붙인 키에서 최소 인원수를 뽑는다."""
    nums = [int(n) for n in re.findall(r"\d+", key)]
    return min(nums) if nums else 0


def _best_match(playset: dict[str, Any], kind: str, entry: str) -> tuple[int, int, float]:
    """'분류: 요소' 형태의 문자열을 (분류번호, 요소번호)로 되돌린다.

    간편 준비 표기와 본문 표기가 미묘하게 다른 경우('맥타운 외곽' vs '맥타운: 외곽',
    '수퍼마켓' vs '슈퍼마켓')가 있어 정확 일치 대신 유사도 최댓값을 쓴다.
    """
    text = entry.lstrip("+ ").strip()
    if ": " in text:
        cat_hint, elem_hint = text.split(": ", 1)
    else:
        cat_hint, elem_hint = "", text

    best: tuple[int, int, float] = (1, 1, -1.0)
    for cat in playset["lists"][kind]:
        cat_score = SequenceMatcher(None, cat_hint, cat["name"]).ratio() if cat_hint else 0.0
        for elem in cat["elements"]:
            score = SequenceMatcher(None, elem_hint, elem["text"]).ratio() + 0.3 * cat_score
            if score > best[2]:
                best = (cat["number"], elem["number"], score)
    return best


def quick_setup_entries(playset: dict[str, Any], player_count: int) -> dict[str, list[dict[str, Any]]]:
    """인원수에 맞는 간편 준비 항목을 종류별로 돌려준다.

    키는 '그 인원수부터 추가되는 항목'을 뜻한다(키의 최소 인원수 이상이면 포함).
    결과는 관계 `player_count` 개, 세부사항 `player_count` 개가 되도록 설계돼 있다.
    """
    quick = playset.get("quickSetup") or {}
    if not quick:
        raise PlaysetError("이 플레이세트에는 간편 준비 데이터가 없습니다.")

    result: dict[str, list[dict[str, Any]]] = {}
    for json_key, kind in _QUICK_SECTIONS:
        section = quick.get(json_key, {})
        picked: list[dict[str, Any]] = []
        for key in sorted(section.keys(), key=_key_min_count):
            if _key_min_count(key) > player_count:
                continue
            for entry in section[key]:
                cat, elem, score = _best_match(playset, kind, entry)
                cat_name, elem_text = element_text(playset, kind, cat, elem)
                picked.append(
                    {
                        "kind": kind,
                        "category": cat,
                        "element": elem,
                        "categoryName": cat_name,
                        "text": elem_text,
                        "source": entry,
                        "matchScore": round(score, 3),
                    }
                )
        result[kind] = picked
    return result
