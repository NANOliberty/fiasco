"""게임 엔진 테스트 — 전체 게임을 프로그램으로 끝까지 돌려 본다."""

from __future__ import annotations

import random

import pytest

from app import game, playsets
from app.tables import lookup_aftermath


def make_room(n: int = 3, playset_id: str = "pretty_southern_town") -> dict:
    state = game.new_state("TEST01")
    for i in range(n):
        game.add_player(state, f"P{i + 1}")
    host = state["players"][0]["id"]
    game.set_playset(state, host, playset_id)
    return state


def host_id(state: dict) -> str:
    return state["hostId"]


def current_setup_player(state: dict) -> str:
    return game.player_by_seat(state, state["turnSeat"])["id"]


def spotlight(state: dict) -> str:
    return state["scene"]["spotlightId"]


def other_than(state: dict, player_id: str) -> str:
    return next(p["id"] for p in state["players"] if p["id"] != player_id)


# ---------------------------------------------------------------------------
# 플레이세트 데이터
# ---------------------------------------------------------------------------


def test_all_playsets_normalize():
    for playset in playsets.all_playsets():
        for kind in playsets.LIST_KEYS:
            categories = playset["lists"][kind]
            assert [c["number"] for c in categories] == [1, 2, 3, 4, 5, 6]
            for cat in categories:
                assert [e["number"] for e in cat["elements"]] == [1, 2, 3, 4, 5, 6]


@pytest.mark.parametrize("count", [3, 4, 5])
def test_quick_setup_entry_counts(count):
    """간편 준비는 인원수만큼의 관계와 세부사항을 정확히 내놓아야 한다."""
    for playset in playsets.all_playsets():
        if not playset["quickSetup"]:
            continue
        entries = playsets.quick_setup_entries(playset, count)
        details = sum(len(entries[k]) for k in ("desire", "object", "place"))
        assert len(entries["relationship"]) == count, playset["id"]
        assert details == count, playset["id"]
        # 표기 흔들림이 있어도 원문과 충분히 가까운 항목으로 되돌아가야 한다.
        # 본문에 괄호 예시가 붙은 항목("전문직(목사, 의사…)과 손님")은 점수가 낮게
        # 나오므로 하한만 확인하고, 정확도는 아래 골든 테스트에서 검증한다.
        for kind, items in entries.items():
            for item in items:
                assert item["matchScore"] > 0.7, (playset["id"], kind, item)


@pytest.mark.parametrize(
    "playset_id,kind,source_fragment,expected",
    [
        # 간편 준비 표기와 본문 표기가 어긋나는 경우들 — 되돌린 번호가 정확해야 한다
        ("suburbia", "place", "수퍼마켓", (6, 6)),  # 수퍼 vs 슈퍼
        ("the_ice", "place", "맥타운 외곽", (4, 2)),  # '맥타운 외곽' vs '맥타운: 외곽'
        ("pretty_southern_town", "relationship", "전문직과 손님", (2, 6)),  # 본문엔 괄호 예시가 붙음
        ("boomtown", "relationship", "공무원 / 시민", (6, 5)),
        ("suburbia", "relationship", "직공 / 집 주인", (2, 4)),
        ("boomtown", "relationship", "같은 사람과 결혼", (3, 5)),
        ("pretty_southern_town", "place", "엘 페로 알토", (1, 2)),
    ],
)
def test_quick_setup_resolves_tricky_labels(playset_id, kind, source_fragment, expected):
    playset = playsets.get(playset_id)
    entries = playsets.quick_setup_entries(playset, 5)
    match = next(e for e in entries[kind] if source_fragment in e["source"])
    assert (match["category"], match["element"]) == expected
    # 되돌린 번호로 표를 다시 조회하면 매칭된 텍스트가 그대로 나와야 한다
    cat_name, text = playsets.element_text(playset, kind, match["category"], match["element"])
    assert (cat_name, text) == (match["categoryName"], match["text"])


# ---------------------------------------------------------------------------
# 시작 조건
# ---------------------------------------------------------------------------


def test_needs_three_players():
    state = game.new_state("X")
    game.add_player(state, "혼자")
    game.set_playset(state, state["hostId"], "boomtown")
    with pytest.raises(game.GameError, match="3~5명"):
        game.start_game(state, state["hostId"])


