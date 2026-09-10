"""
Unit Tests and Performance Benchmarks for NFL Connections 4x4 Engine.
Tests:
1. Knuth's Algorithm X Exact Cover Solver & Uniqueness Verifier (Bitset + DLX).
2. Category Taxonomy & Tier Classification (Tier 1 Bronze -> Tier 4 Platinum).
3. Daily Connections Generator Orchestrator & Deterministic Seeding.
4. Validation API & RFC 7807 Error Handling.
5. Exact Cover Execution Benchmarks (< 1ms per board).
"""

from datetime import date
import json
import time
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, Integer, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.db.base import Base
from app.db.models.franchise import Franchise, TeamSeason
from app.db.models.player import Player, PlayerTeamStint
from app.db.models.puzzle import DailyPuzzle
from app.db.models.stats import Accolade, PlayerCareerStat, PlayerSeasonStat
from app.db.session import get_async_session
from app.domain.connections_taxonomy import (
    ConnectionsCategoryDefinition,
    ConnectionsTier,
    connections_registry,
)
from app.domain.connections_validator import ConnectionsValidator
from app.domain.exact_cover_validator import (
    DancingLinks,
    ExactCoverValidator,
)
from app.main import app
from packages.etl.generator.connections_generator import ConnectionsGenerator


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
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_maker
    await engine.dispose()


@pytest_asyncio.fixture
async def session(db_session_factory):
    async with db_session_factory() as s:
        yield s


# =====================================================================
# 1. Knuth's Algorithm X & Dancing Links Tests
# =====================================================================
def test_dlx_exact_cover_basic():
    """Verifies that Dancing Links (DLX) finds exact covers on a matrix."""
    columns = ["c1", "c2", "c3", "c4"]
    dlx = DancingLinks(columns)
    # Row 0 covers c1, c2
    dlx.add_row(0, ["c1", "c2"])
    # Row 1 covers c3, c4
    dlx.add_row(1, ["c3", "c4"])
    # Row 2 covers c2, c3
    dlx.add_row(2, ["c2", "c3"])

    solutions = dlx.solve()
    assert len(solutions) == 1
    assert sorted(solutions[0]) == [0, 1]


def test_algorithm_x_unique_partition():
    """Tests Algorithm X uniqueness on a strictly valid 16-player board."""
    items = [f"p{i}" for i in range(16)]
    g1 = {"p0", "p1", "p2", "p3"}
    g2 = {"p4", "p5", "p6", "p7"}
    g3 = {"p8", "p9", "p10", "p11"}
    g4 = {"p12", "p13", "p14", "p15"}

    # Pools that contain each group
    pools = {
        "cat_1": g1,
        "cat_2": g2,
        "cat_3": g3,
        "cat_4": g4,
    }

    result = ExactCoverValidator.validate_puzzle_uniqueness(
        item_ids=items,
        category_player_pools=pools,
        target_groups=[g1, g2, g3, g4],
    )

    assert result.is_unique is True
    assert result.solution_count == 1
    assert result.rejection_reason is None


def test_algorithm_x_ambiguous_distractor_partition_rejection():
    """
    Tests Algorithm X rejects boards where distractors introduce an alternate valid 4x4 partition.
    Suppose p0, p1, p2, p3 is cat1 and p4, p5, p6, p7 is cat2, but {p0, p1, p4, p5} is cat5 and {p2, p3, p6, p7} is cat6.
    Then there are TWO valid disjoint covers: (cat1, cat2, cat3, cat4) AND (cat5, cat6, cat3, cat4).
    """
    items = [f"p{i}" for i in range(16)]
    g1 = {"p0", "p1", "p2", "p3"}
    g2 = {"p4", "p5", "p6", "p7"}
    g3 = {"p8", "p9", "p10", "p11"}
    g4 = {"p12", "p13", "p14", "p15"}

    # Distractor groups creating alternative partition
    alt_g1 = {"p0", "p1", "p4", "p5"}
    alt_g2 = {"p2", "p3", "p6", "p7"}

    pools = {
        "cat_1": g1,
        "cat_2": g2,
        "cat_3": g3,
        "cat_4": g4,
        "cat_alt_1": alt_g1,
        "cat_alt_2": alt_g2,
    }

    result = ExactCoverValidator.validate_puzzle_uniqueness(
        item_ids=items,
        category_player_pools=pools,
        target_groups=[g1, g2, g3, g4],
    )

    assert result.is_unique is False
    assert result.solution_count == 2
    assert "Ambiguous board" in result.rejection_reason


