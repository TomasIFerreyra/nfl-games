import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.player import Player, PlayerTeamStint
from app.db.models.stats import Accolade
from app.services.grid_precompute_service import GridPrecomputeService
from app.services.grid_validation_service import GridValidationService


@pytest_asyncio.fixture
async def live_db_session():
    """Live database session for end-to-end historical data integrity verification."""
    engine = create_async_engine(settings.async_database_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_brett_favre_data_integrity_and_validation(live_db_session: AsyncSession):
    """
    Verifies Brett Favre's canonical record, career stints across GNB, NYJ, MIN, ATL,
    Hall of Fame accolade, and criterion evaluation.
    """
    # 1. Player record deduplication check
    stmt = select(Player).where(Player.full_name == "Brett Favre")
    result = await live_db_session.execute(stmt)
    favre_records = result.scalars().all()
    assert len(favre_records) == 1, f"Expected exactly 1 canonical record for Brett Favre, found {len(favre_records)}"
    
    favre = favre_records[0]
    assert favre.draft_round == 2
    assert favre.rookie_year == 1991

    # 2. Stints verification
    stint_stmt = select(PlayerTeamStint).where(PlayerTeamStint.player_id == favre.player_id)
    stints = (await live_db_session.execute(stint_stmt)).scalars().all()
    franchises = {s.franchise_id for s in stints if s.games_played >= 1}
    assert "GNB" in franchises, "Brett Favre must have >=1 regular season game for GNB"
    assert "MIN" in franchises, "Brett Favre must have >=1 regular season game for MIN"
    assert "NYJ" in franchises, "Brett Favre must have >=1 regular season game for NYJ"
    assert "ATL" in franchises, "Brett Favre must have >=1 regular season game for ATL"

    # Verify GNB stint spans career years (1992-2007)
    gnb_years = {s.season_year for s in stints if s.franchise_id == "GNB" and s.games_played >= 1}
    assert 1992 in gnb_years
    assert 1996 in gnb_years
    assert 2007 in gnb_years

    # 3. Accolade verification
    acc_stmt = select(Accolade).where(
        Accolade.player_id == favre.player_id,
        Accolade.accolade_type == "HALL_OF_FAME"
    )
    accs = (await live_db_session.execute(acc_stmt)).scalars().all()
    assert len(accs) >= 1, "Brett Favre must have canonical HALL_OF_FAME accolade"

    # 4. Precompute Solution Sets include Favre
    gnb_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "FRAN_GNB")
    min_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "FRAN_MIN")
    nyj_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "FRAN_NYJ")
    hof_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "ACCOLADE_HOF")

    assert favre.player_id in gnb_set, "Brett Favre must qualify for FRAN_GNB"
    assert favre.player_id in min_set, "Brett Favre must qualify for FRAN_MIN"
    assert favre.player_id in nyj_set, "Brett Favre must qualify for FRAN_NYJ"
    assert favre.player_id in hof_set, "Brett Favre must qualify for ACCOLADE_HOF"

    # Intersections:
    # Favre in Packers x Vikings
    assert favre.player_id in (gnb_set & min_set), "Brett Favre must be valid for Packers x Vikings"
    # Favre in Jets x Vikings
    assert favre.player_id in (nyj_set & min_set), "Brett Favre must be valid for Jets x Vikings"
    # Favre in Packers x Hall of Fame
    assert favre.player_id in (gnb_set & hof_set), "Brett Favre must be valid for Packers x Hall of Fame"


@pytest.mark.asyncio
async def test_garrett_wilson_data_integrity_and_validation(live_db_session: AsyncSession):
    """
    Verifies Garrett Wilson's canonical draft round (1), NYJ stint,
    and validation for Jets x 1st Round Pick (FRAN_NYJ x DRAFT_RD1).
    """
    stmt = select(Player).where(Player.full_name == "Garrett Wilson")
    result = await live_db_session.execute(stmt)
    wilson_records = result.scalars().all()
    assert len(wilson_records) == 1, f"Expected 1 canonical record for Garrett Wilson, found {len(wilson_records)}"
    
    wilson = wilson_records[0]
    assert wilson.draft_round == 1, f"Garrett Wilson draft_round must be 1, got {wilson.draft_round}"
    assert wilson.draft_overall == 10
    assert wilson.draft_year == 2022

    # Stint in NYJ
    stint_stmt = select(PlayerTeamStint).where(
        PlayerTeamStint.player_id == wilson.player_id,
        PlayerTeamStint.franchise_id == "NYJ",
        PlayerTeamStint.games_played >= 1
    )
    stints = (await live_db_session.execute(stint_stmt)).scalars().all()
    assert len(stints) >= 1, "Garrett Wilson must have >= 1 game stint for NYJ"

    # Precompute intersection
    nyj_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "FRAN_NYJ")
    rd1_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "DRAFT_RD1")
    assert wilson.player_id in nyj_set, "Garrett Wilson must qualify for FRAN_NYJ"
    assert wilson.player_id in rd1_set, "Garrett Wilson must qualify for DRAFT_RD1"
    assert wilson.player_id in (nyj_set & rd1_set), "Garrett Wilson must be in solution set for Jets x 1st Round Pick"