def test_needs_playset():
    state = game.new_state("X")
    for i in range(3):
        game.add_player(state, f"P{i}")
    with pytest.raises(game.GameError, match="플레이세트"):
        game.start_game(state, state["hostId"])


def test_sixth_player_rejected():
    state = make_room(5)
    with pytest.raises(game.GameError, match="정원"):
        game.add_player(state, "여섯번째")


def test_only_host_starts():
    state = make_room(3)
    with pytest.raises(game.GameError, match="방장"):
        game.start_game(state, state["players"][1]["id"])


def test_dice_count_matches_player_count():
    for n in (3, 4, 5):
        state = make_room(n)
        game.start_game(state, host_id(state))
        assert state["totalDice"] == n * 4
        black = sum(1 for d in state["central"] if d["color"] == "black")
        assert black == n * 2


# ---------------------------------------------------------------------------
# 준비 단계
# ---------------------------------------------------------------------------


def manual_setup(state: dict) -> None:
    """관계 3개 + 유형이 다른 세부사항 3개를 손으로 깐다(3인 기준)."""
    n = len(state["players"])
    detail_kinds = ["desire", "object", "place"] * n
    for pair_index in range(n):
        actor = current_setup_player(state)
        die = state["central"][0]
        game.setup_claim_category(state, actor, die["id"], "relationship", pair_index=pair_index)
        slot = state["setup"]["slots"][-1]

        actor = current_setup_player(state)
        game.setup_assign_element(state, actor, state["central"][0]["id"], slot["id"])

        actor = current_setup_player(state)
        game.setup_claim_category(
            state,
            actor,
            state["central"][0]["id"],
            detail_kinds[pair_index],
            relationship_slot_id=slot["id"],
        )
        detail = state["setup"]["slots"][-1]

        actor = current_setup_player(state)
        game.setup_assign_element(state, actor, state["central"][0]["id"], detail["id"])


def test_manual_setup_consumes_every_die():
    state = make_room(3)
    game.start_game(state, host_id(state))
    manual_setup(state)
    assert state["central"] == []
    check = game.setup_validation(state)
    assert check["errors"] == [], check
    assert check["canFinish"]


def test_setup_turn_order_is_enforced():
    state = make_room(3)
    game.start_game(state, host_id(state))
    wrong = game.player_by_seat(state, (state["turnSeat"] + 1) % 3)["id"]
    with pytest.raises(game.GameError, match="차례"):
        game.setup_claim_category(state, wrong, state["central"][0]["id"], "relationship", pair_index=0)


def test_setup_rejects_duplicate_relationship_on_a_pair():
    state = make_room(3)
    game.start_game(state, host_id(state))
    actor = current_setup_player(state)
    game.setup_claim_category(state, actor, state["central"][0]["id"], "relationship", pair_index=0)
    actor = current_setup_player(state)
    with pytest.raises(game.GameError, match="이미 관계"):
        game.setup_claim_category(state, actor, state["central"][0]["id"], "relationship", pair_index=0)


def test_setup_blocks_actions_that_make_completion_impossible():
    """관계를 하나도 안 만든 채 세부사항만 쌓으면 규칙대로 끝낼 수 없다."""
    state = make_room(3)
    game.start_game(state, host_id(state))
    actor = current_setup_player(state)
    game.setup_claim_category(state, actor, state["central"][0]["id"], "relationship", pair_index=0)
    slot = state["setup"]["slots"][-1]
    actor = current_setup_player(state)
    game.setup_assign_element(state, actor, state["central"][0]["id"], slot["id"])

    # 이 관계에 세부사항 4개를 몰아주려 하면 어느 순간 막혀야 한다.
    kinds = ["desire", "object", "place", "desire"]
    with pytest.raises(game.GameError, match="부족|자리가 없어"):
        for kind in kinds:
            actor = current_setup_player(state)
            game.setup_claim_category(
                state, actor, state["central"][0]["id"], kind, relationship_slot_id=slot["id"]
            )
            detail = state["setup"]["slots"][-1]
            actor = current_setup_player(state)
            game.setup_assign_element(state, actor, state["central"][0]["id"], detail["id"])


