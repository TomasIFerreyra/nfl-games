"""
Unit Tests and Verification Suite for NFL Top 10 Leaderboard Engine.
Tests:
1. Category Taxonomy, Archetypes & Recency Guardrails (Draft post-2015, Single-Season post-2010).
2. Ranking Resolution & Strict Tie-Breaking Invariants.
3. Deterministic Daily Generator Seeding & Archetype Family Rotation.
4. Guess Validation Engine (O(1) Direct ID, Tied ID, Name Normalization, Deduplication).
5. FastAPI REST API Endpoints & RFC 7807 Error Handling.
"""

from datetime import date, timedelta
import json
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, Integer, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.db.base import Base
from app.db.models.player import Player
from app.db.models.puzzle import DailyPuzzle
from app.db.models.stats import Accolade, PlayerCareerStat, PlayerSeasonStat
from app.db.session import get_async_session
from app.domain.top10_generator import Top10Generator
from app.domain.top10_taxonomy import (
    Top10Archetype,
    Top10CategoryDefinition,
    resolve_category_leaderboard,
    top10_registry,
)
from app.domain.top10_validator import Top10Validator
from app.main import app
from app.schemas.top10 import Top10Entry


# Register SQLite compilations for PostgreSQL specific types
@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


@compiles(BigInteger, "sqlite")
def compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