def test_algorithm_x_unsolvable_rejection():
    """Tests Algorithm X rejects boards with no valid partition."""
    items = [f"p{i}" for i in range(16)]
    pools = {
        "cat_1": {"p0", "p1", "p2", "p3"},
        "cat_2": {"p4", "p5", "p6", "p7"},
        "cat_3": {"p8", "p9", "p10", "p11"},
    }

    result = ExactCoverValidator.validate_puzzle_uniqueness(
        item_ids=items,
        category_player_pools=pools,
    )

    assert result.is_unique is False
    assert result.solution_count == 0
    assert "No valid 4x4 exact cover partition" in result.rejection_reason


def test_algorithm_x_performance_benchmark():
    """
    Benchmark: Runs Exact Cover verification across 200 board evaluations.
    Asserts average solve time is strictly < 2.0ms per board.
    """
    items = [f"p{i}" for i in range(16)]
    g1 = {"p0", "p1", "p2", "p3"}
    g2 = {"p4", "p5", "p6", "p7"}
    g3 = {"p8", "p9", "p10", "p11"}
    g4 = {"p12", "p13", "p14", "p15"}
    pools = {"cat_1": g1, "cat_2": g2, "cat_3": g3, "cat_4": g4}

    iterations = 200
    start = time.perf_counter()
    for _ in range(iterations):
        res = ExactCoverValidator.validate_puzzle_uniqueness(
            item_ids=items,
            category_player_pools=pools,
        )
        assert res.is_unique is True
    total_elapsed_ms = (time.perf_counter() - start) * 1000
    avg_solve_ms = total_elapsed_ms / iterations

    print(f"\n[BENCHMARK] Algorithm X Exact Cover: {avg_solve_ms:.4f}ms per board ({iterations} iterations)")
    assert avg_solve_ms < 2.0, f"Algorithm X benchmark too slow: {avg_solve_ms:.4f}ms"


# =====================================================================
# 2. Connections Taxonomy & Tier Tests
# =====================================================================
def test_taxonomy_tiers_coverage():
    """Verifies that the taxonomy contains categories across all 4 tiers."""
    all_cats = connections_registry.get_all_categories(active_only=True)
    assert len(all_cats) >= 30

    t1 = connections_registry.get_categories_by_tier(ConnectionsTier.BRONZE)
    t2 = connections_registry.get_categories_by_tier(ConnectionsTier.SILVER)
    t3 = connections_registry.get_categories_by_tier(ConnectionsTier.GOLD)
    t4 = connections_registry.get_categories_by_tier(ConnectionsTier.PLATINUM)

    assert len(t1) >= 5, "Tier 1 (Bronze) has insufficient categories."
    assert len(t2) >= 5, "Tier 2 (Silver) has insufficient categories."
    assert len(t3) >= 5, "Tier 3 (Gold) has insufficient categories."
    assert len(t4) >= 5, "Tier 4 (Platinum) has insufficient categories."


@pytest.mark.asyncio
async def test_taxonomy_sql_resolver(session: AsyncSession):
    """Verifies SQL resolver methods against database entities."""
    # Seed test players
    p1 = Player(player_id="p-bama-1", full_name="Bama Star 1", first_name="Bama", last_name="Star1", college="Alabama", primary_position="QB", rookie_year=2020)
    p2 = Player(player_id="p-bama-2", full_name="Bama Star 2", first_name="Bama", last_name="Star2", college="Alabama", primary_position="RB", rookie_year=2021)
    p3 = Player(player_id="p-bama-3", full_name="Bama Star 3", first_name="Bama", last_name="Star3", college="Alabama", primary_position="WR", rookie_year=2022)
    p4 = Player(player_id="p-bama-4", full_name="Bama Star 4", first_name="Bama", last_name="Star4", college="Alabama", primary_position="DB", rookie_year=2023)

    session.add_all([p1, p2, p3, p4])
    await session.commit()

    cat_bama = connections_registry.get_category("COLLEGE_ALABAMA")
    assert cat_bama is not None

    resolved = await connections_registry.resolve_player_pool(cat_bama, session)
    resolved_ids = {p.player_id for p in resolved}
    assert {"p-bama-1", "p-bama-2", "p-bama-3", "p-bama-4"}.issubset(resolved_ids)