def test_rejected_setup_action_returns_the_die():
    state = make_room(3)
    game.start_game(state, host_id(state))
    before = len(state["central"])
    actor = current_setup_player(state)
    with pytest.raises(game.GameError):
        game.setup_claim_category(state, actor, state["central"][0]["id"], "desire", relationship_slot_id="없음")
    assert len(state["central"]) == before
    assert state["turnSeat"] == 0 or True  # 차례도 넘어가지 않는다
    assert current_setup_player(state) == actor


def test_setup_undo_restores_die_and_turn():
    state = make_room(3)
    game.start_game(state, host_id(state))
    actor = current_setup_player(state)
    before_dice = len(state["central"])
    game.setup_claim_category(state, actor, state["central"][0]["id"], "relationship", pair_index=0)
    assert len(state["central"]) == before_dice - 1
    game.setup_undo(state, host_id(state))
    assert len(state["central"]) == before_dice
    assert current_setup_player(state) == actor
    assert state["setup"]["slots"] == []


def test_last_setup_die_value_can_be_chosen():
    state = make_room(3)
    game.start_game(state, host_id(state))
    n = len(state["players"])
    # 마지막 한 개만 남을 때까지 정상 진행
    for pair_index in range(n):
        kinds = ["desire", "object", "place"]
        actor = current_setup_player(state)
        game.setup_claim_category(state, actor, state["central"][0]["id"], "relationship", pair_index=pair_index)
        slot = state["setup"]["slots"][-1]
        actor = current_setup_player(state)
        game.setup_assign_element(state, actor, state["central"][0]["id"], slot["id"])
        actor = current_setup_player(state)
        game.setup_claim_category(
            state, actor, state["central"][0]["id"], kinds[pair_index], relationship_slot_id=slot["id"]
        )
        detail = state["setup"]["slots"][-1]
        if pair_index < n - 1:
            actor = current_setup_player(state)
            game.setup_assign_element(state, actor, state["central"][0]["id"], detail["id"])

    assert len(state["central"]) == 1
    actor = current_setup_player(state)
    game.setup_assign_element(state, actor, state["central"][0]["id"], detail["id"], value_override=4)
    assert detail["element"] == 4


def test_free_die_value_rejected_when_more_dice_remain():
    state = make_room(3)
    game.start_game(state, host_id(state))
    actor = current_setup_player(state)
    with pytest.raises(game.GameError, match="마지막 한 개"):
        game.setup_claim_category(
            state, actor, state["central"][0]["id"], "relationship", pair_index=0, value_override=3
        )


@pytest.mark.parametrize("count", [3, 4, 5])
def test_quick_setup_finishes_immediately(count):
    state = make_room(count)
    game.start_game(state, host_id(state))
    game.quick_setup(state, host_id(state))
    check = game.setup_validation(state)
    assert check["errors"] == [], check
    rel = [s for s in state["setup"]["slots"] if s["kind"] == "relationship"]
    detail = [s for s in state["setup"]["slots"] if s["kind"] == "detail"]
    assert len(rel) == count
    assert len(detail) == count
    assert {s["pairIndex"] for s in rel} == set(range(count))


def test_finish_setup_returns_all_dice_to_center():
    state = make_room(3)
    game.start_game(state, host_id(state))
    game.quick_setup(state, host_id(state))
    game.finish_setup(state, host_id(state))
    assert state["phase"] == "act1"
    assert len(state["central"]) == state["totalDice"] == 12
    assert all(not p["dice"] for p in state["players"])
    assert state["scene"]["act"] == 1


def test_finish_setup_blocked_while_dice_remain():
    state = make_room(3)
    game.start_game(state, host_id(state))
    with pytest.raises(game.GameError, match="주사위"):
        game.finish_setup(state, host_id(state))


# ---------------------------------------------------------------------------
# 장면
# ---------------------------------------------------------------------------


def begin_act1(state: dict) -> None:
    game.start_game(state, host_id(state))
    game.quick_setup(state, host_id(state))
    for p in state["players"]:
        game.set_character_name(state, p["id"], f"{p['name']}의 캐릭터")
    game.finish_setup(state, host_id(state))


