from datetime import date, datetime
import hashlib
import json
import logging
import math
import random
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.puzzle import DailyPuzzle
from app.services.grid_precompute_service import GridPrecomputeService

logger = logging.getLogger(__name__)

PUZZLE_START_DATE = date(2026, 9, 1)

FRANCHISE_POOL: List[Dict[str, Any]] = [
    {"criterion_id": "FRAN_ARI", "type": "FRANCHISE", "display_title": "Arizona Cardinals", "parameters": {"franchise_id": "ARI"}},
    {"criterion_id": "FRAN_ATL", "type": "FRANCHISE", "display_title": "Atlanta Falcons", "parameters": {"franchise_id": "ATL"}},
    {"criterion_id": "FRAN_BAL", "type": "FRANCHISE", "display_title": "Baltimore Ravens", "parameters": {"franchise_id": "BAL"}},
    {"criterion_id": "FRAN_BUF", "type": "FRANCHISE", "display_title": "Buffalo Bills", "parameters": {"franchise_id": "BUF"}},
    {"criterion_id": "FRAN_CAR", "type": "FRANCHISE", "display_title": "Carolina Panthers", "parameters": {"franchise_id": "CAR"}},
    {"criterion_id": "FRAN_CHI", "type": "FRANCHISE", "display_title": "Chicago Bears", "parameters": {"franchise_id": "CHI"}},
    {"criterion_id": "FRAN_CIN", "type": "FRANCHISE", "display_title": "Cincinnati Bengals", "parameters": {"franchise_id": "CIN"}},
    {"criterion_id": "FRAN_CLE", "type": "FRANCHISE", "display_title": "Cleveland Browns", "parameters": {"franchise_id": "CLE"}},
    {"criterion_id": "FRAN_DAL", "type": "FRANCHISE", "display_title": "Dallas Cowboys", "parameters": {"franchise_id": "DAL"}},
    {"criterion_id": "FRAN_DEN", "type": "FRANCHISE", "display_title": "Denver Broncos", "parameters": {"franchise_id": "DEN"}},
    {"criterion_id": "FRAN_DET", "type": "FRANCHISE", "display_title": "Detroit Lions", "parameters": {"franchise_id": "DET"}},
    {"criterion_id": "FRAN_GNB", "type": "FRANCHISE", "display_title": "Green Bay Packers", "parameters": {"franchise_id": "GNB"}},
    {"criterion_id": "FRAN_HOU", "type": "FRANCHISE", "display_title": "Houston Texans", "parameters": {"franchise_id": "HOU"}},
    {"criterion_id": "FRAN_IND", "type": "FRANCHISE", "display_title": "Indianapolis Colts", "parameters": {"franchise_id": "IND"}},
    {"criterion_id": "FRAN_JAX", "type": "FRANCHISE", "display_title": "Jacksonville Jaguars", "parameters": {"franchise_id": "JAX"}},
    {"criterion_id": "FRAN_KC",  "type": "FRANCHISE", "display_title": "Kansas City Chiefs", "parameters": {"franchise_id": "KC"}},
    {"criterion_id": "FRAN_LAC", "type": "FRANCHISE", "display_title": "Los Angeles Chargers", "parameters": {"franchise_id": "LAC"}},
    {"criterion_id": "FRAN_LAR", "type": "FRANCHISE", "display_title": "Los Angeles Rams", "parameters": {"franchise_id": "LAR"}},
    {"criterion_id": "FRAN_LVR", "type": "FRANCHISE", "display_title": "Las Vegas Raiders", "parameters": {"franchise_id": "LVR"}},
    {"criterion_id": "FRAN_MIA", "type": "FRANCHISE", "display_title": "Miami Dolphins", "parameters": {"franchise_id": "MIA"}},
    {"criterion_id": "FRAN_MIN", "type": "FRANCHISE", "display_title": "Minnesota Vikings", "parameters": {"franchise_id": "MIN"}},
    {"criterion_id": "FRAN_NE",  "type": "FRANCHISE", "display_title": "New England Patriots", "parameters": {"franchise_id": "NE"}},
    {"criterion_id": "FRAN_NOR", "type": "FRANCHISE", "display_title": "New Orleans Saints", "parameters": {"franchise_id": "NOR"}},
    {"criterion_id": "FRAN_NYG", "type": "FRANCHISE", "display_title": "New York Giants", "parameters": {"franchise_id": "NYG"}},
    {"criterion_id": "FRAN_NYJ", "type": "FRANCHISE", "display_title": "New York Jets", "parameters": {"franchise_id": "NYJ"}},
    {"criterion_id": "FRAN_PHI", "type": "FRANCHISE", "display_title": "Philadelphia Eagles", "parameters": {"franchise_id": "PHI"}},
    {"criterion_id": "FRAN_PIT", "type": "FRANCHISE", "display_title": "Pittsburgh Steelers", "parameters": {"franchise_id": "PIT"}},
    {"criterion_id": "FRAN_SEA", "type": "FRANCHISE", "display_title": "Seattle Seahawks", "parameters": {"franchise_id": "SEA"}},
    {"criterion_id": "FRAN_SFO", "type": "FRANCHISE", "display_title": "San Francisco 49ers", "parameters": {"franchise_id": "SFO"}},
    {"criterion_id": "FRAN_TAM", "type": "FRANCHISE", "display_title": "Tampa Bay Buccaneers", "parameters": {"franchise_id": "TAM"}},
    {"criterion_id": "FRAN_TEN", "type": "FRANCHISE", "display_title": "Tennessee Titans", "parameters": {"franchise_id": "TEN"}},
    {"criterion_id": "FRAN_WAS", "type": "FRANCHISE", "display_title": "Washington Commanders", "parameters": {"franchise_id": "WAS"}},
]

