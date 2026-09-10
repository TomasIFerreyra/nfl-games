"""
Unit tests for Player Search Index Serialization, ETL Canonical Metadata, and Career Span Resolution.
"""

import gzip
import json
import os
import tempfile
import uuid
import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.db.base import Base
from app.db.models.player import Player, PlayerTeamStint
from app.db.models.franchise import Franchise
from app.db.session import get_async_session
from app.main import app
from packages.etl.generator.export_search_index import export_player_search_index
from packages.etl.pipeline.transform import NFLDataTransformer


# Register SQLite type compilations for in-memory testing
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

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(db_session_factory):
    """Seeds foundational franchises and test players."""
    async with db_session_factory() as session:
        # 1. Franchises
        kc = Franchise(franchise_id="KC", canonical_name="Kansas City Chiefs", established_year=1960)
        nwe = Franchise(franchise_id="NWE", canonical_name="New England Patriots", established_year=1960)
        ind = Franchise(franchise_id="IND", canonical_name="Indianapolis Colts", established_year=1953)
        lar = Franchise(franchise_id="LAR", canonical_name="Los Angeles Rams", established_year=1937)
        session.add_all([kc, nwe, ind, lar])
        await session.flush()

        # 2. Players
        # Active player (Patrick Mahomes)
        p_mahomes = Player(
            player_id=str(uuid.uuid4()),
            gsis_id="00-0033873",
            pfr_id="MahoPa00",
            full_name="Patrick Mahomes",
            first_name="Patrick",
            last_name="Mahomes",
            primary_position="QB",
            rookie_year=2017,
            final_year=None,
            is_active=True,
        )

        # Retired legend with explicit final_year (Tom Brady)
        p_brady = Player(
            player_id=str(uuid.uuid4()),
            gsis_id="00-0019596",
            pfr_id="BradTo00",
            full_name="Tom Brady",
            first_name="Tom",
            last_name="Brady",
            primary_position="QB",
            rookie_year=2000,
            final_year=2022,
            is_active=False,
        )

        # Retired legend with explicit final_year (Peyton Manning)
        p_manning = Player(
            player_id=str(uuid.uuid4()),
            gsis_id="00-0010346",
            pfr_id="MannPe00",
            full_name="Peyton Manning",
            first_name="Peyton",
            last_name="Manning",
            primary_position="QB",
            rookie_year=1998,
            final_year=2015,
            is_active=False,
        )

        # Inactive historical player with NULL final_year (to test stint fallback)
        p_historical_null_end = Player(
            player_id=str(uuid.uuid4()),
            gsis_id=None,
            pfr_id=None,
            full_name="Historical Star",
            first_name="Historical",
            last_name="Star",
            primary_position="RB",
            rookie_year=1995,
            final_year=None,
            is_active=False,
        )

        session.add_all([p_mahomes, p_brady, p_manning, p_historical_null_end])
        await session.flush()

        # Add stints
        stint1 = PlayerTeamStint(player_id=p_historical_null_end.player_id, franchise_id="IND", season_year=1995, games_played=16)
        stint2 = PlayerTeamStint(player_id=p_historical_null_end.player_id, franchise_id="IND", season_year=2003, games_played=16)
        session.add_all([stint1, stint2])

        await session.commit()
        yield session


