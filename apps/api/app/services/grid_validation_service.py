import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player
from app.db.models.puzzle import AggregatedAnswerStats, DailyPuzzle
from app.domain.player_catalog import CANONICAL_ROUND_1_PICKS, KNOWN_FALLBACK_PLAYERS
from app.schemas.grid import GridValidateResponse
from app.schemas.player import PlayerSummary
from app.services.grid_precompute_service import GridPrecomputeService

logger = logging.getLogger(__name__)


class GridValidationService:
    """
    High-throughput, real-time O(1) validation service for 3x3 Daily Grid puzzles.
    Uses Redis asynchronous Set operations for sub-15ms validation and atomic rarity counters,
    with automatic failover to PostgreSQL JSONB precomputed solutions.
    """

    M_PRIOR_WEIGHT: int = 25  # Calibrated Bayesian pseudo-observations parameter

    @classmethod
    def calculate_bayesian_rarity(
        cls,
        player_picks: int,
        total_picks: int,
        possible_answers_count: int,
    ) -> float:
        """
        Calculates smoothed Bayesian rarity score:
        R*(p, c) = [(n(p, c) + M * pi(p, c)) / (N(c) + M)] * 100
        where M = 25 and pi(p, c) = 1 / |S_c|.
        """
        k_possible = max(possible_answers_count, 1)
        prior_pi = 1.0 / k_possible
        m = cls.M_PRIOR_WEIGHT

        raw_rarity = ((player_picks + m * prior_pi) / (total_picks + m)) * 100.0
        # Clamp between 0.01% and 100.00% and round to 2 decimal places
        return max(0.01, min(100.0, round(raw_rarity, 2)))

    @classmethod
    async def resolve_player_summary(
        cls,
        session: AsyncSession,
        player_id: str,
        redis_client: Optional[Redis] = None,
    ) -> PlayerSummary:
        """
        Retrieves player metadata (name, position, headshot) with Redis caching.
        """
        clean_id = (player_id or "").strip()
        player_meta_key = f"player:{clean_id}:summary"

        # 1. Check Redis Cache
        if redis_client is not None:
            try:
                cached_meta = await redis_client.get(player_meta_key)
                if cached_meta:
                    data = json.loads(cached_meta)
                    return PlayerSummary(**data)
            except (RedisError, Exception) as exc:
                logger.debug(f"Redis player cache miss/error: {exc}")

        # 2. Query PostgreSQL Database
        stmt = select(Player).where(
            or_(
                Player.player_id == clean_id,
                Player.gsis_id == clean_id,
                Player.pfr_id == clean_id,
            )
        )
        result = await session.execute(stmt)
        player = result.scalar_one_or_none()

        if player:
            summary = PlayerSummary(
                player_id=player.player_id,
                full_name=player.full_name,
                position=player.primary_position,
                headshot_url=player.headshot_url,
            )
        else:
            # 3. Check fallback catalog
            fb = KNOWN_FALLBACK_PLAYERS.get(clean_id)
            if fb:
                summary = PlayerSummary(
                    player_id=clean_id,
                    full_name=fb.get("name", clean_id),
                    position=fb.get("position", "ATH"),
                    headshot_url=None,
                )
            else:
                clean_name = (
                    clean_id
                    .replace("draft2024-", "")
                    .replace("draft2025-", "")
                    .replace("draft2026-", "")
                    .replace("p-", "")
                    .replace("-", " ")
                    .title()
                )
                summary = PlayerSummary(
                    player_id=clean_id,
                    full_name=clean_name if clean_name else clean_id,
                    position="ATH",
                    headshot_url=None,
                )

        # 4. Cache in Redis
        if redis_client is not None:
            try:
                await redis_client.set(
                    player_meta_key,
                    json.dumps(summary.model_dump()),
                    ex=86400 * 3,  # 3 days TTL
                )
            except (RedisError, Exception):
                pass

        return summary

    @classmethod
    async def validate_guess(
        cls,
        session: AsyncSession,
        puzzle_id: Union[uuid.UUID, str],
        row_index: int,
        col_index: int,
        player_id: str,
        redis_client: Optional[Redis] = None,
    ) -> GridValidateResponse:
        """
        High-performance O(1) membership validation and atomic Bayesian scoring.
        """
        str_puzzle_id = str(puzzle_id)
        cell_key = f"{row_index}_{col_index}"
        cell_identifier = f"r{row_index}_c{col_index}"
        sol_redis_key = f"puzzle:{str_puzzle_id}:cell:{cell_key}:solutions"
        total_redis_key = f"puzzle:{str_puzzle_id}:cell:{cell_key}:total"
        picks_redis_key = f"puzzle:{str_puzzle_id}:cell:{cell_key}:picks"
        card_redis_key = f"puzzle:{str_puzzle_id}:cell:{cell_key}:cardinality"

        is_valid: bool = False
        possible_count: int = 10
        total_picks: int = 1
        player_picks: int = 1
        rarity_score: float = 100.0

        # Retrieve player summary for response
        player_summary = await cls.resolve_player_summary(session, player_id, redis_client)

        # -------------------------------------------------------------
        # 1. Primary Path: Redis O(1) SISMEMBER Check
        # -------------------------------------------------------------
        redis_available = False
        if redis_client is not None:
            try:
                # Check if solution set exists in Redis
                set_exists = await redis_client.exists(sol_redis_key)
                if set_exists:
                    redis_available = True
                    is_valid = bool(await redis_client.sismember(sol_redis_key, player_id))
                    # Also retrieve cached cardinality
                    cached_card = await redis_client.get(card_redis_key)
                    if cached_card:
                        possible_count = int(cached_card)
                else:
                    # Key missing in Redis -> attempt cache warming from PostgreSQL
                    logger.info(f"Redis cache miss for key {sol_redis_key}. Attempting auto-warm from DB.")
            except (RedisError, OSError) as exc:
                logger.warning(f"Redis error during SISMEMBER check: {exc}. Falling back to PostgreSQL.")
                redis_available = False

        # -------------------------------------------------------------
        # 2. Fallback Path: PostgreSQL JSONB Lookup
        # -------------------------------------------------------------
        if not redis_available:
            puzzle = None
            is_valid_uuid = False
            try:
                uid = uuid.UUID(str_puzzle_id) if isinstance(puzzle_id, str) else puzzle_id
                is_valid_uuid = True
                stmt = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
                result = await session.execute(stmt)
                puzzle = result.scalar_one_or_none()
            except (ValueError, TypeError, AttributeError):
                is_valid_uuid = False

            if not puzzle and not is_valid_uuid:
                # If non-UUID string was passed (e.g., 'demo-grid-001' or date string), attempt latest active grid
                stmt = (
                    select(DailyPuzzle)
                    .where(DailyPuzzle.game_type == "GRID")
                    .order_by(DailyPuzzle.target_date.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                puzzle = result.scalar_one_or_none()

            if not puzzle or puzzle.game_type != "GRID":
                raise ValueError(f"Valid 3x3 Grid puzzle not found for puzzle_id: '{str_puzzle_id}'")

            raw_data = puzzle.puzzle_data
            puzzle_data = json.loads(raw_data) if isinstance(raw_data, str) else dict(raw_data)
            valid_solutions = puzzle_data.get("valid_solutions")

            # If puzzle_data lacks precomputed solutions, compute and persist them
            if not valid_solutions:
                logger.info(f"Puzzle {str_puzzle_id} has uncomputed solutions. Running precomputation.")
                precompute_res = await GridPrecomputeService.precompute_and_store_puzzle(
                    session=session,
                    puzzle_id=puzzle.puzzle_id,
                    redis_client=redis_client,
                )
                await session.refresh(puzzle)
                raw_data = puzzle.puzzle_data
                puzzle_data = json.loads(raw_data) if isinstance(raw_data, str) else dict(raw_data)
                valid_solutions = puzzle_data.get("valid_solutions", {})

            cell_solutions = set(valid_solutions.get(cell_key, []))
            is_valid = (player_id in cell_solutions)

            cardinalities = puzzle_data.get("cell_cardinalities", [[10]*3]*3)
            if row_index < len(cardinalities) and col_index < len(cardinalities[row_index]):
                possible_count = cardinalities[row_index][col_index]
            else:
                possible_count = len(cell_solutions) or 10

            # If Redis is active now, warm it up for subsequent requests
            if redis_client is not None:
                try:
                    await GridPrecomputeService.warm_redis_for_puzzle(
                        puzzle_id=str_puzzle_id,
                        puzzle_data=puzzle_data,
                        redis_client=redis_client,
                    )
                except Exception as exc:
                    logger.debug(f"Failed to lazily warm Redis: {exc}")

        # -------------------------------------------------------------
        # 3. Handle Incorrect Guess
        # -------------------------------------------------------------
        if not is_valid:
            return GridValidateResponse(
                is_valid=False,
                row_index=row_index,
                col_index=col_index,
                player=player_summary,
                failed_criteria=["GRID_CRITERIA_MISMATCH"],
                reason="Player does not satisfy the intersecting row and column criteria.",
            )

        # -------------------------------------------------------------
        # 4. Handle Correct Guess: Atomic Counters & Bayesian Scoring
        # -------------------------------------------------------------
        if redis_client is not None:
            try:
                # Pipeline atomic counter increments: INCR total, HINCRBY picks
                pipe = redis_client.pipeline(transaction=True)
                pipe.incr(total_redis_key)
                pipe.hincrby(picks_redis_key, player_id, 1)
                pipe_res = await pipe.execute()

                total_picks = int(pipe_res[0])
                player_picks = int(pipe_res[1])
            except (RedisError, OSError) as exc:
                logger.warning(f"Redis counter increment failed: {exc}. Falling back to DB counters.")
                total_picks, player_picks = await cls._increment_db_counters(
                    session=session,
                    puzzle_id=str_puzzle_id,
                    cell_identifier=cell_identifier,
                    player_id=player_id,
                )
        else:
            total_picks, player_picks = await cls._increment_db_counters(
                session=session,
                puzzle_id=str_puzzle_id,
                cell_identifier=cell_identifier,
                player_id=player_id,
            )

        # Calculate Bayesian Rarity
        rarity_score = cls.calculate_bayesian_rarity(
            player_picks=player_picks,
            total_picks=total_picks,
            possible_answers_count=possible_count,
        )

        # -------------------------------------------------------------
        # 5. Buffer / Synchronize Aggregated Stats to PostgreSQL
        # -------------------------------------------------------------
        try:
            await cls._sync_stats_to_db(
                session=session,
                puzzle_id=str_puzzle_id,
                cell_identifier=cell_identifier,
                player_id=player_id,
                selection_count=player_picks,
                pick_percentage=rarity_score,
            )
            await session.commit()
        except Exception as exc:
            logger.warning(f"Aggregated stats sync to PostgreSQL failed: {exc}")
            await session.rollback()

        return GridValidateResponse(
            is_valid=True,
            row_index=row_index,
            col_index=col_index,
            player=player_summary,
            rarity_score=rarity_score,
            total_picks_for_cell=total_picks,
            player_picks_for_cell=player_picks,
            possible_answers_count=possible_count,
        )

    @classmethod
    async def _increment_db_counters(
        cls,
        session: AsyncSession,
        puzzle_id: str,
        cell_identifier: str,
        player_id: str,
    ) -> Tuple[int, int]:
        """
        Database fallback for counter calculation when Redis is unavailable.
        """
        uid = uuid.UUID(puzzle_id) if isinstance(puzzle_id, str) else puzzle_id
        stat_query = select(AggregatedAnswerStats).where(
            AggregatedAnswerStats.puzzle_id == uid,
            AggregatedAnswerStats.cell_identifier == cell_identifier,
            AggregatedAnswerStats.player_id == player_id,
        )
        stat_record = (await session.execute(stat_query)).scalar_one_or_none()
        player_picks = (stat_record.selection_count if stat_record else 0) + 1

        total_query = select(func.coalesce(func.sum(AggregatedAnswerStats.selection_count), 0)).where(
            AggregatedAnswerStats.puzzle_id == uid,
            AggregatedAnswerStats.cell_identifier == cell_identifier,
        )
        total_picks = (await session.execute(total_query)).scalar() or 0
        total_picks += 1

        return int(total_picks), int(player_picks)

    @classmethod
    async def _sync_stats_to_db(
        cls,
        session: AsyncSession,
        puzzle_id: str,
        cell_identifier: str,
        player_id: str,
        selection_count: int,
        pick_percentage: float,
    ) -> None:
        """
        Upserts aggregated answer statistics into PostgreSQL aggregated_answer_stats table.
        """
        uid = uuid.UUID(puzzle_id) if isinstance(puzzle_id, str) else puzzle_id
        stat_query = select(AggregatedAnswerStats).where(
            AggregatedAnswerStats.puzzle_id == uid,
            AggregatedAnswerStats.cell_identifier == cell_identifier,
            AggregatedAnswerStats.player_id == player_id,
        )
        record = (await session.execute(stat_query)).scalar_one_or_none()

        if record:
            record.selection_count = selection_count
            record.pick_percentage = pick_percentage
        else:
            new_record = AggregatedAnswerStats(
                puzzle_id=uid,
                cell_identifier=cell_identifier,
                player_id=player_id,
                selection_count=selection_count,
                pick_percentage=pick_percentage,
            )
            session.add(new_record)