@pytest.mark.asyncio
async def test_jordan_love_data_integrity_and_validation(live_db_session: AsyncSession):
    """
    Verifies Jordan Love's canonical draft round (1), GNB stint,
    and validation for Packers x 1st Round Pick (FRAN_GNB x DRAFT_RD1).
    """
    stmt = select(Player).where(Player.full_name == "Jordan Love")
    result = await live_db_session.execute(stmt)
    love_records = result.scalars().all()
    assert len(love_records) == 1, f"Expected 1 canonical record for Jordan Love, found {len(love_records)}"
    
    love = love_records[0]
    assert love.draft_round == 1, f"Jordan Love draft_round must be 1, got {love.draft_round}"
    assert love.draft_overall == 26
    assert love.draft_year == 2020

    # Stint in GNB
    stint_stmt = select(PlayerTeamStint).where(
        PlayerTeamStint.player_id == love.player_id,
        PlayerTeamStint.franchise_id == "GNB",
        PlayerTeamStint.games_played >= 1
    )
    stints = (await live_db_session.execute(stint_stmt)).scalars().all()
    assert len(stints) >= 1, "Jordan Love must have >= 1 game stint for GNB"

    # Precompute intersection
    gnb_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "FRAN_GNB")
    rd1_set = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(live_db_session, "DRAFT_RD1")
    assert love.player_id in gnb_set, "Jordan Love must qualify for FRAN_GNB"
    assert love.player_id in rd1_set, "Jordan Love must qualify for DRAFT_RD1"
    assert love.player_id in (gnb_set & rd1_set), "Jordan Love must be in solution set for Packers x 1st Round Pick"


@pytest.mark.asyncio
async def test_accolade_canonical_naming_and_no_stale_records(live_db_session: AsyncSession):
    """
    Verifies that all accolades follow uppercase canonical enum strings and have no duplicates.
    """
    valid_accolades = {
        "HALL_OF_FAME",
        "MVP",
        "OROY",
        "DROY",
        "WPMOTY",
        "FIRST_TEAM_ALL_PRO",
        "PRO_BOWL",
        "SUPER_BOWL_MVP",
        "OPOTY",
        "DPOTY",
        "COMEBACK_PLAYER",
    }
    stmt = text("SELECT DISTINCT accolade_type FROM accolades")
    res = (await live_db_session.execute(stmt)).fetchall()
    found_types = {r[0] for r in res}
    invalid = found_types - valid_accolades
    assert not invalid, f"Found invalid / non-canonical accolade types: {invalid}"


@pytest.mark.asyncio
async def test_entity_deduplication_integrity(live_db_session: AsyncSession):
    """
    Verifies that no active player entities share GSIS ID or PFR ID across multiple records.
    """
    # Check GSIS ID duplicates
    gsis_stmt = text("""
        SELECT gsis_id, COUNT(*)
        FROM players
        WHERE gsis_id IS NOT NULL AND gsis_id != ''
        GROUP BY gsis_id
        HAVING COUNT(*) > 1;
    """)
    gsis_dups = (await live_db_session.execute(gsis_stmt)).fetchall()
    assert len(gsis_dups) == 0, f"Found duplicated GSIS IDs: {gsis_dups}"

    # Check PFR ID duplicates
    pfr_stmt = text("""
        SELECT pfr_id, COUNT(*)
        FROM players
        WHERE pfr_id IS NOT NULL AND pfr_id != ''
        GROUP BY pfr_id
        HAVING COUNT(*) > 1;
    """)
    pfr_dups = (await live_db_session.execute(pfr_stmt)).fetchall()
    assert len(pfr_dups) == 0, f"Found duplicated PFR IDs: {pfr_dups}"
