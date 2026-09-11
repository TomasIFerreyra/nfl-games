import asyncio
from datetime import date
from decimal import Decimal
import json
from typing import Any, Dict, List, Optional, Set
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError, RedisError
from sqlalchemy import BigInteger, Integer, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.redis import get_redis
from app.db.base import Base
from app.db.models.franchise import Franchise
from app.db.models.player import Player, PlayerTeamStint
from app.db.models.puzzle import AggregatedAnswerStats, DailyPuzzle
from app.db.models.stats import Accolade, PlayerSeasonStat
from app.db.session import get_async_session
from app.main import app
from app.schemas.grid import GridValidateRequest, GridValidateResponse
from app.services.grid_precompute_service import GridPrecomputeService
from app.services.grid_validation_service import GridValidationService


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


# =====================================================================
# In-Memory Async Redis Mock with Atomic Concurrency Support
# =====================================================================
class MockRedisPipeline:
    def __init__(self, client: "MockRedis"):
        self.client = client
        self.commands: List[Any] = []

    def incr(self, key: str) -> "MockRedisPipeline":
        self.commands.append(("incr", key))
        return self

    def hincrby(self, key: str, field: str, amount: int = 1) -> "MockRedisPipeline":
        self.commands.append(("hincrby", key, field, amount))
        return self

    def get(self, key: str) -> "MockRedisPipeline":
        self.commands.append(("get", key))
        return self

    def set(self, key: str, value: str, ex: Optional[int] = None) -> "MockRedisPipeline":
        self.commands.append(("set", key, value, ex))
        return self

    def delete(self, *keys: str) -> "MockRedisPipeline":
        self.commands.append(("delete", keys))
        return self

    def sadd(self, key: str, *members: str) -> "MockRedisPipeline":
        self.commands.append(("sadd", key, members))
        return self

    def expire(self, key: str, ttl: int) -> "MockRedisPipeline":
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self) -> List[Any]:
        results = []
        async with self.client._lock:
            for cmd in self.commands:
                op = cmd[0]
                if op == "incr":
                    key = cmd[1]
                    val = int(self.client._kv.get(key, 0)) + 1
                    self.client._kv[key] = str(val)
                    results.append(val)
                elif op == "hincrby":
                    key, field, amount = cmd[1], cmd[2], cmd[3]
                    if key not in self.client._hashes:
                        self.client._hashes[key] = {}
                    val = int(self.client._hashes[key].get(field, 0)) + amount
                    self.client._hashes[key][field] = str(val)
                    results.append(val)
                elif op == "get":
                    key = cmd[1]
                    results.append(self.client._kv.get(key))
                elif op == "set":
                    key, value, _ = cmd[1], cmd[2], cmd[3]
                    self.client._kv[key] = str(value)
                    results.append(True)
                elif op == "delete":
                    for k in cmd[1]:
                        self.client._kv.pop(k, None)
                        self.client._sets.pop(k, None)
                        self.client._hashes.pop(k, None)
                    results.append(1)
                elif op == "sadd":
                    key, members = cmd[1], cmd[2]
                    if key not in self.client._sets:
                        self.client._sets[key] = set()
                    self.client._sets[key].update(members)
                    results.append(len(members))
                elif op == "expire":
                    results.append(True)
        return results


