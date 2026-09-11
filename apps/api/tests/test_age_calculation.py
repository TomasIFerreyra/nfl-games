from datetime import date
import pytest

from app.db.models.player import Player
from app.schemas.weddle import AttributeComparison, WeddlePlayer
from app.services.weddle_service import WeddleService, compute_player_age


def test_compute_player_age_basic():
    # Born 2000-01-01
    dob = date(2000, 1, 1)
    assert compute_player_age(dob, reference_date=date(2026, 1, 1)) == 26
    assert compute_player_age(dob, reference_date=date(2026, 6, 15)) == 26
    assert compute_player_age(dob, reference_date=date(2025, 12, 31)) == 25


def test_aj_brown_evaluates_to_29():
    """
    Direct requirement test: A.J. Brown (born June 30, 1997) must dynamically
    evaluate to 29 years old on 2026-09-11 instead of stale static integer 27.
    """
    aj_dob = date(1997, 6, 30)
    eval_date = date(2026, 9, 11)
    age = compute_player_age(aj_dob, reference_date=eval_date)
    assert age == 29

    # Test via WeddleService catalog
    aj_player = WeddleService.get_player("A.J. Brown")
    assert aj_player is not None
    assert aj_player.birth_date == aj_dob
    assert aj_player.age == 29


def test_birthday_today_vs_tomorrow_vs_yesterday():
    dob = date(1996, 9, 11)

    # 1. Birthday Today: turns 30 today on 2026-09-11
    assert compute_player_age(dob, reference_date=date(2026, 9, 11)) == 30

    # 2. Birthday Tomorrow: still 29 on 2026-09-10
    assert compute_player_age(dob, reference_date=date(2026, 9, 10)) == 29

    # 3. Birthday Yesterday: was 30 on 2026-09-12
    assert compute_player_age(dob, reference_date=date(2026, 9, 12)) == 30


def test_leap_year_born_feb_29():
    """
    Tests edge cases for players born on leap day (Feb 29).
    """
    leap_dob = date(2000, 2, 29)

    # In non-leap year 2025:
    # On Feb 28, 2025: not yet reached March -> 24 years old
    assert compute_player_age(leap_dob, reference_date=date(2025, 2, 28)) == 24
    # On Mar 1, 2025: month 3 > month 2 -> 25 years old
    assert compute_player_age(leap_dob, reference_date=date(2025, 3, 1)) == 25

    # In leap year 2024:
    # On Feb 28, 2024 -> 23 years old
    assert compute_player_age(leap_dob, reference_date=date(2024, 2, 28)) == 23
    # On Feb 29, 2024 (exact 24th birthday) -> 24 years old
    assert compute_player_age(leap_dob, reference_date=date(2024, 2, 29)) == 24
    # On Mar 1, 2024 -> 24 years old
    assert compute_player_age(leap_dob, reference_date=date(2024, 3, 1)) == 24


def test_player_model_hybrid_property():
    player_with_dob = Player(
        player_id="test-1",
        full_name="Test Player",
        first_name="Test",
        last_name="Player",
        primary_position="QB",
        rookie_year=2020,
        birth_date=date(1997, 6, 30),
    )
    assert player_with_dob.current_age == 29
    assert player_with_dob.age == 29

    player_no_dob = Player(
        player_id="test-2",
        full_name="Unknown DOB",
        first_name="Unknown",
        last_name="DOB",
        primary_position="WR",
        rookie_year=2020,
        birth_date=None,
    )
    assert player_with_dob.current_age == 29
    assert player_no_dob.current_age is None
    assert player_no_dob.age is None


def test_weddle_age_distance_comparisons():
    def make_player(name: str, age: int) -> WeddlePlayer:
        return WeddlePlayer(
            player_id=f"id-{name}",
            full_name=name,
            team="KC",
            side_of_ball="Offense",
            position="QB",
            conference="AFC",
            division="West",
            age=age,
            height_inches=74,
            height_formatted="6'2\"",
            jersey_number=15,
        )

    target_player = make_player("Target", 28)

    # 1. Exact match (diff = 0) -> green, None
    guess_exact = make_player("Exact", 28)
    comp = WeddleService.compare_attributes(target_player, guess_exact)
    assert comp.age.status == "green"
    assert comp.age.direction is None

    # 2. Within +1 year (Target 28, Guess 27) -> yellow, "higher"
    guess_minus_1 = make_player("Minus1", 27)
    comp = WeddleService.compare_attributes(target_player, guess_minus_1)
    assert comp.age.status == "yellow"
    assert comp.age.direction == "higher"

    # 3. Within +2 years (Target 28, Guess 26) -> yellow, "higher"
    guess_minus_2 = make_player("Minus2", 26)
    comp = WeddleService.compare_attributes(target_player, guess_minus_2)
    assert comp.age.status == "yellow"
    assert comp.age.direction == "higher"

    # 4. Beyond +2 years (Target 28, Guess 25, diff = 3) -> gray, "higher"
    guess_minus_3 = make_player("Minus3", 25)
    comp = WeddleService.compare_attributes(target_player, guess_minus_3)
    assert comp.age.status == "gray"
    assert comp.age.direction == "higher"

    # 5. Within -1 year (Target 28, Guess 29) -> yellow, "lower"
    guess_plus_1 = make_player("Plus1", 29)
    comp = WeddleService.compare_attributes(target_player, guess_plus_1)
    assert comp.age.status == "yellow"
    assert comp.age.direction == "lower"

    # 6. Within -2 years (Target 28, Guess 30) -> yellow, "lower"
    guess_plus_2 = make_player("Plus2", 30)
    comp = WeddleService.compare_attributes(target_player, guess_plus_2)
    assert comp.age.status == "yellow"
    assert comp.age.direction == "lower"

    # 7. Beyond -2 years (Target 28, Guess 32, diff = 4) -> gray, "lower"
    guess_plus_4 = make_player("Plus4", 32)
    comp = WeddleService.compare_attributes(target_player, guess_plus_4)
    assert comp.age.status == "gray"
    assert comp.age.direction == "lower"
