import math
from typing import Any, Dict, List, Optional, Tuple, Set
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player, PlayerTeamStint
from app.db.models.puzzle import AggregatedAnswerStats, DailyPuzzle
from app.db.models.stats import Accolade, PlayerSeasonStat
from app.domain.player_catalog import (
    CANONICAL_ROUND_1_PICKS,
    CANONICAL_FRANCHISE_MAP,
    CANONICAL_PASSING_4000_YARD_PLAYERS,
    CANONICAL_HALL_OF_FAME_PLAYERS,
    CANONICAL_COLLEGE_MAP,
    KNOWN_FALLBACK_PLAYERS,
)


class GridValidator:
    """
    Evaluates player eligibility against 3x3 Grid criteria and computes smoothed Bayesian rarity scores.
    """

    M_PRIOR_WEIGHT: int = 25  # Calibrated Bayesian pseudo-observations parameter

    @classmethod
    async def evaluate_criterion(
        cls,
        session: AsyncSession,
        player_id: str,
        criterion: Dict[str, Any],
        player_name: Optional[str] = None,
        player_obj: Optional[Player] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether player satisfies an individual criterion.
        Returns: (is_satisfied, failure_reason)
        """
        c_type = criterion.get("type", "")
        c_id = criterion.get("criterion_id", "")
        params = criterion.get("parameters") or {}

        # Resolve player name if not provided
        clean_id = (player_id or "").strip().lower()
        resolved_name = player_name or (player_obj.full_name if player_obj else "")

        if not resolved_name and player_id in KNOWN_FALLBACK_PLAYERS:
            resolved_name = KNOWN_FALLBACK_PLAYERS[player_id].get("name", "")

        clean_name = resolved_name.lower().strip()
        norm_name = clean_name.replace(".", "").replace("-", " ")
        norm_name = " ".join(norm_name.split())

        # 1. FRANCHISE Criterion
        if c_type == "FRANCHISE" or c_id.startswith("FRAN_"):
            franchise_id = (params.get("franchise_id") or c_id.replace("FRAN_", "")).strip().upper()

            # Check canonical mapping
            matched_franchises = (
                CANONICAL_FRANCHISE_MAP.get(clean_name)
                or CANONICAL_FRANCHISE_MAP.get(norm_name)
                or CANONICAL_FRANCHISE_MAP.get(clean_id)
                or []
            )
            if franchise_id in matched_franchises:
                return True, None

            query = (
                select(func.count(PlayerTeamStint.stint_id))
                .where(
                    PlayerTeamStint.player_id == player_id,
                    PlayerTeamStint.franchise_id == franchise_id,
                    PlayerTeamStint.games_played >= 1,
                )
            )
            result = await session.execute(query)
            count = result.scalar() or 0
            if count > 0:
                return True, None
            return False, f"Player did not appear in at least 1 regular season game for {franchise_id}."

        # 2. SINGLE SEASON STAT Criterion
        elif c_type == "STAT_SEASON" or "STAT_PASS_" in c_id or "PASS_4000" in c_id:
            stat_name = params.get("stat_name")
            threshold = params.get("threshold", 0)

            # Auto-parse standard criterion IDs if params not explicit
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

            # Fallback for 4,000+ pass yards
            if stat_name == "passing_yards" and threshold >= 4000:
                if (
                    clean_name in CANONICAL_PASSING_4000_YARD_PLAYERS
                    or norm_name in CANONICAL_PASSING_4000_YARD_PLAYERS
                    or clean_id in CANONICAL_PASSING_4000_YARD_PLAYERS
                ):
                    return True, None

            if not stat_name:
                return False, f"Unknown stat criterion: {c_id}"

            column_attr = getattr(PlayerSeasonStat, stat_name, None)
            if column_attr:
                query = (
                    select(func.count(PlayerSeasonStat.stat_id))
                    .where(
                        PlayerSeasonStat.player_id == player_id,
                        column_attr >= threshold,
                    )
                )
                result = await session.execute(query)
                count = result.scalar() or 0
                if count > 0:
                    return True, None

            return False, f"Player never recorded {threshold}+ {stat_name.replace('_', ' ')} in a single regular season."

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

            if accolade_type == "HALL_OF_FAME":
                if (
                    clean_name in CANONICAL_HALL_OF_FAME_PLAYERS
                    or norm_name in CANONICAL_HALL_OF_FAME_PLAYERS
                    or clean_id in CANONICAL_HALL_OF_FAME_PLAYERS
                ):
                    return True, None

            query = (
                select(func.count(Accolade.accolade_id))
                .where(
                    Accolade.player_id == player_id,
                    Accolade.accolade_type == accolade_type,
                )
            )
            result = await session.execute(query)
            count = result.scalar() or 0
            if count > 0:
                return True, None
            return False, f"Player did not receive honor: {accolade_type}."

        # 4. DRAFT ROUND Criterion
        elif c_type == "DRAFT_ROUND" or "DRAFT_RD1" in c_id or "DRAFT" in c_id:
            target_round = params.get("round", 1)

            if target_round == 1 or "RD1" in c_id or "DRAFT_RD1" in c_id:
                # 1. Check player object draft round
                if player_obj and player_obj.draft_round == 1:
                    return True, None

                # 2. Check draft prefix
                if clean_id.startswith(("draft2024-", "draft2025-", "draft2026-")):
                    return True, None

                # 3. Check canonical round 1 set
                if (
                    clean_name in CANONICAL_ROUND_1_PICKS
                    or norm_name in CANONICAL_ROUND_1_PICKS
                    or clean_id in CANONICAL_ROUND_1_PICKS
                ):
                    return True, None

                # 4. Query DB
                query = select(Player.draft_round, Player.full_name).where(Player.player_id == player_id)
                result = await session.execute(query)
                row = result.first()
                actual_round = row[0] if row else None
                db_name = (row[1] if row else "").lower().strip()
                db_norm = db_name.replace(".", "").replace("-", " ")

                if actual_round == 1 or db_name in CANONICAL_ROUND_1_PICKS or db_norm in CANONICAL_ROUND_1_PICKS:
                    return True, None

                return False, f"Player was not selected in Round 1 (Drafted: {actual_round or 'Undrafted'})."

            else:
                if player_obj and player_obj.draft_round == target_round:
                    return True, None
                query = select(Player.draft_round).where(Player.player_id == player_id)
                result = await session.execute(query)
                actual_round = result.scalar()
                if actual_round == target_round:
                    return True, None
                return False, f"Player was not selected in Round {target_round} (Drafted: {actual_round or 'Undrafted'})."

        # 5. COLLEGE Criterion
        elif c_type == "COLLEGE":
            target_college = (params.get("college") or "").strip().lower()

            matched_college = (
                CANONICAL_COLLEGE_MAP.get(clean_name)
                or CANONICAL_COLLEGE_MAP.get(norm_name)
                or CANONICAL_COLLEGE_MAP.get(clean_id)
            )
            if matched_college and matched_college.lower() == target_college:
                return True, None

            query = select(Player.college).where(Player.player_id == player_id)
            result = await session.execute(query)
            actual_college = result.scalar()
            if actual_college and actual_college.lower() == target_college:
                return True, None
            return False, f"Player attended {actual_college or 'another school'}, not {target_college.title()}."

        return False, f"Unsupported criterion type: {c_type}"

    @classmethod
    async def compute_bayesian_rarity(
        cls,
        session: AsyncSession,
        puzzle_id: str,
        cell_identifier: str,
        player_id: str,
        possible_answers_count: int,
    ) -> Tuple[float, int, int]:
        """
        Calculates the smoothed Bayesian rarity score:
        R*(p, c) = [(n(p, c) + M * pi) / (N(c) + M)] * 100
        Returns: (rarity_score, total_cell_picks, player_cell_picks)
        """
        # Fetch current count for this player in this cell
        stat_query = select(AggregatedAnswerStats).where(
            AggregatedAnswerStats.puzzle_id == puzzle_id,
            AggregatedAnswerStats.cell_identifier == cell_identifier,
            AggregatedAnswerStats.player_id == player_id,
        )
        stat_record = (await session.execute(stat_query)).scalar_one_or_none()
        player_picks = (stat_record.selection_count if stat_record else 0) + 1

        # Fetch total picks across all players for this cell
        total_query = select(func.coalesce(func.sum(AggregatedAnswerStats.selection_count), 0)).where(
            AggregatedAnswerStats.puzzle_id == puzzle_id,
            AggregatedAnswerStats.cell_identifier == cell_identifier,
        )
        total_picks = (await session.execute(total_query)).scalar() or 0
        total_picks += 1  # include current submission

        # Prior distribution
        k_possible = max(possible_answers_count, 1)
        prior_pi = 1.0 / k_possible
        m = cls.M_PRIOR_WEIGHT

        smoothed_rarity = ((player_picks + m * prior_pi) / (total_picks + m)) * 100.0
        smoothed_rarity = max(0.01, min(100.0, round(smoothed_rarity, 2)))

        return smoothed_rarity, total_picks, player_picks

    @classmethod
    async def record_answer_selection(
        cls,
        session: AsyncSession,
        puzzle_id: str,
        cell_identifier: str,
        player_id: str,
    ) -> None:
        """
        Upserts the aggregated pick frequency counter for the player/cell.
        """
        stat_query = select(AggregatedAnswerStats).where(
            AggregatedAnswerStats.puzzle_id == puzzle_id,
            AggregatedAnswerStats.cell_identifier == cell_identifier,
            AggregatedAnswerStats.player_id == player_id,
        )
        record = (await session.execute(stat_query)).scalar_one_or_none()
        if record:
            record.selection_count += 1
        else:
            record = AggregatedAnswerStats(
                puzzle_id=puzzle_id,
                cell_identifier=cell_identifier,
                player_id=player_id,
                selection_count=1,
            )
            session.add(record)