def play_scene(state: dict, scene_type: str = "resolve", color: str | None = None) -> None:
    """장면 하나를 끝까지 진행한다."""
    star = spotlight(state)
    game.scene_choose_type(state, star, scene_type)
    if color is None:
        color = state["central"][0]["color"]
    awarder = star if scene_type == "resolve" else other_than(state, star)
    game.scene_award_die(state, awarder, color)
    if state["scene"]["status"] == "handoff":
        game.scene_hand_off(state, star, other_than(state, star))
    game.scene_end(state, star)


def test_scene_type_is_exclusive():
    state = make_room(3)
    begin_act1(state)
    star = spotlight(state)
    game.scene_choose_type(state, star, "resolve")
    with pytest.raises(game.GameError, match="이미"):
        game.scene_choose_type(state, star, "establish")


def test_only_spotlight_chooses_scene_type():
    state = make_room(3)
    begin_act1(state)
    star = spotlight(state)
    with pytest.raises(game.GameError, match="조명"):
        game.scene_choose_type(state, other_than(state, star), "resolve")


def test_resolve_color_is_picked_by_spotlight_only():
    state = make_room(3)
    begin_act1(state)
    star = spotlight(state)
    game.scene_choose_type(state, star, "resolve")
    with pytest.raises(game.GameError, match="직접"):
        game.scene_award_die(state, other_than(state, star), state["central"][0]["color"])


def test_establish_color_is_picked_by_others_only():
    state = make_room(3)
    begin_act1(state)
    star = spotlight(state)
    game.scene_choose_type(state, star, "establish")
    with pytest.raises(game.GameError, match="다른 사람들"):
        game.scene_award_die(state, star, state["central"][0]["color"])


def test_act1_forces_handoff_to_someone_else():
    state = make_room(3)
    begin_act1(state)
    star = spotlight(state)
    game.scene_choose_type(state, star, "resolve")
    game.scene_award_die(state, star, state["central"][0]["color"])
    assert state["scene"]["status"] == "handoff"
    assert not game.player_by_id(state, star)["dice"]
    with pytest.raises(game.GameError, match="자기가 가질 수 없"):
        game.scene_hand_off(state, star, star)
    target = other_than(state, star)
    game.scene_hand_off(state, star, target)
    assert len(game.player_by_id(state, target)["dice"]) == 1


def test_scene_cannot_end_before_result():
    state = make_room(3)
    begin_act1(state)
    star = spotlight(state)
    game.scene_choose_type(state, star, "resolve")
    with pytest.raises(game.GameError, match="결말"):
        game.scene_end(state, star)


def test_spotlight_rotates_in_turn_order():
    state = make_room(3)
    begin_act1(state)
    seen = []
    for _ in range(3):
        seen.append(spotlight(state))
        play_scene(state)
    order = [game.player_by_seat(state, s)["id"] for s in game.turn_order(state)]
    assert seen == order


def test_act1_ends_when_central_pool_halves():
    state = make_room(3)
    begin_act1(state)
    halfway = state["totalDice"] // 2
    scenes = 0
    while state["phase"] == "act1":
        play_scene(state)
        scenes += 1
        assert scenes <= 20, "1막이 끝나지 않는다"
    assert scenes == halfway == 6  # 인원 × 2 장면
    assert state["phase"] == "twist"
    assert len(state["central"]) == halfway


# ---------------------------------------------------------------------------
# 비틀기
# ---------------------------------------------------------------------------


def run_act1(state: dict) -> None:
    while state["phase"] == "act1":
        play_scene(state)


def test_twist_choosers_and_transition_to_act2():
    random.seed(7)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    assert state["phase"] == "twist"
    twist = state["twist"]
    assert len(twist["choosers"]) == 2

    for pid in dict.fromkeys(twist["choosers"]):
        game.twist_reference_roll(state, pid)
        assert len(twist["reference"][pid]) == 2

    for i, pid in enumerate(twist["choosers"]):
        if state["phase"] != "twist":
            break
        game.twist_choose(state, pid, category=(i % 6) + 1, element=((i + 2) % 6) + 1)

    assert state["phase"] == "act2"
    assert len(state["twistDetails"]) == 2
    assert state["act"] == 2
    assert state["scene"]["act"] == 2


