from datetime import date
import pytest

from app.schemas.weddle import (
    WeddleGuessRequest,
    WeddleGuessResponse,
    WeddlePlayer,
)
from app.services.weddle_service import WeddleService, format_height


def test_format_height():
    assert format_height(74) == "6'2\""
    assert format_height(70) == "5'10\""
    assert format_height(78) == "6'6\""


def test_target_selection_determinism():
    d1 = date(2026, 9, 11)
    target1 = WeddleService.select_daily_target(d1)
    target2 = WeddleService.select_daily_target(d1)
    assert target1.player_id == target2.player_id
    assert target1.full_name == target2.full_name

    # Different date produces deterministic target
    d2 = date(2026, 9, 12)
    target_d2 = WeddleService.select_daily_target(d2)
    assert target_d2.player_id is not None


def test_all_target_eligible_players_invariant():
    eligible = WeddleService.get_all_target_eligible_players()
    assert len(eligible) >= 30, "Active player pool must contain at least 30 qualified players"

    for p in eligible:
        assert p.player_id, "player_id must not be empty"
        assert p.full_name, "full_name must not be empty"
        assert p.team, f"team missing for {p.full_name}"
        assert p.position, f"position missing for {p.full_name}"
        assert p.side_of_ball in {"Offense", "Defense"}, f"invalid side_of_ball for {p.full_name}"
        assert p.conference in {"AFC", "NFC"}, f"invalid conference for {p.full_name}"
        assert p.division in {"East", "North", "South", "West"}, f"invalid division for {p.full_name}"
        assert p.age > 18 and p.age < 55, f"invalid age for {p.full_name}"
        assert p.height_inches >= 60 and p.height_inches <= 90, f"invalid height for {p.full_name}"
        assert p.jersey_number >= 0 and p.jersey_number <= 99, f"invalid jersey_number for {p.full_name}"
        assert p.height_formatted, "height_formatted must be populated"


def test_comparison_exact_match():
    mahomes = WeddleService.get_player("Patrick Mahomes")
    assert mahomes is not None

    res = WeddleService.evaluate_guess(target=mahomes, guessed=mahomes, previous_guesses=[])
    assert res.is_correct is True
    assert res.is_game_over is True
    assert res.guesses_remaining == 5
    assert res.revealed_target is not None
    assert res.revealed_target.player_id == mahomes.player_id

    attrs = res.comparison.attributes
    assert attrs.team.status == "green"
    assert attrs.position.status == "green"
    assert attrs.side_of_ball.status == "green"
    assert attrs.conference.status == "green"
    assert attrs.division.status == "green"
    assert attrs.age.status == "green"
    assert attrs.age.direction is None
    assert attrs.height.status == "green"
    assert attrs.height.direction is None
    assert attrs.jersey_number.status == "green"
    assert attrs.jersey_number.direction is None


def test_comparison_partial_and_directional():
    # Target: Patrick Mahomes (KC, Offense, QB, AFC, West, Age 28, 74", #15)
    # Guessed: Josh Allen (BUF, Offense, QB, AFC, East, Age 28, 77", #17)
    mahomes = WeddleService.get_player("Patrick Mahomes")
    allen = WeddleService.get_player("Josh Allen")
    assert mahomes is not None
    assert allen is not None

    res = WeddleService.evaluate_guess(target=mahomes, guessed=allen, previous_guesses=[])
    assert res.is_correct is False
    assert res.is_game_over is False
    assert res.guesses_remaining == 5
    assert res.revealed_target is None  # anti-cheat: hidden while active

    attrs = res.comparison.attributes
    assert attrs.team.status == "gray"  # BUF vs KC
    assert attrs.side_of_ball.status == "green"  # Both Offense
    assert attrs.position.status == "green"  # Both QB
    assert attrs.conference.status == "green"  # Both AFC
    assert attrs.division.status == "gray"  # East vs West
    assert attrs.age.status == "green"  # Both 28
    assert attrs.age.direction is None

    # Height: Target 74", Guessed 77" -> Target is shorter (74 < 77) -> direction "lower"
    # diff = 3 -> status "gray" (> 2)
    assert attrs.height.status == "gray"
    assert attrs.height.direction == "lower"

    # Jersey: Target 15, Guessed 17 -> Target is lower (15 < 17) -> direction "lower"
    # diff = 2 -> status "yellow" (<= 2)
    assert attrs.jersey_number.status == "yellow"
    assert attrs.jersey_number.direction == "lower"


