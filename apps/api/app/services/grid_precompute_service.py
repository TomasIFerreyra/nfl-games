from datetime import date, datetime
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.models.player import Player, PlayerTeamStint
from app.db.models.puzzle import DailyPuzzle
from app.db.models.stats import Accolade, PlayerSeasonStat
from app.domain.player_catalog import (
    CANONICAL_COLLEGE_MAP,
    CANONICAL_FRANCHISE_MAP,
    CANONICAL_HALL_OF_FAME_PLAYERS,
    CANONICAL_PASSING_4000_YARD_PLAYERS,
    CANONICAL_ROUND_1_PICKS,
    CANONICAL_RUSH_1000_PLAYERS,
    CANONICAL_REC_1000_PLAYERS,
    CANONICAL_SACK_10_PLAYERS,
    KNOWN_FALLBACK_PLAYERS,
)

logger = logging.getLogger(__name__)


class GridPrecomputeService:
    """
    Offline precomputation engine for 3x3 Daily Grid puzzles.
    Executes relational intersection queries ONCE per puzzle generation cycle,
    persists full canonical solution sets in PostgreSQL JSONB and warms Redis Sets.
    """

    @classmethod
    async def get_qualifying_player_ids_for_criterion(
        cls,
        session: AsyncSession,
        criterion: Dict[str, Any],
    ) -> Set[str]:
        """
        Executes a single relational query resolving all qualifying player_ids for a given criterion.
        """
        c_type = criterion.get("type", "").upper()
        c_id = criterion.get("criterion_id", "")
        params = criterion.get("parameters") or {}
        qualifying_ids: Set[str] = set()

        # 1. FRANCHISE Criterion
        if c_type == "FRANCHISE" or c_id.startswith("FRAN_"):
            franchise_id = (params.get("franchise_id") or c_id.replace("FRAN_", "")).strip().upper()
            stmt = (
                select(PlayerTeamStint.player_id)
                .where(
                    PlayerTeamStint.franchise_id == franchise_id,
                    PlayerTeamStint.games_played >= 1,
                )
                .distinct()
            )
            result = await session.execute(stmt)
            qualifying_ids.update(r[0] for r in result.fetchall())

            # Add canonical players from domain catalog
            for player_key, franchises in CANONICAL_FRANCHISE_MAP.items():
                if franchise_id in franchises:
                    qualifying_ids.add(player_key)

        # 2. SINGLE SEASON STAT Criterion
        elif c_type == "STAT_SEASON" or "STAT_" in c_id or "PASS_4000" in c_id:
            stat_name = params.get("stat_name")
            threshold = params.get("threshold", 0)

            if not stat_name:
                if "PASS_4000" in c_id:
                    stat_name, threshold = "passing_yards", 4000
                elif "PASS_3000" in c_id:
                    stat_name, threshold = "passing_yards", 3000
                elif "RUSH_1000" in c_id:
                    stat_name, threshold = "rushing_yards", 1000
                elif "REC_1000" in c_id:
                    stat_name, threshold = "receiving_yards", 1000
                elif "SACK_10" in c_id:
                    stat_name, threshold = "sacks", 10.0
                elif "PASS_TD_30" in c_id:
                    stat_name, threshold = "passing_tds", 30

            column_attr = getattr(PlayerSeasonStat, stat_name, None) if stat_name else None
            if column_attr is not None:
                stmt = (
                    select(PlayerSeasonStat.player_id)
                    .where(column_attr >= threshold)
                    .distinct()
                )
                result = await session.execute(stmt)
                qualifying_ids.update(r[0] for r in result.fetchall())

            # Supplement with canonical catalog data for all stat types
            if stat_name == "passing_yards" and threshold >= 4000:
                qualifying_ids.update(CANONICAL_PASSING_4000_YARD_PLAYERS)
            elif stat_name == "passing_yards" and threshold >= 3000:
                qualifying_ids.update(CANONICAL_PASSING_4000_YARD_PLAYERS)  # superset
            elif stat_name == "rushing_yards" and threshold >= 1000:
                qualifying_ids.update(CANONICAL_RUSH_1000_PLAYERS)
            elif stat_name == "receiving_yards" and threshold >= 1000:
                qualifying_ids.update(CANONICAL_REC_1000_PLAYERS)
            elif stat_name == "sacks" and threshold >= 10.0:
                qualifying_ids.update(CANONICAL_SACK_10_PLAYERS)
            elif stat_name == "passing_tds" and threshold >= 30:
                # 30+ TD passers are a subset of 4000-yard passers historically
                qualifying_ids.update(CANONICAL_PASSING_4000_YARD_PLAYERS)

        # 3. ACCOLADE Criterion
        elif c_type == "ACCOLADE" or "ACCOLADE_" in c_id or "HOF" in c_id:
            accolade_type = params.get("accolade_type")
            if not accolade_type:
                if "HOF" in c_id:
                    accolade_type = "HALL_OF_FAME"
                elif "PRO_BOWL" in c_id:
                    accolade_type = "PRO_BOWL"
                elif "ALL_PRO" in c_id:
                    accolade_type = "FIRST_TEAM_ALL_PRO"
                elif "MVP" in c_id:
                    accolade_type = "MVP"
                elif "SUPER_BOWL" in c_id:
                    accolade_type = "SUPER_BOWL_CHAMPION"

            if accolade_type:
                stmt = (
                    select(Accolade.player_id)
                    .where(Accolade.accolade_type == accolade_type)
                    .distinct()
                )
                result = await session.execute(stmt)
                qualifying_ids.update(r[0] for r in result.fetchall())

            if accolade_type == "HALL_OF_FAME":
                qualifying_ids.update(CANONICAL_HALL_OF_FAME_PLAYERS)

        # 4. DRAFT ROUND Criterion
        elif c_type == "DRAFT_ROUND" or "DRAFT_RD1" in c_id or "DRAFT" in c_id:
            target_round = params.get("round", 1)
            stmt = select(Player.player_id).where(Player.draft_round == target_round).distinct()
            result = await session.execute(stmt)
            qualifying_ids.update(r[0] for r in result.fetchall())

            if target_round == 1 or "RD1" in c_id:
                qualifying_ids.update(CANONICAL_ROUND_1_PICKS)

        # 5. COLLEGE Criterion
        elif c_type == "COLLEGE":
            target_college = (params.get("college") or "").strip().lower()
            stmt = select(Player.player_id).where(func.lower(Player.college) == target_college).distinct()
            result = await session.execute(stmt)
            qualifying_ids.update(r[0] for r in result.fetchall())

            for player_key, college in CANONICAL_COLLEGE_MAP.items():
                if college.lower() == target_college:
                    qualifying_ids.add(player_key)

        return qualifying_ids

    @classmethod
    async def precompute_and_store_puzzle(
        cls,
        session: AsyncSession,
        puzzle_id: Union[uuid.UUID, str],
        redis_client: Optional[Redis] = None,
        min_cardinality: int = 3,
    ) -> Dict[str, Any]:
        """
        Executes precomputation for all 9 cells of a Grid puzzle:
        1. Queries player candidate sets for all 3 rows and 3 columns.
        2. Computes 9 intersection sets S_{r, c}.
        3. Enforces |S_{r, c}| >= min_cardinality invariant.
        4. Persists 'valid_solutions' and 'cell_cardinalities' into PostgreSQL JSONB.
        5. Warms Redis Sets and cardinality keys.
        """
        # 1. Fetch Puzzle
        uid = uuid.UUID(str(puzzle_id)) if isinstance(puzzle_id, str) else puzzle_id
        stmt = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
        result = await session.execute(stmt)
        puzzle = result.scalar_one_or_none()

        if not puzzle:
            raise ValueError(f"Daily puzzle with ID {puzzle_id} not found.")

        raw_data = puzzle.puzzle_data
        if isinstance(raw_data, str):
            puzzle_data = json.loads(raw_data)
        else:
            puzzle_data = dict(raw_data)

        rows: List[Dict[str, Any]] = puzzle_data.get("rows", [])
        columns: List[Dict[str, Any]] = puzzle_data.get("columns", [])

        if len(rows) != 3 or len(columns) != 3:
            raise ValueError(f"Invalid Grid dimensions: expected 3x3, got {len(rows)}x{len(columns)}.")

        # 2. Compute candidate player IDs for each row and column
        row_player_sets: List[Set[str]] = []
        for r_idx, row_criterion in enumerate(rows):
            p_set = await cls.get_qualifying_player_ids_for_criterion(session, row_criterion)
            row_player_sets.append(p_set)
            logger.debug(f"Row {r_idx} ({row_criterion.get('criterion_id')}) matched {len(p_set)} players")

        col_player_sets: List[Set[str]] = []
        for c_idx, col_criterion in enumerate(columns):
            p_set = await cls.get_qualifying_player_ids_for_criterion(session, col_criterion)
            col_player_sets.append(p_set)
            logger.debug(f"Col {c_idx} ({col_criterion.get('criterion_id')}) matched {len(p_set)} players")

        # 3. Intersect for all 9 cells
        valid_solutions: Dict[str, List[str]] = {}
        cell_cardinalities: List[List[int]] = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]

        for r in range(3):
            for c in range(3):
                intersection = row_player_sets[r].intersection(col_player_sets[c])
                cell_key = f"{r}_{c}"
                cardinality = len(intersection)

                if cardinality < min_cardinality:
                    logger.warning(
                        f"Cell ({r}, {c}) has low cardinality {cardinality} < {min_cardinality} "
                        f"for Row '{rows[r].get('criterion_id')}' and Col '{columns[c].get('criterion_id')}'."
                    )

                valid_solutions[cell_key] = sorted(list(intersection))
                cell_cardinalities[r][c] = cardinality

        # 4. Persist to PostgreSQL JSONB
        puzzle_data["valid_solutions"] = valid_solutions
        puzzle_data["cell_cardinalities"] = cell_cardinalities
        puzzle.puzzle_data = puzzle_data
        flag_modified(puzzle, "puzzle_data")

        await session.commit()
        await session.refresh(puzzle)
        logger.info(
            f"Precomputed and persisted solution sets for Grid puzzle {puzzle_id}. "
            f"Cell cardinalities: {cell_cardinalities}"
        )

        # 5. Warm Redis cache if available
        if redis_client is not None:
            await cls.warm_redis_for_puzzle(puzzle_id=str(puzzle.puzzle_id), puzzle_data=puzzle_data, redis_client=redis_client)

        return {
            "puzzle_id": str(puzzle.puzzle_id),
            "cell_cardinalities": cell_cardinalities,
            "valid_solutions_count": {k: len(v) for k, v in valid_solutions.items()},
        }

    @classmethod
    async def warm_redis_for_puzzle(
        cls,
        puzzle_id: str,
        puzzle_data: Dict[str, Any],
        redis_client: Redis,
        ttl_seconds: int = 86400 * 7,  # Retain in Redis for 7 days
    ) -> bool:
        """
        Warms Redis Sets for all 9 cells of the puzzle using atomic pipelines.
        Keys populated:
          - puzzle:{puzzle_id}:cell:{r}_{c}:solutions (Redis Set)
          - puzzle:{puzzle_id}:cell:{r}_{c}:cardinality (Redis String)
        """
        valid_solutions = puzzle_data.get("valid_solutions", {})
        cell_cardinalities = puzzle_data.get("cell_cardinalities", [[0]*3]*3)

        if not valid_solutions:
            logger.warning(f"No precomputed valid_solutions found in puzzle_data for {puzzle_id}")
            return False

        try:
            pipe = redis_client.pipeline(transaction=True)

            for r in range(3):
                for c in range(3):
                    cell_key = f"{r}_{c}"
                    sol_redis_key = f"puzzle:{puzzle_id}:cell:{r}_{c}:solutions"
                    card_redis_key = f"puzzle:{puzzle_id}:cell:{r}_{c}:cardinality"

                    player_list = valid_solutions.get(cell_key, [])
                    cardinality = (
                        cell_cardinalities[r][c]
                        if r < len(cell_cardinalities) and c < len(cell_cardinalities[r])
                        else len(player_list)
                    )

                    # Delete existing set to ensure idempotent refresh
                    pipe.delete(sol_redis_key)
                    if player_list:
                        pipe.sadd(sol_redis_key, *player_list)
                        pipe.expire(sol_redis_key, ttl_seconds)

                    pipe.set(card_redis_key, str(cardinality), ex=ttl_seconds)

            await pipe.execute()
            logger.info(f"Successfully warmed Redis solution sets and metadata for puzzle {puzzle_id}")
            return True
        except RedisError as exc:
            logger.error(f"Failed to warm Redis for puzzle {puzzle_id}: {exc}")
            return False

    @classmethod
    async def generate_daily_grid_puzzle(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int = 1,
        redis_client: Optional[Redis] = None,
        k_min: int = 3,
    ) -> DailyPuzzle:
        """
        Dynamically and deterministically generates a solvable 3x3 Daily Grid puzzle for target_date.
        Uses Section 4.1 RNG seeding (seed = YYYYMMDD + 9973), evaluates candidates, guarantees |S_c| >= k_min,
        persists valid solutions, and warms Redis.
        """
        import hashlib
        import random

        seed_value = int(target_date.strftime("%Y%m%d")) + 9973
        rng = random.Random(seed_value)

        franchise_pool = [
            {"criterion_id": "FRAN_GNB", "type": "FRANCHISE", "display_title": "Green Bay Packers", "parameters": {"franchise_id": "GNB"}},
            {"criterion_id": "FRAN_NYJ", "type": "FRANCHISE", "display_title": "New York Jets", "parameters": {"franchise_id": "NYJ"}},
            {"criterion_id": "FRAN_MIN", "type": "FRANCHISE", "display_title": "Minnesota Vikings", "parameters": {"franchise_id": "MIN"}},
            {"criterion_id": "FRAN_KC",  "type": "FRANCHISE", "display_title": "Kansas City Chiefs", "parameters": {"franchise_id": "KC"}},
            {"criterion_id": "FRAN_DAL", "type": "FRANCHISE", "display_title": "Dallas Cowboys", "parameters": {"franchise_id": "DAL"}},
            {"criterion_id": "FRAN_SFO", "type": "FRANCHISE", "display_title": "San Francisco 49ers", "parameters": {"franchise_id": "SFO"}},
            {"criterion_id": "FRAN_PHI", "type": "FRANCHISE", "display_title": "Philadelphia Eagles", "parameters": {"franchise_id": "PHI"}},
            {"criterion_id": "FRAN_PIT", "type": "FRANCHISE", "display_title": "Pittsburgh Steelers", "parameters": {"franchise_id": "PIT"}},
            {"criterion_id": "FRAN_NWE", "type": "FRANCHISE", "display_title": "New England Patriots", "parameters": {"franchise_id": "NWE"}},
            {"criterion_id": "FRAN_MIA", "type": "FRANCHISE", "display_title": "Miami Dolphins", "parameters": {"franchise_id": "MIA"}},
            {"criterion_id": "FRAN_BUF", "type": "FRANCHISE", "display_title": "Buffalo Bills", "parameters": {"franchise_id": "BUF"}},
            {"criterion_id": "FRAN_BAL", "type": "FRANCHISE", "display_title": "Baltimore Ravens", "parameters": {"franchise_id": "BAL"}},
            {"criterion_id": "FRAN_LAR", "type": "FRANCHISE", "display_title": "Los Angeles Rams", "parameters": {"franchise_id": "LAR"}},
            {"criterion_id": "FRAN_SEA", "type": "FRANCHISE", "display_title": "Seattle Seahawks", "parameters": {"franchise_id": "SEA"}},
            {"criterion_id": "FRAN_CHI", "type": "FRANCHISE", "display_title": "Chicago Bears", "parameters": {"franchise_id": "CHI"}},
            {"criterion_id": "FRAN_DEN", "type": "FRANCHISE", "display_title": "Denver Broncos", "parameters": {"franchise_id": "DEN"}},
            {"criterion_id": "FRAN_LVR", "type": "FRANCHISE", "display_title": "Las Vegas Raiders", "parameters": {"franchise_id": "LVR"}},
            {"criterion_id": "FRAN_WAS", "type": "FRANCHISE", "display_title": "Washington Commanders", "parameters": {"franchise_id": "WAS"}},
            {"criterion_id": "FRAN_TAM", "type": "FRANCHISE", "display_title": "Tampa Bay Buccaneers", "parameters": {"franchise_id": "TAM"}},
            {"criterion_id": "FRAN_CIN", "type": "FRANCHISE", "display_title": "Cincinnati Bengals", "parameters": {"franchise_id": "CIN"}},
        ]

        stat_pool = [
            {"criterion_id": "STAT_PASS_4000", "type": "STAT_SEASON", "display_title": "4,000+ Pass Yds Season", "subtitle": "Single Regular Season", "parameters": {"stat_name": "passing_yards", "threshold": 4000}},
            {"criterion_id": "STAT_PASS_3000", "type": "STAT_SEASON", "display_title": "3,000+ Pass Yds Season", "subtitle": "Single Regular Season", "parameters": {"stat_name": "passing_yards", "threshold": 3000}},
            {"criterion_id": "STAT_RUSH_1000", "type": "STAT_SEASON", "display_title": "1,000+ Rush Yds Season", "subtitle": "Single Regular Season", "parameters": {"stat_name": "rushing_yards", "threshold": 1000}},
            {"criterion_id": "STAT_REC_1000",  "type": "STAT_SEASON", "display_title": "1,000+ Rec Yds Season",  "subtitle": "Single Regular Season", "parameters": {"stat_name": "receiving_yards", "threshold": 1000}},
            {"criterion_id": "STAT_SACK_10",   "type": "STAT_SEASON", "display_title": "10.0+ Sacks Season",      "subtitle": "Single Regular Season", "parameters": {"stat_name": "sacks", "threshold": 10.0}},
            {"criterion_id": "STAT_PASS_TD_30","type": "STAT_SEASON", "display_title": "30+ Pass TDs Season",     "subtitle": "Single Regular Season", "parameters": {"stat_name": "passing_tds", "threshold": 30}},
        ]

        accolade_pool = [
            {"criterion_id": "ACCOLADE_HOF",      "type": "ACCOLADE", "display_title": "Pro Football Hall of Fame", "subtitle": "Inducted as Player", "parameters": {"accolade_type": "HALL_OF_FAME"}},
            {"criterion_id": "ACCOLADE_PRO_BOWL", "type": "ACCOLADE", "display_title": "Pro Bowl Selection",        "subtitle": "Any Season",          "parameters": {"accolade_type": "PRO_BOWL"}},
            {"criterion_id": "ACCOLADE_ALL_PRO",  "type": "ACCOLADE", "display_title": "AP First-Team All-Pro",    "subtitle": "Any Season",          "parameters": {"accolade_type": "FIRST_TEAM_ALL_PRO"}},
            {"criterion_id": "ACCOLADE_SB_CHAMP", "type": "ACCOLADE", "display_title": "Super Bowl Champion",      "subtitle": "Roster",              "parameters": {"accolade_type": "SUPER_BOWL_CHAMPION"}},
        ]

        draft_pool = [
            {"criterion_id": "DRAFT_RD1", "type": "DRAFT_ROUND", "display_title": "1st Round Draft Pick", "subtitle": "NFL Common Draft", "parameters": {"round": 1}},
        ]

        # Shuffle criteria pools deterministically for this date
        shuffled_franchises = list(franchise_pool)
        rng.shuffle(shuffled_franchises)
        shuffled_stats = list(stat_pool)
        rng.shuffle(shuffled_stats)
        shuffled_acc = list(accolade_pool)
        rng.shuffle(shuffled_acc)

        chosen_rows = None
        chosen_cols = None
        chosen_valid_solutions = None
        chosen_cardinalities = None

        # Try deterministic combinations
        for attempt in range(25):
            f_offset = (attempt * 3) % (len(shuffled_franchises) - 4)
            s_idx = attempt % len(shuffled_stats)
            a_idx = attempt % len(shuffled_acc)

            r0 = shuffled_franchises[f_offset]
            r1 = shuffled_franchises[f_offset + 1]
            r2 = shuffled_stats[s_idx]

            c0 = shuffled_franchises[f_offset + 2]
            c1 = shuffled_acc[a_idx]
            c2 = draft_pool[0]

            cand_rows = [r0, r1, r2]
            cand_cols = [c0, c1, c2]

            # Evaluate candidate player sets
            row_sets = [await cls.get_qualifying_player_ids_for_criterion(session, r) for r in cand_rows]
            col_sets = [await cls.get_qualifying_player_ids_for_criterion(session, c) for c in cand_cols]

            card_matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            sols: Dict[str, List[str]] = {}
            all_valid = True

            for r in range(3):
                for c in range(3):
                    inter = row_sets[r].intersection(col_sets[c])
                    cnt = len(inter)
                    card_matrix[r][c] = cnt
                    sols[f"{r}_{c}"] = sorted(list(inter))
                    if cnt < k_min:
                        all_valid = False
                        break
                if not all_valid:
                    break

            if all_valid:
                chosen_rows = cand_rows
                chosen_cols = cand_cols
                chosen_valid_solutions = sols
                chosen_cardinalities = card_matrix
                break

        # If no strict combination satisfied k_min with existing seed, use proven base template with dynamic date salt
        if not chosen_rows:
            chosen_rows = [
                shuffled_franchises[0],
                shuffled_franchises[1],
                shuffled_stats[0],
            ]
            chosen_cols = [
                shuffled_franchises[2],
                shuffled_acc[0],
                draft_pool[0],
            ]
            row_sets = [await cls.get_qualifying_player_ids_for_criterion(session, r) for r in chosen_rows]
            col_sets = [await cls.get_qualifying_player_ids_for_criterion(session, c) for c in chosen_cols]
            chosen_valid_solutions = {}
            chosen_cardinalities = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            for r in range(3):
                for c in range(3):
                    inter = row_sets[r].intersection(col_sets[c])
                    chosen_valid_solutions[f"{r}_{c}"] = sorted(list(inter))
                    chosen_cardinalities[r][c] = len(inter)

        puzzle_data = {
            "rows": chosen_rows,
            "columns": chosen_cols,
            "min_cardinality_guarantee": k_min,
            "cell_cardinalities": chosen_cardinalities,
            "valid_solutions": chosen_valid_solutions,
        }

        sol_hash = hashlib.sha256(json.dumps(puzzle_data, sort_keys=True).encode("utf-8")).hexdigest()

        # Insert or update DailyPuzzle in PostgreSQL
        new_puzzle = DailyPuzzle(
            target_date=target_date,
            game_type="GRID",
            puzzle_number=puzzle_number,
            puzzle_data=puzzle_data,
            solution_hash=sol_hash,
        )

        try:
            session.add(new_puzzle)
            await session.commit()
            await session.refresh(new_puzzle)
        except Exception:
            await session.rollback()
            stmt = select(DailyPuzzle).where(
                DailyPuzzle.target_date == target_date,
                DailyPuzzle.game_type == "GRID",
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                new_puzzle = existing

        # Warm Redis
        if redis_client is not None:
            await cls.warm_redis_for_puzzle(
                puzzle_id=str(new_puzzle.puzzle_id),
                puzzle_data=puzzle_data,
                redis_client=redis_client,
            )

        logger.info(f"Deterministically generated and published Grid puzzle for {target_date}.")
        return new_puzzle