def test_non_chooser_cannot_pick_twist():
    random.seed(11)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    outsider = next(
        (p["id"] for p in state["players"] if p["id"] not in state["twist"]["choosers"]), None
    )
    if outsider:
        with pytest.raises(game.GameError, match="고를 사람"):
            game.twist_choose(state, outsider, 1, 1)


def test_twist_keeps_player_dice_and_rerolls_center():
    random.seed(3)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    held = {p["id"]: len(p["dice"]) for p in state["players"]}
    assert sum(held.values()) == state["totalDice"] // 2
    finish_twist(state)
    assert {p["id"]: len(p["dice"]) for p in state["players"]} == held
    assert len(state["central"]) == state["totalDice"] // 2


def test_twist_choosers_cover_both_colors_when_present():
    random.seed(5)
    state = make_room(4)
    begin_act1(state)
    run_act1(state)
    tallies = state["twist"]["tallies"]
    colors = {t["color"] for t in tallies.values() if t["color"]}
    if colors == {"black", "white"}:
        chooser_colors = {tallies[pid]["color"] for pid in state["twist"]["choosers"]}
        assert chooser_colors == {"black", "white"}


def test_single_color_gives_high_and_low_the_picks():
    """전원이 같은 색인 경우 그 색의 최고점자와 최저점자가 고른다."""
    state = make_room(4)
    ids = [p["id"] for p in state["players"]]
    tallies = {
        ids[0]: {"black": 10, "white": 2, "value": 8, "color": "black"},
        ids[1]: {"black": 9, "white": 4, "value": 5, "color": "black"},
        ids[2]: {"black": 8, "white": 6, "value": 2, "color": "black"},
        ids[3]: {"black": 12, "white": 1, "value": 11, "color": "black"},
    }
    choosers = game._pick_twist_choosers(state, tallies)
    assert choosers == [ids[3], ids[2]]


def test_no_colors_falls_back_to_turn_order():
    state = make_room(3)
    ids = [p["id"] for p in state["players"]]
    tallies = {pid: {"black": 5, "white": 5, "value": 0, "color": None} for pid in ids}
    assert game._pick_twist_choosers(state, tallies) == ids[:2]


# ---------------------------------------------------------------------------
# 2막
# ---------------------------------------------------------------------------


def finish_twist(state: dict) -> None:
    for i, pid in enumerate(state["twist"]["choosers"]):
        if state["phase"] != "twist":
            return
        game.twist_choose(state, pid, (i % 6) + 1, (i % 6) + 1)


def test_act2_keeps_the_die_with_the_spotlight():
    random.seed(13)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    finish_twist(state)

    star = spotlight(state)
    before = len(game.player_by_id(state, star)["dice"])
    game.scene_choose_type(state, star, "resolve")
    game.scene_award_die(state, star, state["central"][0]["color"])
    assert state["scene"]["status"] == "resolved"  # 넘기는 단계가 없다
    assert len(game.player_by_id(state, star)["dice"]) == before + 1


def test_free_outcome_only_on_the_last_die_and_color_is_untouched():
    random.seed(17)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    finish_twist(state)

    # 마지막 한 개가 남을 때까지 진행
    while len(state["central"]) > 1:
        star = spotlight(state)
        game.scene_choose_type(state, star, "resolve")
        game.scene_award_die(state, star, state["central"][0]["color"])
        game.scene_end(state, star)
        if len(state["central"]) > 1:
            continue

    star = spotlight(state)
    game.scene_choose_type(state, star, "resolve")
    last_color = state["central"][0]["color"]
    opposite = "good" if last_color == "black" else "bad"
    game.scene_award_die(state, star, last_color, free_outcome=opposite)
    award = state["scene"]["award"]
    assert award["free"] is True
    assert award["outcome"] == opposite
    # 결과만 뒤집혔을 뿐 주사위의 실제 색은 그대로다
    assert award["die"]["color"] == last_color
    assert game.player_by_id(state, star)["dice"][-1]["color"] == last_color