STAT_POOL: List[Dict[str, Any]] = [
    {"criterion_id": "STAT_PASS_4000", "type": "STAT_SEASON", "display_title": "4,000+ Pass Yds Season", "subtitle": "Single Regular Season", "parameters": {"stat_name": "passing_yards", "threshold": 4000}},
    {"criterion_id": "STAT_PASS_3000", "type": "STAT_SEASON", "display_title": "3,000+ Pass Yds Season", "subtitle": "Single Regular Season", "parameters": {"stat_name": "passing_yards", "threshold": 3000}},
    {"criterion_id": "STAT_RUSH_1000", "type": "STAT_SEASON", "display_title": "1,000+ Rush Yds Season", "subtitle": "Single Regular Season", "parameters": {"stat_name": "rushing_yards", "threshold": 1000}},
    {"criterion_id": "STAT_REC_1000",  "type": "STAT_SEASON", "display_title": "1,000+ Rec Yds Season",  "subtitle": "Single Regular Season", "parameters": {"stat_name": "receiving_yards", "threshold": 1000}},
    {"criterion_id": "STAT_SACK_10",   "type": "STAT_SEASON", "display_title": "10.0+ Sacks Season",      "subtitle": "Single Regular Season", "parameters": {"stat_name": "sacks", "threshold": 10.0}},
    {"criterion_id": "STAT_PASS_TD_30","type": "STAT_SEASON", "display_title": "30+ Pass TDs Season",     "subtitle": "Single Regular Season", "parameters": {"stat_name": "passing_tds", "threshold": 30}},
]

ACCOLADE_POOL: List[Dict[str, Any]] = [
    {"criterion_id": "ACCOLADE_HOF",      "type": "ACCOLADE", "display_title": "Pro Football Hall of Fame", "subtitle": "Inducted as Player", "parameters": {"accolade_type": "HALL_OF_FAME"}},
    {"criterion_id": "ACCOLADE_PRO_BOWL", "type": "ACCOLADE", "display_title": "Pro Bowl Selection",        "subtitle": "Any Season",          "parameters": {"accolade_type": "PRO_BOWL"}},
    {"criterion_id": "ACCOLADE_ALL_PRO",  "type": "ACCOLADE", "display_title": "AP First-Team All-Pro",    "subtitle": "Any Season",          "parameters": {"accolade_type": "FIRST_TEAM_ALL_PRO"}},
    {"criterion_id": "ACCOLADE_SB_CHAMP", "type": "ACCOLADE", "display_title": "Super Bowl Champion",      "subtitle": "Roster",              "parameters": {"accolade_type": "SUPER_BOWL_CHAMPION"}},
]

DRAFT_POOL: List[Dict[str, Any]] = [
    {"criterion_id": "DRAFT_RD1", "type": "DRAFT_ROUND", "display_title": "1st Round Draft Pick", "subtitle": "NFL Common Draft", "parameters": {"round": 1}},
]