def test_positional_subgroups_yellow():
    # Cornerback vs Safety -> DB subgroup (Yellow)
    assert WeddleService.is_same_position_group("CB", "S") is True
    assert WeddleService.is_same_position_group("CB", "FS") is True
    # Offensive Tackle vs Center -> OL subgroup (Yellow)
    assert WeddleService.is_same_position_group("OT", "C") is True
    assert WeddleService.is_same_position_group("OG", "C") is True
    # Defensive End vs Defensive Tackle -> DL/EDGE subgroup (Yellow)
    assert WeddleService.is_same_position_group("DE", "DT") is True
    # WR vs TE -> Pass Catchers subgroup (Yellow)
    assert WeddleService.is_same_position_group("WR", "TE") is True
    # RB vs FB -> Backfield subgroup (Yellow)
    assert WeddleService.is_same_position_group("RB", "FB") is True
    # QB vs WR -> Different subgroups (Gray)
    assert WeddleService.is_same_position_group("QB", "WR") is False


def test_game_over_loss_reveals_target():
    mahomes = WeddleService.get_player("Patrick Mahomes")
    allen = WeddleService.get_player("Josh Allen")

    # 5 previous guesses already made -> 6th guess exhausts budget
    prev_guesses = ["id1", "id2", "id3", "id4", "id5"]
    res = WeddleService.evaluate_guess(target=mahomes, guessed=allen, previous_guesses=prev_guesses)

    assert res.is_correct is False
    assert res.guesses_remaining == 0
    assert res.is_game_over is True
    assert res.revealed_target is not None
    assert res.revealed_target.player_id == mahomes.player_id


def test_2026_preseason_player_moves():
    """
    Verifies 2026 preseason player moves and trade assignments:
    - A.J. Brown: New England Patriots (NE), #1
    - Myles Garrett: Los Angeles Rams (LAR), #95
    - Cooper Kupp: Seattle Seahawks (SEA), #10
    - Daniel Jones: Indianapolis Colts (IND), #17
    - Drake Maye: New England Patriots (NE), #10
    """
    aj = WeddleService.get_player("A.J. Brown")
    assert aj is not None
    assert aj.team in ("NE", "NWE"), f"Expected A.J. Brown to be on NE, got {aj.team}"
    assert aj.conference == "AFC"
    assert aj.division == "East"
    assert aj.jersey_number == 1, f"Expected A.J. Brown to wear #1, got #{aj.jersey_number}"

    mg = WeddleService.get_player("Myles Garrett")
    assert mg is not None
    assert mg.team in ("LAR", "LA"), f"Expected Myles Garrett to be on LAR, got {mg.team}"
    assert mg.conference == "NFC"
    assert mg.division == "West"
    assert mg.jersey_number == 95

    kupp = WeddleService.get_player("Cooper Kupp")
    assert kupp is not None
    assert kupp.team == "SEA", f"Expected Cooper Kupp to be on SEA, got {kupp.team}"
    assert kupp.conference == "NFC"
    assert kupp.division == "West"
    assert kupp.jersey_number == 10

    dj = WeddleService.get_player("Daniel Jones")
    assert dj is not None
    assert dj.team == "IND"
    assert dj.jersey_number == 17

    maye = WeddleService.get_player("Drake Maye")
    assert maye is not None
    assert maye.team in ("NE", "NWE")
    assert maye.jersey_number == 10