@pytest_asyncio.fixture
async def db_session_factory():
    """Provides an isolated in-memory SQLite database for async testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_db_session(db_session_factory):
    """Populates test database with players, stats, and awards."""
    async with db_session_factory() as session:
        # Seed players
        players_data = [
            Player(player_id="p-mahomes-pat01", gsis_id="00-0033873", full_name="Patrick Mahomes", first_name="Patrick", last_name="Mahomes", primary_position="QB", rookie_year=2017, draft_year=2017, draft_overall=10, is_active=True),
            Player(player_id="p-jackson-lam01", gsis_id="00-0034796", full_name="Lamar Jackson", first_name="Lamar", last_name="Jackson", primary_position="QB", rookie_year=2018, draft_year=2018, draft_overall=32, is_active=True),
            Player(player_id="p-burrow-joe01", gsis_id="00-0036442", full_name="Joe Burrow", first_name="Joe", last_name="Burrow", primary_position="QB", rookie_year=2020, draft_year=2020, draft_overall=1, is_active=True),
            Player(player_id="p-stroud-cj01", gsis_id="00-0039163", full_name="C.J. Stroud", first_name="C.J.", last_name="Stroud", primary_position="QB", rookie_year=2023, draft_year=2023, draft_overall=2, is_active=True),
            Player(player_id="p-watt-tj01", gsis_id="00-0033882", full_name="T.J. Watt", first_name="T.J.", last_name="Watt", primary_position="DE", rookie_year=2017, draft_year=2017, draft_overall=30, is_active=True),
            Player(player_id="p-smith-bru01", gsis_id="p-smith-bru01", full_name="Bruce Smith", first_name="Bruce", last_name="Smith", primary_position="DE", rookie_year=1985, final_year=2003, draft_year=1985, draft_overall=1, is_active=False),
            Player(player_id="p-white-reg01", gsis_id="p-white-reg01", full_name="Reggie White", first_name="Reggie", last_name="White", primary_position="DE", rookie_year=1985, final_year=2000, draft_year=1984, draft_overall=4, is_active=False),
        ]
        session.add_all(players_data)

        # Seed awards
        accolades = [
            Accolade(player_id="p-jackson-lam01", season_year=2023, accolade_type="MVP"),
            Accolade(player_id="p-mahomes-pat01", season_year=2022, accolade_type="MVP"),
            Accolade(player_id="p-mahomes-pat01", season_year=2018, accolade_type="MVP"),
            Accolade(player_id="p-stroud-cj01", season_year=2023, accolade_type="OROY"),
        ]
        session.add_all(accolades)

        # Seed career stats
        career_stats = [
            PlayerCareerStat(player_id="p-smith-bru01", seasons_played=19, games_played=279, sacks=200.0),
            PlayerCareerStat(player_id="p-white-reg01", seasons_played=15, games_played=232, sacks=198.0),
        ]
        session.add_all(career_stats)

        await session.commit()
        yield session


# =============================================================================
# 1. TAXONOMY & ERA GUARDRAILS TESTS
# =============================================================================

def test_taxonomy_archetype_coverage():
    """Verifies that all 4 archetype categories exist in the registry."""
    categories = top10_registry.get_all()
    assert len(categories) >= 8

    archetypes_found = {c.archetype for c in categories}
    assert Top10Archetype.SINGLE_SEASON_MILESTONE in archetypes_found
    assert Top10Archetype.CHRONOLOGICAL_ACCOLADE in archetypes_found
    assert Top10Archetype.RECENT_DRAFT_PEDIGREE in archetypes_found
    assert Top10Archetype.ALL_TIME_HISTORICAL_LEADERBOARD in archetypes_found


def test_recency_guardrails_on_draft_and_single_season():
    """Enforces that draft queries are strictly post-2015 and seasonal queries post-2010."""
    draft_cats = top10_registry.get_by_archetype(Top10Archetype.RECENT_DRAFT_PEDIGREE)
    for cat in draft_cats:
        draft_year = cat.parameters.get("draft_year")
        assert draft_year is not None and draft_year >= 2015, f"Draft category {cat.category_id} violates 2015+ guardrail."

    season_cats = top10_registry.get_by_archetype(Top10Archetype.SINGLE_SEASON_MILESTONE)
    for cat in season_cats:
        min_year = cat.min_season_year or cat.parameters.get("year") or cat.parameters.get("min_year")
        assert min_year is not None and min_year >= 2010, f"Single-season category {cat.category_id} violates 2010+ guardrail."


# =============================================================================
# 2. DETERMINISTIC GENERATOR & ARCHETYPE ROTATION TESTS
# =============================================================================

def test_generator_deterministic_seeding():
    """Verifies that the same calendar date always produces the exact same category."""
    test_date = date(2026, 9, 15)
    cat1 = Top10Generator.select_category_for_date(test_date)
    cat2 = Top10Generator.select_category_for_date(test_date)
    assert cat1.category_id == cat2.category_id


def test_generator_archetype_rotation_across_consecutive_days():
    """Verifies that adjacent calendar dates never share the same archetype family."""
    base_date = date(2026, 9, 1)
    archetypes = [
        Top10Generator.select_category_for_date(base_date + timedelta(days=i)).archetype
        for i in range(7)
    ]
    for i in range(len(archetypes) - 1):
        assert archetypes[i] != archetypes[i + 1], f"Day {i} and Day {i+1} share archetype {archetypes[i]}!"


@pytest.mark.asyncio
async def test_top10_generation_and_publishing(seeded_db_session: AsyncSession):
    """Verifies generation, hashing, and database persistence of a daily Top 10 puzzle."""
    test_date = date(2026, 9, 20)
    puzzle_data = await Top10Generator.generate_and_publish_daily_puzzle(
        session=seeded_db_session,
        target_date=test_date,
        puzzle_number=42,
    )

    assert puzzle_data["slots_count"] == 10
    assert len(puzzle_data["leaderboard"]) == 10
    assert puzzle_data["leaderboard"][0]["rank"] == 1
    assert puzzle_data["leaderboard"][9]["rank"] == 10

    # Query daily_puzzles table to ensure persistence
    stmt = select(DailyPuzzle).where(
        DailyPuzzle.target_date == test_date,
        DailyPuzzle.game_type == "TOP10",
    )
    saved = (await seeded_db_session.execute(stmt)).scalar_one_or_none()
    assert saved is not None
    assert saved.puzzle_number == 42
    assert len(saved.solution_hash) == 64


# =============================================================================
# 3. TIE-BREAKING & RANKING INVARIANTS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_tie_breaking_and_tied_player_ids(seeded_db_session: AsyncSession):
    """Verifies that tied players are mapped to tied_player_ids and evaluated as hits."""
    category = top10_registry.get("TOP10_PASS_TD_2020S")
    assert category is not None

    leaderboard = await resolve_category_leaderboard(seeded_db_session, category)
    assert len(leaderboard) == 10

    # Test fallback data has tied players recognized properly
    sample_puzzle_data = {
        "leaderboard": [
            {
                "rank": 1,
                "player_id": "p-mahomes-pat01",
                "player_name": "Patrick Mahomes",
                "metric_value": 41.0,
                "formatted_value": "41 TDs",
                "tied_player_ids": ["p-stafford-mat01"],
            },
            {
                "rank": 2,
                "player_id": "p-stafford-mat01",
                "player_name": "Matthew Stafford",
                "metric_value": 41.0,
                "formatted_value": "41 TDs",
                "tied_player_ids": ["p-mahomes-pat01"],
            },
        ]
    }

    # Guessing Stafford matches tied rank
    is_hit, entry, is_rep, strikes, reason = Top10Validator.evaluate_guess(
        puzzle_data=sample_puzzle_data,
        player_id="p-stafford-mat01",
    )
    assert is_hit is True
    assert strikes == 0


# =============================================================================
# 4. GUESS VALIDATION TESTS
# =============================================================================

def test_validator_direct_hit():
    puzzle_data = {
        "leaderboard": [
            {"rank": 1, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 41.0, "formatted_value": "41 TDs"},
            {"rank": 2, "player_id": "00-0034796", "player_name": "Lamar Jackson", "metric_value": 36.0, "formatted_value": "36 TDs"},
        ]
    }

    is_hit, entry, is_rep, strikes, reason = Top10Validator.evaluate_guess(
        puzzle_data=puzzle_data,
        player_id="00-0033873",
    )
    assert is_hit is True
    assert entry["rank"] == 1
    assert strikes == 0
    assert not is_rep


def test_validator_name_normalization_hit():
    """Verifies that punctuation variations like 'T.J. Watt' vs 'TJ Watt' evaluate as hits."""
    puzzle_data = {
        "leaderboard": [
            {"rank": 1, "player_id": "00-0033882", "player_name": "T.J. Watt", "metric_value": 22.5, "formatted_value": "22.5 Sacks"},
        ]
    }

    is_hit, entry, is_rep, strikes, reason = Top10Validator.evaluate_guess(
        puzzle_data=puzzle_data,
        player_id="tj watt",
    )
    assert is_hit is True
    assert entry["rank"] == 1
    assert strikes == 0


def test_validator_miss_adds_strike():
    puzzle_data = {
        "leaderboard": [
            {"rank": 1, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 41.0, "formatted_value": "41 TDs"},
        ]
    }

    is_hit, entry, is_rep, strikes, reason = Top10Validator.evaluate_guess(
        puzzle_data=puzzle_data,
        player_id="unknown-player-id",
    )
    assert is_hit is False
    assert entry is None
    assert strikes == 1
    assert not is_rep


def test_validator_repeated_guess_deduplication():
    """Verifies that repeated submissions in a session do not burn a strike."""
    puzzle_data = {
        "leaderboard": [
            {"rank": 1, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 41.0, "formatted_value": "41 TDs"},
        ]
    }

    is_hit, entry, is_rep, strikes, reason = Top10Validator.evaluate_guess(
        puzzle_data=puzzle_data,
        player_id="00-0033873",
        previous_guesses=["00-0033873"],
    )
    assert is_hit is False
    assert is_rep is True
    assert strikes == 0
    assert "already been submitted" in reason


# =============================================================================
# 5. FASTAPI REST API ENDPOINTS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_fastapi_top10_guess_endpoint(db_session_factory):
    """Tests POST /api/v1/top10/guess endpoint via httpx AsyncClient."""
    async with db_session_factory() as session:
        # Create a test TOP10 puzzle
        puzzle_id = uuid.uuid4()
        test_puzzle_data = {
            "category_id": "TOP10_LAST_MVPS",
            "title": "Last 10 AP NFL Regular Season MVPs",
            "metric_label": "MVP Season",
            "slots_count": 10,
            "leaderboard": [
                {"rank": 1, "player_id": "00-0034796", "player_name": "Lamar Jackson", "metric_value": 2023.0, "formatted_value": "2023 MVP (BAL)"},
                {"rank": 2, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 2022.0, "formatted_value": "2022 MVP (KC)"},
                {"rank": 3, "player_id": "00-0023459", "player_name": "Aaron Rodgers", "metric_value": 2021.0, "formatted_value": "2021 MVP (GB)"},
            ],
        }

        puzzle = DailyPuzzle(
            puzzle_id=puzzle_id,
            target_date=date(2026, 9, 25),
            game_type="TOP10",
            puzzle_number=100,
            puzzle_data=test_puzzle_data,
            solution_hash="test-hash-top10-001",
        )
        session.add(puzzle)
        await session.commit()

        # Dependency override for session
        app.dependency_overrides[get_async_session] = lambda: session

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Correct Guess Hit
            hit_res = await client.post(
                "/api/v1/top10/guess",
                json={"puzzle_id": str(puzzle_id), "player_id": "00-0034796"},
            )
            assert hit_res.status_code == 200
            hit_json = hit_res.json()
            assert hit_json["is_hit"] is True
            assert hit_json["entry"]["rank"] == 1
            assert hit_json["strikes_added"] == 0

            # 2. Incorrect Guess Miss
            miss_res = await client.post(
                "/api/v1/top10/guess",
                json={"puzzle_id": str(puzzle_id), "player_id": "unknown-non-mvp"},
            )
            assert miss_res.status_code == 200
            miss_json = miss_res.json()
            assert miss_json["is_hit"] is False
            assert miss_json["strikes_added"] == 1

            # 3. Repeated Guess
            rep_res = await client.post(
                "/api/v1/top10/guess",
                json={
                    "puzzle_id": str(puzzle_id),
                    "player_id": "00-0034796",
                    "previous_guesses": ["00-0034796"],
                },
            )
            assert rep_res.status_code == 200
            rep_json = rep_res.json()
            assert rep_json["is_repeated"] is True
            assert rep_json["strikes_added"] == 0

            # 4. Missing Puzzle 404
            missing_res = await client.post(
                "/api/v1/top10/guess",
                json={"puzzle_id": str(uuid.uuid4()), "player_id": "00-0034796"},
            )
            assert missing_res.status_code == 404

            # 5. Empty Player ID 422
            empty_res = await client.post(
                "/api/v1/top10/guess",
                json={"puzzle_id": str(puzzle_id), "player_id": "   "},
            )
            assert empty_res.status_code == 422

        app.dependency_overrides.clear()