# =====================================================================
# 3. Connections Generator & Determinism Tests
# =====================================================================
@pytest.mark.asyncio
async def test_connections_generator_deterministic(session: AsyncSession):
    """Verifies that identical dates yield identical puzzles via seeded RNG."""
    target_date = date(2026, 9, 25)
    puzzle1 = await ConnectionsGenerator.generate_puzzle_data(session, target_date, puzzle_number=100)
    puzzle2 = await ConnectionsGenerator.generate_puzzle_data(session, target_date, puzzle_number=100)

    hash1 = ConnectionsGenerator.compute_solution_hash(puzzle1)
    hash2 = ConnectionsGenerator.compute_solution_hash(puzzle2)

    assert hash1 == hash2
    assert len(puzzle1["items"]) == 16
    assert len(puzzle1["groups"]) == 4

    tiers = [g["tier"] for g in puzzle1["groups"]]
    assert sorted(tiers) == [1, 2, 3, 4]


# =====================================================================
# 4. Validation Engine & API Router Tests
# =====================================================================
def test_connections_validator_exact_match_and_one_away():
    """Verifies domain validator correctly handles exact matches and 3-overlap one-aways."""
    puzzle_data = {
        "items": [
            {"item_id": f"i{i}", "display_text": f"Player {i}"} for i in range(1, 17)
        ],
        "groups": [
            {
                "group_id": "grp1",
                "tier": 1,
                "title": "Group 1",
                "item_ids": ["i1", "i2", "i3", "i4"],
                "explanation": "Group 1 explanation",
            },
            {
                "group_id": "grp2",
                "tier": 2,
                "title": "Group 2",
                "item_ids": ["i5", "i6", "i7", "i8"],
                "explanation": "Group 2 explanation",
            },
        ],
    }

    # 1. Exact Match
    is_match, group, is_one_away, count = ConnectionsValidator.validate_group(
        puzzle_data, ["i1", "i2", "i3", "i4"]
    )
    assert is_match is True
    assert group is not None
    assert group["group_id"] == "grp1"
    assert is_one_away is False
    assert count == 4

    # 2. One Away (3 items match group 1)
    is_match, group, is_one_away, count = ConnectionsValidator.validate_group(
        puzzle_data, ["i1", "i2", "i3", "i5"]
    )
    assert is_match is False
    assert group is None
    assert is_one_away is True
    assert count == 3

    # 3. Two Overlap (not one away)
    is_match, group, is_one_away, count = ConnectionsValidator.validate_group(
        puzzle_data, ["i1", "i2", "i5", "i6"]
    )
    assert is_match is False
    assert group is None
    assert is_one_away is False
    assert count == 2


