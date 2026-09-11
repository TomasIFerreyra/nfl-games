import asyncio
from datetime import date, timedelta
from decimal import Decimal
import random
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.franchise import Franchise, TeamSeason
from app.db.models.player import Player, PlayerTeamStint
from app.db.models.puzzle import DailyPuzzle
from app.db.models.stats import Accolade, PlayerCareerStat, PlayerSeasonStat
from app.domain.criteria_registry import (
    CriteriaRegistry,
    CriterionArchetype,
    CriterionDefinition,
    CriterionType,
    registry,
)
from app.domain.grid_templates import (
    TEMPLATES,
    AntiClashValidator,
    GridTemplate,
    TemplateSelector,
)
from app.domain.rotation_tracker import RotationTracker
from packages.etl.generator.grid_generator import GridGenerator
from packages.etl.pipeline.data_enrichment import DataEnrichmentService


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
# Unit Tests: Criteria Taxonomy & Registry
# =====================================================================
def test_criteria_registry_archetypes():
    """Verifies that criteria registry catalogs criteria across all 6 archetypes."""
    all_criteria = registry.get_all_criteria(active_only=False)
    assert len(all_criteria) >= 50

    for arch in CriterionArchetype:
        by_arch = registry.get_criteria_by_archetype(arch, active_only=False)
        assert len(by_arch) > 0, f"Archetype {arch} has 0 criteria registered."


def test_criteria_registry_activation_toggle():
    """Verifies criteria can be dynamically enabled/disabled for coverage."""
    reg = CriteriaRegistry()
    crit_id = "STAT_PASS_4000"
    crit = reg.get_criterion(crit_id)
    assert crit is not None
    assert crit.is_active is True

    reg.set_active_status(crit_id, False)
    assert reg.get_criterion(crit_id).is_active is False

    active_list = reg.get_all_criteria(active_only=True)
    assert crit_id not in [c.criterion_id for c in active_list]


# =====================================================================
# Unit Tests: Anti-Clash Verification
# =====================================================================
def test_anti_clash_duplicate_franchises():
    """Rejects grids containing identical franchises across rows or columns."""
    r0 = registry.get_criterion("FRAN_GNB")
    r1 = registry.get_criterion("FRAN_NYJ")
    r2 = registry.get_criterion("STAT_PASS_4000")

    c0 = registry.get_criterion("FRAN_GNB")  # Duplicate with r0
    c1 = registry.get_criterion("ACCOLADE_HOF")
    c2 = registry.get_criterion("DRAFT_RD1")

    is_valid, reason = AntiClashValidator.validate_grid([r0, r1, r2], [c0, c1, c2])
    assert is_valid is False
    assert "Duplicate" in reason


def test_anti_clash_franchise_division_overlap():
    """Rejects grids where a franchise intersects with the division it belongs to."""
    # NE Patriots belongs to AFC East
    r0 = registry.get_criterion("FRAN_NE")
    r1 = registry.get_criterion("FRAN_DAL")
    r2 = registry.get_criterion("STAT_RUSH_1000")

    c0 = registry.get_criterion("DIV_AFC_EAST")  # Clash with NE!
    c1 = registry.get_criterion("ACCOLADE_HOF")
    c2 = registry.get_criterion("DRAFT_RD1")

    is_valid, reason = AntiClashValidator.validate_grid([r0, r1, r2], [c0, c1, c2])
    assert is_valid is False
    assert "belongs to division" in reason


def test_anti_clash_mutually_exclusive_draft():
    """Rejects combinations of Round 1 with Round 4+ or Undrafted."""
    r_rd1 = registry.get_criterion("DRAFT_RD1")
    c_rd4 = registry.get_criterion("DRAFT_RD4_PLUS")

    is_valid, reason = AntiClashValidator.validate_cell_intersection(r_rd1, c_rd4)
    assert is_valid is False
    assert "mutually exclusive" in reason


def test_anti_clash_valid_grid():
    """Validates that a legitimate, non-clashing grid passes cleanly."""
    r0 = registry.get_criterion("FRAN_GNB")
    r1 = registry.get_criterion("FRAN_NYJ")
    r2 = registry.get_criterion("STAT_PASS_4000")

    c0 = registry.get_criterion("FRAN_MIN")
    c1 = registry.get_criterion("ACCOLADE_HOF")
    c2 = registry.get_criterion("DRAFT_RD1")

    is_valid, reason = AntiClashValidator.validate_grid([r0, r1, r2], [c0, c1, c2])
    assert is_valid is True
    assert reason is None