class MockRedis:
    def __init__(self):
        self._sets: Dict[str, Set[str]] = {}
        self._kv: Dict[str, str] = {}
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._lock = asyncio.Lock()
        self.is_connected = True

    async def ping(self) -> bool:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        return True

    async def sismember(self, key: str, member: str) -> bool:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            return member in self._sets.get(key, set())

    async def sadd(self, key: str, *members: str) -> int:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            if key not in self._sets:
                self._sets[key] = set()
            self._sets[key].update(members)
            return len(members)

    async def exists(self, key: str) -> int:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            return 1 if (key in self._sets or key in self._kv or key in self._hashes) else 0

    async def get(self, key: str) -> Optional[str]:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            return self._kv.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            if nx and (key in self._kv or key in self._sets or key in self._hashes):
                return False
            if xx and key not in self._kv:
                return False
            self._kv[key] = str(value)
            return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            if "del" in script and len(keys_and_args) >= 2:
                key = keys_and_args[0]
                val = keys_and_args[1]
                if self._kv.get(key) == val:
                    self._kv.pop(key, None)
                    return 1
                return 0
            return 1

    async def incr(self, key: str) -> int:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            val = int(self._kv.get(key, 0)) + 1
            self._kv[key] = str(val)
            return val

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            if key not in self._hashes:
                self._hashes[key] = {}
            val = int(self._hashes[key].get(field, 0)) + amount
            self._hashes[key][field] = str(val)
            return val

    async def hgetall(self, key: str) -> Dict[str, str]:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            return dict(self._hashes.get(key, {}))

    async def delete(self, *keys: str) -> int:
        if not self.is_connected:
            raise ConnectionError("Redis server unavailable")
        async with self._lock:
            count = 0
            for k in keys:
                if k in self._sets or k in self._kv or k in self._hashes:
                    self._sets.pop(k, None)
                    self._kv.pop(k, None)
                    self._hashes.pop(k, None)
                    count += 1
            return count

    async def expire(self, key: str, ttl: int) -> bool:
        return True

    def pipeline(self, transaction: bool = True) -> MockRedisPipeline:
        return MockRedisPipeline(self)


# =====================================================================
# Pytest Fixtures with In-Memory SQLite Async Database
# =====================================================================
@pytest_asyncio.fixture
async def test_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield session_maker
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_session_factory):
    async with test_session_factory() as session:
        yield session


@pytest.fixture
def mock_redis() -> MockRedis:
    return MockRedis()


# =====================================================================
# Unit Tests: Bayesian Rarity Formula
# =====================================================================
def test_bayesian_rarity_formula():
    """
    Verifies R*(p, c) = [(n(p, c) + M * pi) / (N(c) + M)] * 100
    where M = 25, pi = 1 / |S_c|.
    """
    # Case 1: First user to pick player A out of |S_c| = 50 possibilities
    # n = 1, N = 1, M = 25, pi = 1/50 = 0.02
    # R* = [(1 + 25 * 0.02) / (1 + 25)] * 100 = [(1 + 0.5) / 26] * 100 = (1.5 / 26) * 100 = 5.769% -> 5.77%
    score_cold_start = GridValidationService.calculate_bayesian_rarity(
        player_picks=1,
        total_picks=1,
        possible_answers_count=50,
    )
    assert score_cold_start == 5.77

    # Case 2: High volume consensus pick (500 picks out of 1000 total picks)
    # n = 500, N = 1000, M = 25, pi = 0.02
    # R* = [(500 + 0.5) / 1025] * 100 = (500.5 / 1025) * 100 = 48.829% -> 48.83%
    score_high_volume = GridValidationService.calculate_bayesian_rarity(
        player_picks=500,
        total_picks=1000,
        possible_answers_count=50,
    )
    assert score_high_volume == 48.83

    # Case 3: Ultra-obscure pick (1 pick out of 10,000 total picks)
    # n = 1, N = 10000, M = 25, pi = 0.02
    # R* = [(1 + 0.5) / 10025] * 100 = (1.5 / 10025) * 100 = 0.0149% -> 0.01%
    score_obscure = GridValidationService.calculate_bayesian_rarity(
        player_picks=1,
        total_picks=10000,
        possible_answers_count=50,
    )
    assert score_obscure == 0.01