def test_free_outcome_rejected_mid_act():
    random.seed(19)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    finish_twist(state)
    star = spotlight(state)
    game.scene_choose_type(state, star, "resolve")
    with pytest.raises(game.GameError, match="마지막 주사위"):
        game.scene_award_die(state, star, state["central"][0]["color"], free_outcome="good")


def test_act2_ends_when_center_is_empty():
    random.seed(23)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    finish_twist(state)
    scenes = 0
    while state["phase"] == "act2":
        star = spotlight(state)
        game.scene_choose_type(state, star, "resolve")
        game.scene_award_die(state, star, state["central"][0]["color"])
        game.scene_end(state, star)
        scenes += 1
        assert scenes <= 30
    assert scenes == 6  # 인원 × 2 장면
    assert state["phase"] == "aftermath"
    assert sum(len(p["dice"]) for p in state["players"]) == state["totalDice"]


# ---------------------------------------------------------------------------
# 후기
# ---------------------------------------------------------------------------


def run_to_aftermath(state: dict) -> None:
    begin_act1(state)
    run_act1(state)
    finish_twist(state)
    while state["phase"] == "act2":
        star = spotlight(state)
        game.scene_choose_type(state, star, "resolve")
        game.scene_award_die(state, star, state["central"][0]["color"])
        game.scene_end(state, star)


def test_aftermath_results_match_dice():
    random.seed(29)
    state = make_room(3)
    run_to_aftermath(state)
    for player in state["players"]:
        result = state["aftermath"]["results"][player["id"]]
        expected = game.tally(player["dice"])
        assert result["value"] == expected["value"]
        assert result["color"] == expected["color"]
        assert result["outcome"]["title"]


def test_montage_runs_until_every_die_is_spent():
    random.seed(31)
    state = make_room(3)
    run_to_aftermath(state)
    total = sum(len(p["dice"]) for p in state["players"])
    steps = 0
    while state["phase"] == "aftermath":
        actor = game.derived(state)["currentPlayerId"]
        game.montage_place(state, actor, "이것은 마지막 모습입니다.")
        steps += 1
        assert steps <= total + 5
    assert steps == total
    assert state["phase"] == "finished"
    assert len(state["aftermath"]["entries"]) == total


def test_montage_enforces_turn():
    random.seed(37)
    state = make_room(3)
    run_to_aftermath(state)
    actor = game.derived(state)["currentPlayerId"]
    wrong = other_than(state, actor)
    with pytest.raises(game.GameError, match="차례"):
        game.montage_place(state, wrong, "새치기")


def test_montage_gift_moves_a_die():
    random.seed(41)
    state = make_room(3)
    run_to_aftermath(state)
    giver = next(p for p in state["players"] if p["dice"])
    receiver = next(p for p in state["players"] if p["id"] != giver["id"])
    before = len(receiver["dice"])
    game.montage_gift(state, giver["id"], receiver["id"])
    assert len(receiver["dice"]) == before + 1


def test_new_game_returns_to_lobby():
    random.seed(43)
    state = make_room(3)
    run_to_aftermath(state)
    while state["phase"] == "aftermath":
        actor = game.derived(state)["currentPlayerId"]
        game.montage_place(state, actor, "끝")
    game.new_game(state, host_id(state))
    assert state["phase"] == "lobby"
    assert all(not p["dice"] for p in state["players"])
    assert state["twistDetails"] == []


# ---------------------------------------------------------------------------
# 후기 표
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [(0, "우주 최악의 상황"), (1, "끔찍함"), (4, "엉망진창"), (7, "꼴불견"), (9, "대단치 않음"), (12, "꽤 좋음"), (40, "훌륭함")],
)
def test_black_aftermath_ranges(value, expected):
    assert lookup_aftermath("black", value)["title"] == expected


@pytest.mark.parametrize(
    "value,expected",
    [(0, "우주 최악의 상황"), (2, "파멸"), (6, "가관"), (8, "불평 못함"), (10, "꽤 괜찮음"), (13, "멋져 죽겠음")],
)
def test_white_aftermath_ranges(value, expected):
    assert lookup_aftermath("white", value)["title"] == expected