class PuzzlePipelineService:
    """
    Orchestrates deterministic batch generation and Just-In-Time (JIT) lazy puzzle compilation.
    Adheres strictly to SPECIFICATION.md Section 4.1 (solvability >= 3, log-density [12.0, 22.0]).
    """

    @classmethod
    def compute_solution_hash(cls, payload: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 hash for puzzle verification."""
        canonical_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def calculate_puzzle_number(cls, target_date: date) -> int:
        """Calculates monotonic puzzle sequence number from epoch."""
        delta = (target_date - PUZZLE_START_DATE).days
        return max(1, delta + 1)

    @classmethod
    def calculate_log_density(cls, cell_cardinalities: List[List[int]]) -> float:
        """
        Computes total log-density: D = sum_{r, c} log10(|S_{r, c}|)
        """
        total_density = 0.0
        for r in range(3):
            for c in range(3):
                val = cell_cardinalities[r][c]
                if val <= 0:
                    return 0.0
                total_density += math.log10(val)
        return round(total_density, 2)

    @classmethod
    async def generate_daily_grid(
        cls,
        session: AsyncSession,
        target_date: date,
        redis_client: Optional[Redis] = None,
        k_min: int = 3,
        max_attempts: int = 50,
    ) -> DailyPuzzle:
        """
        Generates, validates, and persists a 3x3 Grid puzzle for the target date:
        1. Seeded deterministically: seed = YYYYMMDD + 9973.
        2. Dynamic weighted templates with rotation memory & anti-clash verification.
        3. Solvability invariant: |S_{r, c}| >= k_min for all 9 cells.
        4. Log-density invariant: D in [12.0, 22.0].
        5. Persists precomputed solutions and cardinalities to PostgreSQL & warms Redis.
        """
        start_time = time.perf_counter()
        from app.domain.rotation_tracker import RotationTracker
        from app.domain.grid_generator import GridGenerator

        # Fetch recent 14 days of puzzles to load rotation memory
        tracker = RotationTracker()
        try:
            recent_stmt = (
                select(DailyPuzzle)
                .where(DailyPuzzle.game_type == "GRID")
                .order_by(DailyPuzzle.target_date.desc())
                .limit(14)
            )
            recent_res = await session.execute(recent_stmt)
            recent_puzzles = recent_res.scalars().all()
            tracker.load_from_puzzles(recent_puzzles)
        except Exception as exc:
            logger.warning(f"Could not load recent puzzle history for rotation tracker: {exc}")

        puzzle_number = cls.calculate_puzzle_number(target_date)

        chosen_puzzle_data = await GridGenerator.generate_puzzle_data(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
            k_min=k_min,
            max_attempts=max_attempts,
            rotation_tracker=tracker,
        )

        sol_hash = cls.compute_solution_hash(chosen_puzzle_data)
        puzzle_number = cls.calculate_puzzle_number(target_date)

        # Upsert into PostgreSQL
        stmt = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "GRID",
        )
        result = await session.execute(stmt)
        puzzle = result.scalar_one_or_none()

        if puzzle:
            puzzle.puzzle_data = chosen_puzzle_data
            puzzle.solution_hash = sol_hash
            puzzle.puzzle_number = puzzle_number
        else:
            puzzle = DailyPuzzle(
                target_date=target_date,
                game_type="GRID",
                puzzle_number=puzzle_number,
                puzzle_data=chosen_puzzle_data,
                solution_hash=sol_hash,
            )
            session.add(puzzle)

        await session.commit()
        await session.refresh(puzzle)

        # Warm Redis cache
        if redis_client is not None:
            await GridPrecomputeService.warm_redis_for_puzzle(
                puzzle_id=str(puzzle.puzzle_id),
                puzzle_data=chosen_puzzle_data,
                redis_client=redis_client,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Pipeline generated Grid Puzzle #{puzzle_number} for {target_date} "
            f"in {duration_ms:.2f}ms (Template: {chosen_puzzle_data.get('template_id')}, Log-Density: {chosen_puzzle_data.get('log_density')})."
        )
        return puzzle

    @classmethod
    async def generate_daily_connections(
        cls,
        session: AsyncSession,
        target_date: date,
        max_attempts: int = 50,
    ) -> DailyPuzzle:
        """
        Generates, validates, and persists a Connections 4x4 puzzle for the target date.
        Uses Knuth's Algorithm X exact cover solver to guarantee strictly one unique partition.
        """
        start_time = time.perf_counter()
        from app.domain.connections_generator import ConnectionsGenerator

        puzzle_number = cls.calculate_puzzle_number(target_date)
        chosen_puzzle_data = await ConnectionsGenerator.generate_puzzle_data(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
            max_attempts=max_attempts,
        )

        sol_hash = cls.compute_solution_hash(chosen_puzzle_data)

        # Upsert into PostgreSQL
        stmt = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "CONNECTIONS",
        )
        result = await session.execute(stmt)
        puzzle = result.scalar_one_or_none()

        if puzzle:
            puzzle.puzzle_data = chosen_puzzle_data
            puzzle.solution_hash = sol_hash
            puzzle.puzzle_number = puzzle_number
        else:
            puzzle = DailyPuzzle(
                target_date=target_date,
                game_type="CONNECTIONS",
                puzzle_number=puzzle_number,
                puzzle_data=chosen_puzzle_data,
                solution_hash=sol_hash,
            )
            session.add(puzzle)

        await session.commit()
        await session.refresh(puzzle)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Pipeline generated Connections Puzzle #{puzzle_number} for {target_date} in {duration_ms:.2f}ms."
        )
        return puzzle

    @classmethod
    async def generate_daily_top10(
        cls,
        session: AsyncSession,
        target_date: date,
    ) -> DailyPuzzle:
        """
        Generates, validates, and persists a Top 10 Leaderboard puzzle for the target date.
        """
        start_time = time.perf_counter()
        from app.domain.top10_generator import Top10Generator

        puzzle_number = cls.calculate_puzzle_number(target_date)
        chosen_puzzle_data = await Top10Generator.generate_puzzle_data(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
        )

        sol_hash = cls.compute_solution_hash(chosen_puzzle_data)

        # Upsert into PostgreSQL
        stmt = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "TOP10",
        )
        result = await session.execute(stmt)
        puzzle = result.scalar_one_or_none()

        if puzzle:
            puzzle.puzzle_data = chosen_puzzle_data
            puzzle.solution_hash = sol_hash
            puzzle.puzzle_number = puzzle_number
        else:
            puzzle = DailyPuzzle(
                target_date=target_date,
                game_type="TOP10",
                puzzle_number=puzzle_number,
                puzzle_data=chosen_puzzle_data,
                solution_hash=sol_hash,
            )
            session.add(puzzle)

        await session.commit()
        await session.refresh(puzzle)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Pipeline generated Top 10 Puzzle #{puzzle_number} for {target_date} in {duration_ms:.2f}ms."
        )
        return puzzle

    @classmethod
    async def generate_daily_weddle(
        cls,
        session: AsyncSession,
        target_date: date,
    ) -> DailyPuzzle:
        """
        Generates and persists the daily 'Guess the Player' (Weddle) mystery puzzle record.
        Deterministic seed: seed = YYYYMMDD + 5503.
        """
        from app.services.weddle_service import WeddleService

        start_time = time.perf_counter()
        puzzle_number = cls.calculate_puzzle_number(target_date)

        target_player = WeddleService.select_daily_target(target_date)
        puzzle_data = {
            "mode": "weddle",
            "target_player_id": target_player.player_id,
            "target_player_name": target_player.full_name,
            "max_attempts": 6,
            "attributes_count": 8,
        }

        sol_hash = cls.compute_solution_hash(puzzle_data)

        stmt = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "WEDDLE",
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.puzzle_data = puzzle_data
            existing.solution_hash = sol_hash
            existing.puzzle_number = puzzle_number
            puzzle = existing
        else:
            puzzle = DailyPuzzle(
                target_date=target_date,
                game_type="WEDDLE",
                puzzle_number=puzzle_number,
                puzzle_data=puzzle_data,
                solution_hash=sol_hash,
            )
            session.add(puzzle)

        await session.commit()
        await session.refresh(puzzle)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Pipeline generated Weddle Puzzle #{puzzle_number} for {target_date} in {duration_ms:.2f}ms."
        )
        return puzzle

    @classmethod
    async def ensure_daily_puzzles(
        cls,
        session: AsyncSession,
        target_date: Optional[date] = None,
        redis_client: Optional[Redis] = None,
    ) -> Dict[str, DailyPuzzle]:
        """
        Checks that all daily puzzles for target_date (defaulting to current UTC date) exist.
        If any are missing, generates and commits them to the database immediately.
        """
        if target_date is None:
            target_date = datetime.now(datetime.UTC).date() if hasattr(datetime, "UTC") else datetime.utcnow().date()

        puzzles_map: Dict[str, DailyPuzzle] = {}

        # 1. Ensure GRID puzzle
        stmt_grid = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "GRID",
        )
        grid_res = (await session.execute(stmt_grid)).scalar_one_or_none()
        if not grid_res:
            try:
                grid_res = await cls.generate_daily_grid(
                    session=session,
                    target_date=target_date,
                    redis_client=redis_client,
                )
                logger.info(f"Startup check: Generated missing GRID puzzle for {target_date}.")
            except Exception as exc:
                logger.error(f"Failed to auto-generate GRID puzzle on startup: {exc}", exc_info=True)
        if grid_res:
            puzzles_map["GRID"] = grid_res

        # 2. Ensure CONNECTIONS puzzle
        stmt_conn = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "CONNECTIONS",
        )
        conn_res = (await session.execute(stmt_conn)).scalar_one_or_none()
        if not conn_res:
            try:
                conn_res = await cls.generate_daily_connections(
                    session=session,
                    target_date=target_date,
                )
                logger.info(f"Startup check: Generated missing CONNECTIONS puzzle for {target_date}.")
            except Exception as exc:
                logger.error(f"Failed to auto-generate CONNECTIONS puzzle on startup: {exc}", exc_info=True)
        if conn_res:
            puzzles_map["CONNECTIONS"] = conn_res

        # 3. Ensure TOP10 puzzle
        stmt_top10 = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "TOP10",
        )
        top10_res = (await session.execute(stmt_top10)).scalar_one_or_none()
        if not top10_res:
            try:
                top10_res = await cls.generate_daily_top10(
                    session=session,
                    target_date=target_date,
                )
                logger.info(f"Startup check: Generated missing TOP10 puzzle for {target_date}.")
            except Exception as exc:
                logger.error(f"Failed to auto-generate TOP10 puzzle on startup: {exc}", exc_info=True)
        if top10_res:
            puzzles_map["TOP10"] = top10_res

        # 4. Ensure WEDDLE puzzle
        stmt_weddle = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "WEDDLE",
        )
        weddle_res = (await session.execute(stmt_weddle)).scalar_one_or_none()
        if not weddle_res:
            try:
                weddle_res = await cls.generate_daily_weddle(
                    session=session,
                    target_date=target_date,
                )
                logger.info(f"Startup check: Generated missing WEDDLE puzzle for {target_date}.")
            except Exception as exc:
                logger.error(f"Failed to auto-generate WEDDLE puzzle on startup: {exc}", exc_info=True)
        if weddle_res:
            puzzles_map["WEDDLE"] = weddle_res

        return puzzles_map


    @classmethod
    async def acquire_distributed_lock(
        cls,
        redis_client: Optional[Redis],
        lock_key: str,
        timeout_secs: int = 30,
    ) -> Optional[str]:
        """
        Acquires a distributed lock using Redis SET with NX and EX flags.
        Returns lock token if acquired, or None if unavailable.
        """
        if redis_client is None:
            return None
        token = str(uuid.uuid4())
        try:
            acquired = await redis_client.set(lock_key, token, ex=timeout_secs, nx=True)
            return token if acquired else None
        except (RedisError, OSError) as exc:
            logger.warning(f"Redis distributed lock acquire error: {exc}")
            return None

    @classmethod
    async def release_distributed_lock(
        cls,
        redis_client: Optional[Redis],
        lock_key: str,
        lock_token: Optional[str],
    ) -> bool:
        """
        Releases the distributed lock using a Lua script to ensure atomicity.
        """
        if redis_client is None or lock_token is None:
            return False
        lua_release = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
        """
        try:
            res = await redis_client.eval(lua_release, 1, lock_key, lock_token)
            return bool(res)
        except (RedisError, OSError) as exc:
            logger.warning(f"Redis distributed lock release error: {exc}")
            return False