# =====================================================================
# Unit Tests: Rotation Memory & Recency Fatigue
# =====================================================================
def test_rotation_tracker_decay_and_cooldown():
    """Verifies that recently used criteria receive correct decay penalties."""
    tracker = RotationTracker(cooldown_days=3, fatigue_window_days=14)

    target_date = date(2026, 9, 10)

    # 1. Day before (D - 1): strictly locked out (weight = 0.0)
    tracker.record_usage("FRAN_GNB", date(2026, 9, 9))
    assert tracker.get_fatigue_multiplier("FRAN_GNB", target_date) == 0.0

    # 2. 5 days ago (D - 5): strong penalty (weight = 0.25)
    tracker.record_usage("FRAN_MIN", date(2026, 9, 5))
    assert tracker.get_fatigue_multiplier("FRAN_MIN", target_date) == 0.25

    # 3. 10 days ago (D - 10): moderate penalty (weight = 0.60)
    tracker.record_usage("FRAN_KC", date(2026, 9, 1))
    assert tracker.get_fatigue_multiplier("FRAN_KC", target_date) == 0.60

    # 4. 20 days ago or unused: full weight (1.00)
    tracker.record_usage("FRAN_DAL", date(2026, 8, 20))
    assert tracker.get_fatigue_multiplier("FRAN_DAL", target_date) == 1.00
    assert tracker.get_fatigue_multiplier("FRAN_SFO", target_date) == 1.00


# =====================================================================
# Unit Tests: Procedural Grid Generator Pipeline
# =====================================================================
@pytest.mark.asyncio
async def test_grid_generator_deterministic_reproducibility(session: AsyncSession):
    """Verifies that identical dates yield identical puzzles via deterministic seeding."""
    target_date = date(2026, 9, 20)
    puzzle_1 = await GridGenerator.generate_puzzle_data(
        session=session,
        target_date=target_date,
        puzzle_number=20,
        k_min=3,
    )
    puzzle_2 = await GridGenerator.generate_puzzle_data(
        session=session,
        target_date=target_date,
        puzzle_number=20,
        k_min=3,
    )

    hash_1 = GridGenerator.compute_solution_hash(puzzle_1)
    hash_2 = GridGenerator.compute_solution_hash(puzzle_2)

    assert hash_1 == hash_2
    assert puzzle_1["rows"] == puzzle_2["rows"]
    assert puzzle_1["columns"] == puzzle_2["columns"]
    assert puzzle_1["cell_cardinalities"] == puzzle_2["cell_cardinalities"]


@pytest.mark.asyncio
async def test_grid_generator_solvability_invariant(session: AsyncSession):
    """Verifies that generated grid satisfies |S_{r, c}| >= 3 for all 9 cells."""
    target_date = date(2026, 9, 21)
    puzzle = await GridGenerator.generate_puzzle_data(
        session=session,
        target_date=target_date,
        puzzle_number=21,
        k_min=3,
    )

    card_matrix = puzzle["cell_cardinalities"]
    assert len(card_matrix) == 3
    assert len(card_matrix[0]) == 3

    for r in range(3):
        for c in range(3):
            val = card_matrix[r][c]
            assert val >= 3, f"Cell ({r}, {c}) has cardinality {val} < 3"


# =====================================================================
# Unit Tests: Data Enrichment & Coverage Verification
# =====================================================================
@pytest.mark.asyncio
async def test_data_enrichment_career_stats(session: AsyncSession):
    """Tests career statistics aggregation and precomputation into player_career_stats."""
    # 1. Seed player with seasons
    p = Player(
        player_id="p-test-career",
        full_name="Career Hero",
        first_name="Career",
        last_name="Hero",
        primary_position="RB",
        rookie_year=2015,
        is_active=False,
    )
    f = Franchise(franchise_id="KC", canonical_name="Kansas City Chiefs", established_year=1960)
    ts = TeamSeason(team_season_id="KC_2015", franchise_id="KC", season_year=2015, team_name="Chiefs", team_abbr="KC")
    session.add_all([p, f, ts])
    await session.flush()

    s1 = PlayerTeamStint(player_id="p-test-career", franchise_id="KC", season_year=2015, games_played=16)
    stat1 = PlayerSeasonStat(player_id="p-test-career", team_season_id="KC_2015", season_year=2015, rushing_yards=1200, rushing_tds=10)
    stat2 = PlayerSeasonStat(player_id="p-test-career", team_season_id="KC_2015", season_year=2016, rushing_yards=1100, rushing_tds=8)
    session.add_all([s1, stat1, stat2])
    await session.commit()

    # 2. Run career aggregation
    count = await DataEnrichmentService.compute_career_stats(session)
    assert count >= 1

    # 3. Query precomputed career stat
    q = select(PlayerCareerStat).where(PlayerCareerStat.player_id == "p-test-career")
    career_rec = (await session.execute(q)).scalar_one_or_none()
    assert career_rec is not None
    assert career_rec.rushing_yards == 2300
    assert career_rec.rushing_tds == 18
    assert career_rec.franchises_played_count == 1