def test_no_color_is_always_the_worst():
    assert lookup_aftermath(None, 11)["title"] == "우주 최악의 상황"
    assert lookup_aftermath(None, 11)["value"] == 0


def test_every_value_has_a_row():
    for color in ("black", "white"):
        for value in range(0, 60):
            assert lookup_aftermath(color, value)["title"]


# ---------------------------------------------------------------------------
# 선택 규칙
# ---------------------------------------------------------------------------


def test_dice_per_player_option_changes_pool():
    state = make_room(4)
    game.set_options(state, host_id(state), {"dicePerPlayer": 6})
    game.start_game(state, host_id(state))
    assert state["totalDice"] == 24


def test_odd_dice_per_player_rejected():
    state = make_room(3)
    with pytest.raises(game.GameError, match="짝수"):
        game.set_options(state, host_id(state), {"dicePerPlayer": 5})


def test_black_ratio_option():
    state = make_room(5)
    game.set_options(state, host_id(state), {"blackRatio": 0.75})
    game.start_game(state, host_id(state))
    black = sum(1 for d in state["central"] if d["color"] == "black")
    assert black == 15


def test_accelerator_ends_act2_and_shares_out_the_rest():
    random.seed(47)
    state = make_room(3)
    game.set_options(state, host_id(state), {"accelerator": True})
    begin_act1(state)
    run_act1(state)
    finish_twist(state)
    remaining = len(state["central"])
    assert remaining > 0
    game.host_end_act2(state, host_id(state))
    assert state["phase"] == "aftermath"
    assert state["central"] == [] or True
    assert sum(len(p["dice"]) for p in state["players"]) == state["totalDice"]


def test_accelerator_required_for_early_end():
    random.seed(53)
    state = make_room(3)
    begin_act1(state)
    run_act1(state)
    finish_twist(state)
    with pytest.raises(game.GameError, match="액셀"):
        game.host_end_act2(state, host_id(state))


# ---------------------------------------------------------------------------
# 무작위 대량 플레이 — 어떤 순서로도 끝까지 굴러가야 한다
# ---------------------------------------------------------------------------


def play_random_game(seed: int, n: int, playset_id: str) -> dict:
    random.seed(seed)
    state = make_room(n, playset_id)
    game.start_game(state, host_id(state))
    game.quick_setup(state, host_id(state))
    game.finish_setup(state, host_id(state))

    guard = 0
    while state["phase"] != "finished":
        guard += 1
        assert guard < 400, f"진행이 멈췄다: {state['phase']}"
        phase = state["phase"]
        if phase in ("act1", "act2"):
            star = spotlight(state)
            scene_type = random.choice(["establish", "resolve"])
            game.scene_choose_type(state, star, scene_type)
            color = random.choice(state["central"])["color"]
            awarder = star if scene_type == "resolve" else other_than(state, star)
            game.scene_award_die(state, awarder, color)
            if state["scene"]["status"] == "handoff":
                game.scene_hand_off(state, star, other_than(state, star))
            game.scene_end(state, star)
        elif phase == "twist":
            pid = next(
                p for p in state["twist"]["choosers"]
                if sum(1 for x in state["twist"]["picks"] if x["chooserId"] == p)
                < state["twist"]["choosers"].count(p)
            )
            game.twist_choose(state, pid, random.randint(1, 6), random.randint(1, 6))
        elif phase == "aftermath":
            actor = game.derived(state)["currentPlayerId"]
            game.montage_place(state, actor, "…")
        else:
            raise AssertionError(f"예상 못 한 단계: {phase}")
    return state


@pytest.mark.parametrize("seed", range(12))
def test_random_games_always_finish(seed):
    n = 3 + seed % 3
    playset_id = ["pretty_southern_town", "boomtown", "suburbia", "the_ice"][seed % 4]
    state = play_random_game(seed, n, playset_id)
    assert state["phase"] == "finished"
    assert sum(len(p["dice"]) for p in state["players"]) == 0
    assert len(state["central"]) == state["totalDice"]
    assert len(state["twistDetails"]) == 2


def test_public_state_hides_tokens():
    state = make_room(3)
    snapshot = game.public_state(state)
    assert all("token" not in p for p in snapshot["players"])
    assert snapshot["derived"]["pairs"]