@pytest.mark.asyncio
async def test_transform_players_with_id_map_metadata():
    """
    Verifies that transform_players extracts the true canonical rookie_year and final_year
    from id_map_df even when the rosters DataFrame is truncated to seasons >= 2020.
    """
    rosters_data = [
        {"player_id": "00-0019596", "player_name": "Tom Brady", "position": "QB", "season": 2020},
        {"player_id": "00-0019596", "player_name": "Tom Brady", "position": "QB", "season": 2021},
        {"player_id": "00-0019596", "player_name": "Tom Brady", "position": "QB", "season": 2022},
        {"player_id": "00-0033873", "player_name": "Patrick Mahomes", "position": "QB", "season": 2020},
        {"player_id": "00-0033873", "player_name": "Patrick Mahomes", "position": "QB", "season": 2024},
    ]
    rosters_df = pd.DataFrame(rosters_data)

    id_map_data = [
        {
            "gsis_id": "00-0019596",
            "pfr_id": "BradTo00",
            "display_name": "Tom Brady",
            "rookie_season": 2000,
            "draft_year": 2000,
            "last_season": 2022,
            "status": "RET",
        },
        {
            "gsis_id": "00-0033873",
            "pfr_id": "MahoPa00",
            "display_name": "Patrick Mahomes",
            "rookie_season": 2017,
            "draft_year": 2017,
            "last_season": 2026,
            "status": "ACT",
        },
    ]
    id_map_df = pd.DataFrame(id_map_data)

    records = NFLDataTransformer.transform_players(rosters_df, id_map_df)
    by_name = {r["full_name"]: r for r in records}

    # Tom Brady should have rookie_year=2000 (not 2020), final_year=2022, is_active=False
    brady = by_name["Tom Brady"]
    assert brady["rookie_year"] == 2000
    assert brady["final_year"] == 2022
    assert brady["is_active"] is False

    # Patrick Mahomes should have rookie_year=2017 (not 2020), final_year=None, is_active=True
    mahomes = by_name["Patrick Mahomes"]
    assert mahomes["rookie_year"] == 2017
    assert mahomes["final_year"] is None
    assert mahomes["is_active"] is True


@pytest.mark.asyncio
async def test_search_index_api_endpoint(seeded_session, db_session_factory):
    """
    Tests the FastAPI /api/v1/players/search-index endpoint.
    Verifies that:
    1. Active players have is_active=1 and final_year=None.
    2. Retired players have is_active=0 and accurate final_year.
    3. Inactive players missing final_year fallback to MAX(season_year) from stints.
    """
    app.dependency_overrides[get_async_session] = lambda: seeded_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get("/api/v1/players/search-index")
        assert resp.status_code == 200
        data = resp.json()

        assert "fields" in data
        assert data["fields"] == ["id", "name", "pos", "start", "end", "active"]

        players = data["players"]
        players_by_name = {p[1]: p for p in players}

        # Patrick Mahomes (Active)
        mahomes = players_by_name["Patrick Mahomes"]
        assert mahomes[3] == 2017  # start
        assert mahomes[4] is None  # end
        assert mahomes[5] == 1     # active

        # Tom Brady (Retired)
        brady = players_by_name["Tom Brady"]
        assert brady[3] == 2000    # start
        assert brady[4] == 2022    # end
        assert brady[5] == 0       # inactive

        # Peyton Manning (Retired)
        manning = players_by_name["Peyton Manning"]
        assert manning[3] == 1998  # start
        assert manning[4] == 2015  # end
        assert manning[5] == 0     # inactive

        # Historical Star with NULL final_year in DB -> should compute 2003 from stints
        hist = players_by_name["Historical Star"]
        assert hist[3] == 1995     # start
        assert hist[4] == 2003     # computed MAX(stint) = 2003
        assert hist[5] == 0        # inactive

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_player_search_index_gz(seeded_session):
    """
    Tests export_player_search_index function writes valid gzipped JSON with proper schema.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        gz_path = await export_player_search_index(seeded_session, output_dir=tmpdir)
        assert os.path.exists(gz_path)

        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            data = json.load(f)

        assert data["fields"] == ["id", "name", "pos", "start", "end", "active"]
        assert len(data["players"]) == 4

        players_by_name = {p[1]: p for p in data["players"]}
        assert players_by_name["Patrick Mahomes"][3] == 2017
        assert players_by_name["Tom Brady"][3] == 2000
        assert players_by_name["Historical Star"][4] == 2003


def test_career_span_formatting_rules():
    """
    Verifies the frontend formatting rules contract:
    - is_active === True -> `${startYear} - Present`
    - is_active === False and endYear -> `${startYear} - ${endYear}`
    - is_active === False and endYear is None -> `${startYear} - Unknown`
    """
    def format_career_span(start: int, end: int | None, is_active: bool) -> str:
        if is_active:
            return f"{start} - Present"
        if end is not None:
            return f"{start} - {end}"
        return f"{start} - Unknown"

    assert format_career_span(2017, None, True) == "2017 - Present"
    assert format_career_span(2005, None, True) == "2005 - Present"
    assert format_career_span(2000, 2022, False) == "2000 - 2022"
    assert format_career_span(1998, 2015, False) == "1998 - 2015"
    assert format_career_span(1983, 1999, False) == "1983 - 1999"
    assert format_career_span(1990, None, False) == "1990 - Unknown"