@pytest.mark.asyncio
async def test_fastapi_connections_validate_endpoint(session: AsyncSession):
    """Tests FastAPI /api/v1/connections/validate-group with RFC 7807 problem details."""
    app.dependency_overrides[get_async_session] = lambda: session

    # Seed a daily puzzle
    p_uuid = uuid.uuid4()
    p_data = {
        "items": [{"item_id": f"p{i}", "display_text": f"Player {i}"} for i in range(16)],
        "groups": [
            {"group_id": "g1", "tier": 1, "title": "Tier 1 Title", "item_ids": ["p0", "p1", "p2", "p3"], "explanation": "Tier 1 Expl"},
            {"group_id": "g2", "tier": 2, "title": "Tier 2 Title", "item_ids": ["p4", "p5", "p6", "p7"], "explanation": "Tier 2 Expl"},
            {"group_id": "g3", "tier": 3, "title": "Tier 3 Title", "item_ids": ["p8", "p9", "p10", "p11"], "explanation": "Tier 3 Expl"},
            {"group_id": "g4", "tier": 4, "title": "Tier 4 Title", "item_ids": ["p12", "p13", "p14", "p15"], "explanation": "Tier 4 Expl"},
        ],
    }
    db_puzzle = DailyPuzzle(
        puzzle_id=p_uuid,
        target_date=date(2026, 9, 26),
        game_type="CONNECTIONS",
        puzzle_number=50,
        puzzle_data=p_data,
        solution_hash="test_hash_conn",
    )
    session.add(db_puzzle)
    await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Correct Match
        res = await client.post(
            "/api/v1/connections/validate-group",
            json={"puzzle_id": str(p_uuid), "selected_item_ids": ["p0", "p1", "p2", "p3"]},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["is_match"] is True
        assert body["group"]["group_id"] == "g1"
        assert body["is_one_away"] is False

        # 2. One-Away (3 match g1)
        res_away = await client.post(
            "/api/v1/connections/validate-group",
            json={"puzzle_id": str(p_uuid), "selected_item_ids": ["p0", "p1", "p2", "p4"]},
        )
        assert res_away.status_code == 200
        body_away = res_away.json()
        assert body_away["is_match"] is False
        assert body_away["is_one_away"] is True
        assert body_away["matched_count"] == 3

        # 3. Duplicate Items Error (RFC 7807)
        res_dup = await client.post(
            "/api/v1/connections/validate-group",
            json={"puzzle_id": str(p_uuid), "selected_item_ids": ["p0", "p0", "p1", "p2"]},
        )
        assert res_dup.status_code == 422
        body_dup = res_dup.json()
        assert body_dup["error_code"] == "DUPLICATE_ITEMS_SUBMITTED"

        # 4. Invalid Item Count Error (RFC 7807)
        res_cnt = await client.post(
            "/api/v1/connections/validate-group",
            json={"puzzle_id": str(p_uuid), "selected_item_ids": ["p0", "p1"]},
        )
        assert res_cnt.status_code == 422
        body_cnt = res_cnt.json()
        assert "INVALID_ITEM_COUNT" in body_cnt.get("error_code", "") or "VALIDATION_FAILED" in body_cnt.get("error_code", "")

        # 5. Missing Puzzle Error (RFC 7807)
        res_miss = await client.post(
            "/api/v1/connections/validate-group",
            json={"puzzle_id": str(uuid.uuid4()), "selected_item_ids": ["p0", "p1", "p2", "p3"]},
        )
        assert res_miss.status_code == 404
        body_miss = res_miss.json()
        assert body_miss["error_code"] == "PUZZLE_NOT_FOUND"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ensure_daily_puzzles_startup(session: AsyncSession):
    """Verifies ensure_daily_puzzles generates and commits missing daily puzzles (GRID and CONNECTIONS)."""
    from app.services.puzzle_pipeline import PuzzlePipelineService

    target_date = date(2026, 9, 28)
    created = await PuzzlePipelineService.ensure_daily_puzzles(session=session, target_date=target_date)

    assert "GRID" in created
    assert "CONNECTIONS" in created
    assert created["CONNECTIONS"].game_type == "CONNECTIONS"
    assert created["CONNECTIONS"].target_date == target_date

    # Second call should find them and not error
    created_again = await PuzzlePipelineService.ensure_daily_puzzles(session=session, target_date=target_date)
    assert "GRID" in created_again
    assert "CONNECTIONS" in created_again


@pytest.mark.asyncio
async def test_get_daily_connections_jit_generation(session: AsyncSession):
    """Verifies GET /api/v1/puzzles/connections/daily automatically creates missing puzzle on-the-fly."""
    app.dependency_overrides[get_async_session] = lambda: session

    target_date_str = "2026-09-29"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/puzzles/connections/daily?date={target_date_str}")
        assert res.status_code == 200
        data = res.json()
        assert data["game_type"] == "connections"
        assert data["target_date"] == target_date_str
        assert len(data["puzzle_data"]["items"]) == 16

    app.dependency_overrides.clear()