# =====================================================================
# Unit Tests: Precomputation and Solution Set Generation
# =====================================================================
@pytest.mark.asyncio
async def test_grid_precomputation_and_warming(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests offline relational query execution, solution set generation, and Redis warming.
    """
    # 1. Seed database with players, franchises, stints, stats
    p1 = Player(
        player_id="p-favre",
        full_name="Brett Favre",
        first_name="Brett",
        last_name="Favre",
        primary_position="QB",
        rookie_year=1991,
        draft_round=2,
        is_active=False,
    )
    p2 = Player(
        player_id="p-rodgers",
        full_name="Aaron Rodgers",
        first_name="Aaron",
        last_name="Rodgers",
        primary_position="QB",
        rookie_year=2005,
        draft_round=1,
        is_active=True,
    )
    p3 = Player(
        player_id="p-moss",
        full_name="Randy Moss",
        first_name="Randy",
        last_name="Moss",
        primary_position="WR",
        rookie_year=1998,
        draft_round=1,
        is_active=False,
    )
    f_gnb = Franchise(franchise_id="GNB", canonical_name="Green Bay Packers", established_year=1921)
    f_min = Franchise(franchise_id="MIN", canonical_name="Minnesota Vikings", established_year=1961)

    test_db_session.add_all([p1, p2, p3, f_gnb, f_min])
    await test_db_session.flush()

    # Stints:
    # Brett Favre played for GNB and MIN
    s1 = PlayerTeamStint(player_id="p-favre", franchise_id="GNB", season_year=1995, games_played=16)
    s2 = PlayerTeamStint(player_id="p-favre", franchise_id="MIN", season_year=2009, games_played=16)
    # Aaron Rodgers played for GNB
    s3 = PlayerTeamStint(player_id="p-rodgers", franchise_id="GNB", season_year=2010, games_played=16)
    # Randy Moss played for MIN
    s4 = PlayerTeamStint(player_id="p-moss", franchise_id="MIN", season_year=1998, games_played=16)

    # Stats:
    # Favre and Rodgers both threw 4,000+ pass yards
    # (Note: TeamSeason requires franchise_id and season_year)
    from app.db.models.franchise import TeamSeason
    ts_gnb = TeamSeason(team_season_id="GNB_1995", franchise_id="GNB", season_year=1995, team_name="Packers", team_abbr="GNB")
    test_db_session.add(ts_gnb)
    await test_db_session.flush()

    stat1 = PlayerSeasonStat(player_id="p-favre", team_season_id="GNB_1995", season_year=1995, passing_yards=4413)
    stat2 = PlayerSeasonStat(player_id="p-rodgers", team_season_id="GNB_1995", season_year=2011, passing_yards=4643)

    # Accolades:
    acc1 = Accolade(player_id="p-favre", season_year=2016, accolade_type="HALL_OF_FAME")
    acc2 = Accolade(player_id="p-moss", season_year=2018, accolade_type="HALL_OF_FAME")

    test_db_session.add_all([s1, s2, s3, s4, stat1, stat2, acc1, acc2])
    await test_db_session.flush()

    # 2. Create Grid DailyPuzzle instance
    puzzle_id = uuid.uuid4()
    puzzle_data = {
        "rows": [
            {"criterion_id": "FRAN_GNB", "type": "FRANCHISE", "display_title": "Green Bay Packers", "parameters": {"franchise_id": "GNB"}},
            {"criterion_id": "STAT_PASS_4000", "type": "STAT_SEASON", "display_title": "4,000+ Pass Yds", "parameters": {"stat_name": "passing_yards", "threshold": 4000}},
            {"criterion_id": "ACCOLADE_HOF", "type": "ACCOLADE", "display_title": "Hall of Fame", "parameters": {"accolade_type": "HALL_OF_FAME"}},
        ],
        "columns": [
            {"criterion_id": "FRAN_MIN", "type": "FRANCHISE", "display_title": "Minnesota Vikings", "parameters": {"franchise_id": "MIN"}},
            {"criterion_id": "DRAFT_RD1", "type": "DRAFT_ROUND", "display_title": "1st Round Pick", "parameters": {"round": 1}},
            {"criterion_id": "ACCOLADE_HOF", "type": "ACCOLADE", "display_title": "Hall of Fame", "parameters": {"accolade_type": "HALL_OF_FAME"}},
        ],
    }
    puzzle = DailyPuzzle(
        puzzle_id=puzzle_id,
        target_date=date(2026, 9, 7),
        game_type="GRID",
        puzzle_number=101,
        puzzle_data=puzzle_data,
        solution_hash="test_hash",
    )
    test_db_session.add(puzzle)
    await test_db_session.commit()

    # 3. Execute Precomputation Service
    result = await GridPrecomputeService.precompute_and_store_puzzle(
        session=test_db_session,
        puzzle_id=puzzle_id,
        redis_client=mock_redis,
        min_cardinality=1,
    )

    assert result["puzzle_id"] == str(puzzle_id)

    # Cell (0, 0): Played for GNB AND MIN -> Favre
    assert "p-favre" in mock_redis._sets[f"puzzle:{puzzle_id}:cell:0_0:solutions"]
    assert "p-rodgers" not in mock_redis._sets[f"puzzle:{puzzle_id}:cell:0_0:solutions"]

    # Cell (0, 1): Played for GNB AND 1st Round Pick -> Aaron Rodgers
    assert "p-rodgers" in mock_redis._sets[f"puzzle:{puzzle_id}:cell:0_1:solutions"]
    assert "p-favre" not in mock_redis._sets[f"puzzle:{puzzle_id}:cell:0_1:solutions"]  # Favre is 2nd round pick

    # Cardinality key in Redis
    expected_len = len(mock_redis._sets[f"puzzle:{puzzle_id}:cell:0_0:solutions"])
    assert int(mock_redis._kv[f"puzzle:{puzzle_id}:cell:0_0:cardinality"]) == expected_len


# =====================================================================
# Unit Tests: Real-time O(1) Validation and Atomic Counters
# =====================================================================
@pytest.mark.asyncio
async def test_grid_realtime_validation_and_scoring(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests O(1) Redis SISMEMBER lookup, atomic counter increments, and Bayesian rarity return.
    """
    puzzle_id = str(uuid.uuid4())

    # Pre-populate Redis sets and metadata
    sol_key = f"puzzle:{puzzle_id}:cell:0_0:solutions"
    card_key = f"puzzle:{puzzle_id}:cell:0_0:cardinality"
    await mock_redis.sadd(sol_key, "00-0010344", "00-0033873")  # e.g., Patrick Mahomes
    await mock_redis.set(card_key, "50")

    # Add player to DB
    player = Player(
        player_id="00-0033873",
        full_name="Patrick Mahomes",
        first_name="Patrick",
        last_name="Mahomes",
        primary_position="QB",
        rookie_year=2017,
        draft_round=1,
        is_active=True,
    )
    puzzle = DailyPuzzle(
        puzzle_id=uuid.UUID(puzzle_id),
        target_date=date(2026, 9, 8),
        game_type="GRID",
        puzzle_number=102,
        puzzle_data={"valid_solutions": {"0_0": ["00-0010344", "00-0033873"]}, "cell_cardinalities": [[50, 10, 10], [10, 10, 10], [10, 10, 10]]},
        solution_hash="hash",
    )
    test_db_session.add_all([player, puzzle])
    await test_db_session.commit()

    # 1. Validate a CORRECT guess
    resp_correct = await GridValidationService.validate_guess(
        session=test_db_session,
        puzzle_id=puzzle_id,
        row_index=0,
        col_index=0,
        player_id="00-0033873",
        redis_client=mock_redis,
    )

    assert resp_correct.is_valid is True
    assert resp_correct.player.player_id == "00-0033873"
    assert resp_correct.player.full_name == "Patrick Mahomes"
    assert resp_correct.total_picks_for_cell == 1
    assert resp_correct.player_picks_for_cell == 1
    assert resp_correct.possible_answers_count == 50
    assert resp_correct.rarity_score == 5.77  # [(1 + 25*(1/50)) / 26] * 100

    # 2. Validate a second submission for the SAME player
    resp_correct_2 = await GridValidationService.validate_guess(
        session=test_db_session,
        puzzle_id=puzzle_id,
        row_index=0,
        col_index=0,
        player_id="00-0033873",
        redis_client=mock_redis,
    )
    assert resp_correct_2.is_valid is True
    assert resp_correct_2.total_picks_for_cell == 2
    assert resp_correct_2.player_picks_for_cell == 2

    # 3. Validate an INCORRECT guess
    resp_invalid = await GridValidationService.validate_guess(
        session=test_db_session,
        puzzle_id=puzzle_id,
        row_index=0,
        col_index=0,
        player_id="invalid-player-id",
        redis_client=mock_redis,
    )
    assert resp_invalid.is_valid is False
    assert resp_invalid.failed_criteria == ["GRID_CRITERIA_MISMATCH"]


# =====================================================================
# Concurrency Tests: 50+ Parallel Submissions Race Condition Check
# =====================================================================
@pytest.mark.asyncio
async def test_grid_concurrent_submissions(test_session_factory, mock_redis: MockRedis):
    """
    Simulates 50 concurrent validation requests verifying Redis pipeline atomicity (no lost increments).
    """
    puzzle_id = str(uuid.uuid4())
    sol_key = f"puzzle:{puzzle_id}:cell:1_1:solutions"
    card_key = f"puzzle:{puzzle_id}:cell:1_1:cardinality"
    await mock_redis.sadd(sol_key, "player-test-concurrent")
    await mock_redis.set(card_key, "20")

    puzzle = DailyPuzzle(
        puzzle_id=uuid.UUID(puzzle_id),
        target_date=date(2026, 9, 9),
        game_type="GRID",
        puzzle_number=103,
        puzzle_data={"valid_solutions": {"1_1": ["player-test-concurrent"]}, "cell_cardinalities": [[10]*3, [10, 20, 10], [10]*3]},
        solution_hash="hash3",
    )
    async with test_session_factory() as session:
        session.add(puzzle)
        await session.commit()

    # Launch 50 concurrent validation requests, each using its own session
    concurrency = 50

    async def worker():
        async with test_session_factory() as session:
            return await GridValidationService.validate_guess(
                session=session,
                puzzle_id=puzzle_id,
                row_index=1,
                col_index=1,
                player_id="player-test-concurrent",
                redis_client=mock_redis,
            )

    responses = await asyncio.gather(*(worker() for _ in range(concurrency)))

    # Verify all succeeded
    assert all(r.is_valid for r in responses)

    # Check final Redis counter states
    total_in_redis = int(mock_redis._kv[f"puzzle:{puzzle_id}:cell:1_1:total"])
    picks_in_redis = int(mock_redis._hashes[f"puzzle:{puzzle_id}:cell:1_1:picks"]["player-test-concurrent"])

    assert total_in_redis == concurrency
    assert picks_in_redis == concurrency


# =====================================================================
# Failover & Resilience Tests: Redis Offline / Outage Fallback
# =====================================================================
@pytest.mark.asyncio
async def test_grid_redis_failover_to_postgresql(test_db_session: AsyncSession):
    """
    Tests graceful fallback to PostgreSQL JSONB when Redis is disconnected or unavailable.
    """
    puzzle_id = uuid.uuid4()
    player_id = "p-fallback-hero"

    puzzle_data = {
        "valid_solutions": {
            "2_2": [player_id, "other-player"]
        },
        "cell_cardinalities": [
            [10, 10, 10],
            [10, 10, 10],
            [10, 10, 25],
        ],
    }
    puzzle = DailyPuzzle(
        puzzle_id=puzzle_id,
        target_date=date(2026, 9, 10),
        game_type="GRID",
        puzzle_number=104,
        puzzle_data=puzzle_data,
        solution_hash="hash4",
    )
    test_db_session.add(puzzle)
    await test_db_session.commit()

    # Call validate_guess with redis_client = None (Simulating Redis outage)
    response = await GridValidationService.validate_guess(
        session=test_db_session,
        puzzle_id=puzzle_id,
        row_index=2,
        col_index=2,
        player_id=player_id,
        redis_client=None,
    )

    assert response.is_valid is True
    assert response.possible_answers_count == 25
    assert response.total_picks_for_cell == 1
    assert response.player_picks_for_cell == 1

    # Verify that the fallback saved the stats to PostgreSQL
    stats_query = select(AggregatedAnswerStats).where(
        AggregatedAnswerStats.puzzle_id == puzzle_id,
        AggregatedAnswerStats.cell_identifier == "r2_c2",
        AggregatedAnswerStats.player_id == player_id,
    )
    stats_row = (await test_db_session.execute(stats_query)).scalar_one_or_none()
    assert stats_row is not None
    assert stats_row.selection_count == 1


# =====================================================================
# HTTP API Integration Tests (FastAPI Endpoint POST /api/v1/grid/validate)
# =====================================================================
@pytest.mark.asyncio
async def test_fastapi_grid_validate_endpoint(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests the FastAPI endpoint routing, request parsing, and RFC 7807 error responses.
    """
    puzzle_id = str(uuid.uuid4())
    sol_key = f"puzzle:{puzzle_id}:cell:0_2:solutions"
    card_key = f"puzzle:{puzzle_id}:cell:0_2:cardinality"
    await mock_redis.sadd(sol_key, "p-mahomes")
    await mock_redis.set(card_key, "30")

    puzzle = DailyPuzzle(
        puzzle_id=uuid.UUID(puzzle_id),
        target_date=date(2026, 9, 11),
        game_type="GRID",
        puzzle_number=105,
        puzzle_data={"valid_solutions": {"0_2": ["p-mahomes"]}, "cell_cardinalities": [[10, 10, 30], [10, 10, 10], [10, 10, 10]]},
        solution_hash="hash5",
    )
    test_db_session.add(puzzle)
    await test_db_session.commit()

    # Override dependencies
    app.dependency_overrides[get_async_session] = lambda: test_db_session
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Valid submission
        res = await client.post(
            "/api/v1/grid/validate",
            json={
                "puzzle_id": puzzle_id,
                "row_index": 0,
                "col_index": 2,
                "player_id": "p-mahomes",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["is_valid"] is True
        assert data["row_index"] == 0
        assert data["col_index"] == 2
        assert data["possible_answers_count"] == 30

        # 2. Out of bounds coordinates (RFC 7807 Error)
        res_bad_coord = await client.post(
            "/api/v1/grid/validate",
            json={
                "puzzle_id": puzzle_id,
                "row_index": 5,
                "col_index": 0,
                "player_id": "p-mahomes",
            },
        )
        assert res_bad_coord.status_code == 422 or res_bad_coord.status_code == 400

        # 3. Non-existent puzzle ID
        res_not_found = await client.post(
            "/api/v1/grid/validate",
            json={
                "puzzle_id": str(uuid.uuid4()),
                "row_index": 0,
                "col_index": 0,
                "player_id": "p-mahomes",
            },
        )
        assert res_not_found.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_daily_puzzle_auto_generation(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests that requesting today's daily puzzle automatically generates and precomputes
    a valid daily grid if none exists in the database.
    """
    app.dependency_overrides[get_async_session] = lambda: test_db_session
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/puzzles/grid/daily")
        assert res.status_code == 200
        data = res.json()
        assert data["game_type"] == "grid"
        assert len(data["puzzle_data"]["rows"]) == 3
        assert len(data["puzzle_data"]["columns"]) == 3
        assert "puzzle_id" in data
        assert "valid_solutions" not in data["puzzle_data"]  # Sanitized!

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_puzzle_pipeline_deterministic_generation(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests PuzzlePipelineService generates valid grid with solvability, log-density, and distributed locks.
    """
    from app.services.puzzle_pipeline import PuzzlePipelineService

    target_date = date(2026, 9, 15)

    # 1. Test Distributed Lock
    token = await PuzzlePipelineService.acquire_distributed_lock(
        redis_client=mock_redis,
        lock_key="puzzle:lock:grid:2026-09-15",
        timeout_secs=10,
    )
    assert token is not None

    # Secondary acquire attempt must fail while lock is held
    token_duplicate = await PuzzlePipelineService.acquire_distributed_lock(
        redis_client=mock_redis,
        lock_key="puzzle:lock:grid:2026-09-15",
        timeout_secs=10,
    )
    assert token_duplicate is None

    # Release lock
    released = await PuzzlePipelineService.release_distributed_lock(
        redis_client=mock_redis,
        lock_key="puzzle:lock:grid:2026-09-15",
        lock_token=token,
    )
    assert released is True

    # 2. Generate Grid Puzzle via Pipeline
    puzzle = await PuzzlePipelineService.generate_daily_grid(
        session=test_db_session,
        target_date=target_date,
        redis_client=mock_redis,
        k_min=1,
    )

    assert puzzle.target_date == target_date
    assert puzzle.game_type == "GRID"
    assert len(puzzle.puzzle_data["rows"]) == 3
    assert len(puzzle.puzzle_data["columns"]) == 3

    # Check dynamic template metadata
    assert "template_id" in puzzle.puzzle_data
    assert len(puzzle.puzzle_data["rows"]) == 3
    assert len(puzzle.puzzle_data["columns"]) == 3

    # Check precomputed solutions and cardinalities
    assert "valid_solutions" in puzzle.puzzle_data
    assert "cell_cardinalities" in puzzle.puzzle_data
    assert len(puzzle.puzzle_data["cell_cardinalities"]) == 3
    assert len(puzzle.puzzle_data["cell_cardinalities"][0]) == 3

    # Check Redis warming
    card_redis_key = f"puzzle:{puzzle.puzzle_id}:cell:0_0:cardinality"
    assert await mock_redis.exists(card_redis_key) == 1


# =====================================================================
# Unit & Integration Tests: End-of-Game Unrevealed Answers & Summary
# =====================================================================
@pytest.mark.asyncio
async def test_grid_summary_with_user_picks(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests that summary returns the player with highest pick percentage when submissions exist.
    """
    puzzle_id = str(uuid.uuid4())
    p1 = Player(
        player_id="00-0019596",
        full_name="Tom Brady",
        first_name="Tom",
        last_name="Brady",
        primary_position="QB",
        rookie_year=2000,
        draft_round=6,
        is_active=False,
    )
    p2 = Player(
        player_id="00-0023459",
        full_name="Aaron Rodgers",
        first_name="Aaron",
        last_name="Rodgers",
        primary_position="QB",
        rookie_year=2005,
        draft_round=1,
        is_active=True,
    )
    puzzle = DailyPuzzle(
        puzzle_id=uuid.UUID(puzzle_id),
        target_date=date(2026, 9, 12),
        game_type="GRID",
        puzzle_number=106,
        puzzle_data={
            "valid_solutions": {"0_0": ["00-0019596", "00-0023459"]},
            "cell_cardinalities": [[10]*3]*3,
        },
        solution_hash="hash_summary_1",
    )
    test_db_session.add_all([p1, p2, puzzle])
    await test_db_session.commit()

    # Simulate 100 total picks in cell 0_0: 70 for Tom Brady, 30 for Aaron Rodgers
    await mock_redis.set(f"puzzle:{puzzle_id}:cell:0_0:total", "100")
    await mock_redis.hincrby(f"puzzle:{puzzle_id}:cell:0_0:picks", "00-0019596", 70)
    await mock_redis.hincrby(f"puzzle:{puzzle_id}:cell:0_0:picks", "00-0023459", 30)

    summary = await GridValidationService.get_puzzle_summary(
        session=test_db_session,
        puzzle_id=puzzle_id,
        redis_client=mock_redis,
    )

    assert str(summary.puzzle_id) == puzzle_id
    assert "0_0" in summary.cell_solutions
    sol_0_0 = summary.cell_solutions["0_0"]
    assert sol_0_0.player_id == "00-0019596"
    assert sol_0_0.full_name == "Tom Brady"
    assert sol_0_0.pick_percentage == 70.0


@pytest.mark.asyncio
async def test_grid_summary_cold_start_fallback(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests cold-start fallback: when N(c) = 0, returns most prominent historical player (HOF / games started) with pick_percentage: null.
    """
    puzzle_id = str(uuid.uuid4())
    p_hof = Player(
        player_id="00-0010344",
        full_name="Brett Favre",
        first_name="Brett",
        last_name="Favre",
        primary_position="QB",
        rookie_year=1991,
        draft_round=2,
        is_active=False,
    )
    p_bench = Player(
        player_id="p-bench-01",
        full_name="Backup QB",
        first_name="Backup",
        last_name="QB",
        primary_position="QB",
        rookie_year=2020,
        draft_round=7,
        is_active=False,
    )
    f_gnb = Franchise(franchise_id="GNB", canonical_name="Green Bay Packers", established_year=1921)
    stint_hof = PlayerTeamStint(player_id="00-0010344", franchise_id="GNB", season_year=1995, games_played=16, games_started=16)
    stint_bench = PlayerTeamStint(player_id="p-bench-01", franchise_id="GNB", season_year=2020, games_played=2, games_started=0)

    puzzle = DailyPuzzle(
        puzzle_id=uuid.UUID(puzzle_id),
        target_date=date(2026, 9, 13),
        game_type="GRID",
        puzzle_number=107,
        puzzle_data={
            "valid_solutions": {"0_1": ["p-bench-01", "00-0010344"]},
            "cell_cardinalities": [[10]*3]*3,
        },
        solution_hash="hash_cold_1",
    )
    test_db_session.add_all([p_hof, p_bench, f_gnb, stint_hof, stint_bench, puzzle])
    await test_db_session.commit()

    # Call summary on cold start (0 submissions in Redis or DB)
    summary = await GridValidationService.get_puzzle_summary(
        session=test_db_session,
        puzzle_id=puzzle_id,
        redis_client=mock_redis,
    )

    sol_0_1 = summary.cell_solutions["0_1"]
    # Favre is HOF and started 16 games vs backup who started 0
    assert sol_0_1.full_name == "Brett Favre"
    assert sol_0_1.pick_percentage is None


@pytest.mark.asyncio
async def test_fastapi_grid_summary_and_surrender_endpoints(test_db_session: AsyncSession, mock_redis: MockRedis):
    """
    Tests FastAPI endpoints:
    - GET /api/v1/grid/puzzles/{puzzle_id}/summary
    - POST /api/v1/grid/surrender-reveal
    """
    puzzle_id = str(uuid.uuid4())
    player = Player(
        player_id="00-0033873",
        full_name="Patrick Mahomes",
        first_name="Patrick",
        last_name="Mahomes",
        primary_position="QB",
        rookie_year=2017,
        draft_round=1,
        is_active=True,
    )
    puzzle = DailyPuzzle(
        puzzle_id=uuid.UUID(puzzle_id),
        target_date=date(2026, 9, 14),
        game_type="GRID",
        puzzle_number=108,
        puzzle_data={
            "valid_solutions": {"0_0": ["00-0033873"]},
            "cell_cardinalities": [[10]*3]*3,
        },
        solution_hash="hash_endpoints_1",
    )
    test_db_session.add_all([player, puzzle])
    await test_db_session.commit()

    # Populate Redis total and pick
    await mock_redis.set(f"puzzle:{puzzle_id}:cell:0_0:total", "50")
    await mock_redis.hincrby(f"puzzle:{puzzle_id}:cell:0_0:picks", "00-0033873", 45)

    app.dependency_overrides[get_async_session] = lambda: test_db_session
    app.dependency_overrides[get_redis] = lambda: mock_redis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. GET /api/v1/grid/puzzles/{puzzle_id}/summary
        res = await client.get(f"/api/v1/grid/puzzles/{puzzle_id}/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["puzzle_id"] == puzzle_id
        assert "cell_solutions" in data
        assert "0_0" in data["cell_solutions"]
        assert data["cell_solutions"]["0_0"]["full_name"] == "Patrick Mahomes"
        assert data["cell_solutions"]["0_0"]["pick_percentage"] == 90.0

        # 2. POST /api/v1/grid/surrender-reveal
        res_surrender = await client.post(
            "/api/v1/grid/surrender-reveal",
            json={"puzzle_id": puzzle_id},
        )
        assert res_surrender.status_code == 200
        data_surrender = res_surrender.json()
        assert data_surrender["puzzle_id"] == puzzle_id
        assert data_surrender["cell_solutions"]["0_0"]["full_name"] == "Patrick Mahomes"

        # 3. GET /api/v1/puzzles/grid/daily (Anti-Cheat check: no solutions in daily payload)
        res_daily = await client.get("/api/v1/puzzles/grid/daily")
        assert res_daily.status_code == 200
        daily_data = res_daily.json()
        assert "cell_solutions" not in daily_data["puzzle_data"]
        assert "valid_solutions" not in daily_data["puzzle_data"]

    app.dependency_overrides.clear()



