import math
from typing import Any, Dict, List, Optional, Tuple, Set
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player, PlayerTeamStint
from app.db.models.puzzle import AggregatedAnswerStats, DailyPuzzle
from app.db.models.stats import Accolade, PlayerCareerStat, PlayerSeasonStat
from app.domain.criteria_registry import CONFERENCE_MAP, DIVISION_MAP
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
        c_type = str(criterion.get("type", "")).upper()
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

        # 2. DIVISION / CONFERENCE Criterion
        elif c_type == "DIVISION" or c_id.startswith("DIV_"):
            div_id = params.get("division_id") or c_id
            franchise_ids = params.get("franchise_ids") or DIVISION_MAP.get(div_id, [])
            matched_franchises = (
                CANONICAL_FRANCHISE_MAP.get(clean_name)
                or CANONICAL_FRANCHISE_MAP.get(norm_name)
                or CANONICAL_FRANCHISE_MAP.get(clean_id)
                or []
            )
            if any(f in franchise_ids for f in matched_franchises):
                return True, None

            query = (
                select(func.count(PlayerTeamStint.stint_id))
                .where(
                    PlayerTeamStint.player_id == player_id,
                    PlayerTeamStint.franchise_id.in_(franchise_ids),
                    PlayerTeamStint.games_played >= 1,
                )
            )
            result = await session.execute(query)
            count = result.scalar() or 0
            if count > 0:
                return True, None
            return False, f"Player never appeared in at least 1 regular season game for division {div_id}."

        elif c_type == "CONFERENCE" or c_id.startswith("CONF_"):
            conf_id = c_id
            franchise_ids = params.get("franchise_ids") or CONFERENCE_MAP.get(conf_id, [])
            matched_franchises = (
                CANONICAL_FRANCHISE_MAP.get(clean_name)
                or CANONICAL_FRANCHISE_MAP.get(norm_name)
                or CANONICAL_FRANCHISE_MAP.get(clean_id)
                or []
            )
            if any(f in franchise_ids for f in matched_franchises):
                return True, None

            query = (
                select(func.count(PlayerTeamStint.stint_id))
                .where(
                    PlayerTeamStint.player_id == player_id,
                    PlayerTeamStint.franchise_id.in_(franchise_ids),
                    PlayerTeamStint.games_played >= 1,
                )
            )
            result = await session.execute(query)
            count = result.scalar() or 0
            if count > 0:
                return True, None
            return False, f"Player never appeared in at least 1 regular season game for {conf_id}."

        # 3. JOURNEYMAN Criterion
        elif c_type == "JOURNEYMAN" or "JOURNEYMAN" in c_id:
            min_f = params.get("min_franchises", 3)
            matched_franchises = (
                CANONICAL_FRANCHISE_MAP.get(clean_name)
                or CANONICAL_FRANCHISE_MAP.get(norm_name)
                or CANONICAL_FRANCHISE_MAP.get(clean_id)
                or []
            )
            if len(set(matched_franchises)) >= min_f:
                return True, None

            query = (
                select(func.count(func.distinct(PlayerTeamStint.franchise_id)))
                .where(
                    PlayerTeamStint.player_id == player_id,
                    PlayerTeamStint.games_played >= 1,
                )
            )
            result = await session.execute(query)
            f_count = result.scalar() or 0
            if f_count >= min_f:
                return True, None
            return False, f"Player played for {f_count} franchises (required: {min_f}+)."

        # 4. SINGLE SEASON STAT Criterion
        elif c_type == "STAT_SEASON" or "STAT_PASS_" in c_id or "PASS_4000" in c_id:
            stat_name = params.get("stat_name")
            threshold = params.get("threshold", 0)

            if not stat_name:
                if "PASS_5000" in c_id:
                    stat_name, threshold = "passing_yards", 5000
                elif "PASS_4000" in c_id:
                    stat_name, threshold = "passing_yards", 4000
                elif "PASS_3000" in c_id:
                    stat_name, threshold = "passing_yards", 3000
                elif "RUSH_1500" in c_id:
                    stat_name, threshold = "rushing_yards", 1500
                elif "RUSH_1000" in c_id:
                    stat_name, threshold = "rushing_yards", 1000
                elif "REC_1500" in c_id:
                    stat_name, threshold = "receiving_yards", 1500
                elif "REC_1000" in c_id:
                    stat_name, threshold = "receiving_yards", 1000
                elif "SACK_15" in c_id:
                    stat_name, threshold = "sacks", 15.0
                elif "SACK_10" in c_id:
                    stat_name, threshold = "sacks", 10.0
                elif "PASS_TD_30" in c_id:
                    stat_name, threshold = "passing_tds", 30
                elif "RUSH_TD_15" in c_id:
                    stat_name, threshold = "rushing_tds", 15
                elif "RUSH_TD_10" in c_id:
                    stat_name, threshold = "rushing_tds", 10
                elif "REC_TD_10" in c_id:
                    stat_name, threshold = "receiving_tds", 10
                elif "REC_100" in c_id:
                    stat_name, threshold = "receptions", 100
                elif "INT_6" in c_id:
                    stat_name, threshold = "defensive_interceptions", 6

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

        # 5. CAREER STAT Criterion
        elif c_type == "STAT_CAREER" or c_id.startswith("CAREER_"):
            stat_name = params.get("stat_name")
            threshold = params.get("threshold", 0)

            # Check PlayerCareerStat table
            career_attr = getattr(PlayerCareerStat, stat_name, None) if stat_name else None
            if career_attr:
                query = select(career_attr).where(PlayerCareerStat.player_id == player_id)
                res = await session.execute(query)
                val = res.scalar()
                if val is not None and val >= threshold:
                    return True, None

            # Fallback: sum of player season stats
            season_attr = getattr(PlayerSeasonStat, stat_name, None) if stat_name else None
            if season_attr:
                query = select(func.sum(season_attr)).where(PlayerSeasonStat.player_id == player_id)
                res = await session.execute(query)
                total = res.scalar()
                if total is not None and total >= threshold:
                    return True, None

            return False, f"Player did not reach {threshold}+ career {stat_name.replace('_', ' ')}."

        # 6. POSITIONAL QUIRK Criterion
        elif c_type == "STAT_POSITIONAL" or c_id.startswith("POS_"):
            pos = params.get("position")
            stat_name = params.get("stat_name")
            threshold = params.get("threshold", 0)

            # Check player position
            actual_pos = player_obj.primary_position if player_obj else None
            if not actual_pos:
                res = await session.execute(select(Player.primary_position).where(Player.player_id == player_id))
                actual_pos = res.scalar()

            if actual_pos != pos:
                return False, f"Player position is {actual_pos}, expected {pos}."

            season_attr = getattr(PlayerSeasonStat, stat_name, None) if stat_name else None
            if season_attr:
                query = select(func.count(PlayerSeasonStat.stat_id)).where(
                    PlayerSeasonStat.player_id == player_id,
                    season_attr >= threshold,
                )
                res = await session.execute(query)
                count = res.scalar() or 0
                if count > 0:
                    return True, None

            return False, f"Player never recorded {threshold}+ {stat_name.replace('_', ' ')} as {pos} in a single season."

        # 7. ACCOLADE Criterion
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
                elif "SUPER_BOWL_MVP" in c_id or "SB_MVP" in c_id:
                    accolade_type = "SUPER_BOWL_MVP"
                elif "SUPER_BOWL" in c_id:
                    accolade_type = "SUPER_BOWL_CHAMPION"
                elif "OROY" in c_id:
                    accolade_type = "OROY"
                elif "DROY" in c_id:
                    accolade_type = "DROY"
                elif "CPOY" in c_id:
                    accolade_type = "CPOY"
                elif "WPMOTY" in c_id:
                    accolade_type = "WPMOTY"

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

        # 8. MULTI-TIME ACCOLADE Criterion
        elif c_type == "ACCOLADE_COUNT":
            accolade_type = params.get("accolade_type", "PRO_BOWL")
            min_count = params.get("min_count", 3)
            query = (
                select(func.count(Accolade.accolade_id))
                .where(
                    Accolade.player_id == player_id,
                    Accolade.accolade_type == accolade_type,
                )
            )
            result = await session.execute(query)
            count = result.scalar() or 0
            if count >= min_count:
                return True, None
            return False, f"Player earned {count} {accolade_type} honors (required: {min_count}+)."

        # 9. DRAFT ROUND / OVERALL Criterion
        elif c_type in ("DRAFT_ROUND", "DRAFT_OVERALL") or "DRAFT" in c_id:
            actual_round = player_obj.draft_round if player_obj else None
            actual_overall = player_obj.draft_overall if player_obj else None
            db_name = player_obj.full_name.lower().strip() if player_obj else ""

            if actual_round is None and actual_overall is None:
                query = select(Player.draft_round, Player.draft_overall, Player.full_name).where(Player.player_id == player_id)
                result = await session.execute(query)
                row = result.first()
                if row:
                    actual_round, actual_overall, db_name = row[0], row[1], (row[2] or "").lower().strip()

            db_norm = db_name.replace(".", "").replace("-", " ")

            if c_type == "DRAFT_OVERALL" or "TOP5" in c_id:
                max_overall = params.get("max_overall", 5)
                if actual_overall and 1 <= actual_overall <= max_overall:
                    return True, None
                return False, f"Player draft pick was #{actual_overall or 'Undrafted'} (expected Top {max_overall})."

            elif params.get("min_round") or "RD4_PLUS" in c_id:
                min_rd = params.get("min_round", 4)
                if actual_round and actual_round >= min_rd:
                    return True, None
                return False, f"Player drafted in Round {actual_round or 'Undrafted'} (expected Round {min_rd}+)."

            elif params.get("rounds") or "DAY2" in c_id:
                rds = params.get("rounds", [2, 3])
                if actual_round and actual_round in rds:
                    return True, None
                return False, f"Player drafted in Round {actual_round or 'Undrafted'} (expected Day 2: {rds})."

            elif params.get("is_undrafted") or "UNDRAFTED" in c_id:
                if actual_round is None or actual_round == 0:
                    return True, None
                return False, f"Player was drafted in Round {actual_round} (expected Undrafted)."

            else:
                target_round = params.get("round", 1)
                if target_round == 1:
                    if clean_id.startswith(("draft2024-", "draft2025-", "draft2026-")):
                        return True, None
                    if (
                        clean_name in CANONICAL_ROUND_1_PICKS
                        or norm_name in CANONICAL_ROUND_1_PICKS
                        or clean_id in CANONICAL_ROUND_1_PICKS
                        or db_name in CANONICAL_ROUND_1_PICKS
                        or db_norm in CANONICAL_ROUND_1_PICKS
                    ):
                        return True, None

                if actual_round == target_round:
                    return True, None
                return False, f"Player was not selected in Round {target_round} (Drafted: {actual_round or 'Undrafted'})."

        # 10. COLLEGE Criterion
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
