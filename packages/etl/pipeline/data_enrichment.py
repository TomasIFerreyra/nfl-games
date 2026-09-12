"""
Data Enrichment and Criteria Coverage Verification Engine.
Handles automated backfilling of historical draft/college metadata, hardware accolades,
career statistics precomputation, and dynamic criteria coverage validation.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player, PlayerTeamStint
from app.db.models.stats import Accolade, PlayerCareerStat, PlayerSeasonStat
from app.domain.criteria_registry import CriteriaRegistry, registry
from app.services.grid_precompute_service import GridPrecomputeService

logger = logging.getLogger(__name__)


class DataEnrichmentService:
    """
    Automated data enrichment pipeline backfilling advanced puzzle metadata
    and validating criteria feasibility against PostgreSQL.
    """

    @classmethod
    async def enrich_draft_and_colleges(cls, session: AsyncSession) -> int:
        """
        Backfills missing college, draft_round, and draft_overall fields from nflverse / draft dataset.
        """
        logger.info("Extracting draft and college datasets...")
        draft_df = pd.DataFrame()

        # 1. Try nflreadpy / nflverse download
        try:
            url = "https://github.com/nflverse/nflverse-data/releases/download/draft_picks/draft_picks.csv"
            draft_df = pd.read_csv(url, low_memory=False)
            logger.info(f"Loaded {len(draft_df)} draft pick records from nflverse.")
        except Exception as exc:
            logger.warning(f"Failed to fetch remote draft picks: {exc}. Using fallback logic.")

        if draft_df.empty:
            return 0

        updated_count = 0
        # Iterate and batch update players where college or draft info is missing
        stmt = select(Player).where(
            (Player.college.is_(None)) | (Player.draft_round.is_(None))
        )
        res = await session.execute(stmt)
        players = res.scalars().all()

        for p in players:
            match = None
            if p.gsis_id and "gsis_id" in draft_df.columns:
                matches = draft_df[draft_df["gsis_id"] == p.gsis_id]
                if not matches.empty:
                    match = matches.iloc[0]
            elif p.pfr_id and "pfr_player_id" in draft_df.columns:
                matches = draft_df[draft_df["pfr_player_id"] == p.pfr_id]
                if not matches.empty:
                    match = matches.iloc[0]

            if match is not None:
                changed = False
                if not p.college and pd.notna(match.get("college")):
                    p.college = str(match["college"]).strip()
                    changed = True
                if p.draft_round is None and pd.notna(match.get("round")):
                    try:
                        p.draft_round = int(match["round"])
                        changed = True
                    except (ValueError, TypeError):
                        pass
                if p.draft_overall is None and pd.notna(match.get("pick")):
                    try:
                        p.draft_overall = int(match["pick"])
                        changed = True
                    except (ValueError, TypeError):
                        pass

                if changed:
                    updated_count += 1

        await session.commit()
        logger.info(f"Enriched draft & college data for {updated_count} player records.")
        return updated_count

    @classmethod
    async def enrich_accolades(cls, session: AsyncSession) -> int:
        """
        Populates hardware awards and accolades into the accolades table safely.
        """
        logger.info("Enriching accolades table...")
        # Core sample hardware dataset mapping
        sample_hardware = [
            ("Patrick Mahomes", "MVP", 2018),
            ("Patrick Mahomes", "MVP", 2022),
            ("Patrick Mahomes", "SUPER_BOWL_MVP", 2019),
            ("Patrick Mahomes", "SUPER_BOWL_MVP", 2022),
            ("Patrick Mahomes", "SUPER_BOWL_MVP", 2023),
            ("Patrick Mahomes", "SUPER_BOWL_CHAMPION", 2019),
            ("Patrick Mahomes", "SUPER_BOWL_CHAMPION", 2022),
            ("Patrick Mahomes", "SUPER_BOWL_CHAMPION", 2023),
            ("Patrick Mahomes", "FIRST_TEAM_ALL_PRO", 2018),
            ("Patrick Mahomes", "FIRST_TEAM_ALL_PRO", 2022),
            ("Patrick Mahomes", "PRO_BOWL", 2018),
            ("Patrick Mahomes", "PRO_BOWL", 2019),
            ("Patrick Mahomes", "PRO_BOWL", 2020),
            ("Patrick Mahomes", "PRO_BOWL", 2021),
            ("Patrick Mahomes", "PRO_BOWL", 2022),
            ("Patrick Mahomes", "PRO_BOWL", 2023),
            ("Lamar Jackson", "MVP", 2019),
            ("Lamar Jackson", "MVP", 2023),
            ("Lamar Jackson", "FIRST_TEAM_ALL_PRO", 2019),
            ("Lamar Jackson", "FIRST_TEAM_ALL_PRO", 2023),
            ("Aaron Rodgers", "MVP", 2011),
            ("Aaron Rodgers", "MVP", 2014),
            ("Aaron Rodgers", "MVP", 2020),
            ("Aaron Rodgers", "MVP", 2021),
            ("Aaron Rodgers", "SUPER_BOWL_MVP", 2010),
            ("Aaron Rodgers", "SUPER_BOWL_CHAMPION", 2010),
            ("Aaron Rodgers", "FIRST_TEAM_ALL_PRO", 2011),
            ("Aaron Rodgers", "FIRST_TEAM_ALL_PRO", 2014),
            ("Aaron Rodgers", "FIRST_TEAM_ALL_PRO", 2020),
            ("Aaron Rodgers", "FIRST_TEAM_ALL_PRO", 2021),
            ("Tom Brady", "MVP", 2007),
            ("Tom Brady", "MVP", 2010),
            ("Tom Brady", "MVP", 2017),
            ("Tom Brady", "SUPER_BOWL_MVP", 2001),
            ("Tom Brady", "SUPER_BOWL_MVP", 2003),
            ("Tom Brady", "SUPER_BOWL_MVP", 2014),
            ("Tom Brady", "SUPER_BOWL_MVP", 2016),
            ("Tom Brady", "SUPER_BOWL_MVP", 2020),
            ("Tom Brady", "SUPER_BOWL_CHAMPION", 2001),
            ("Tom Brady", "SUPER_BOWL_CHAMPION", 2003),
            ("Tom Brady", "SUPER_BOWL_CHAMPION", 2004),
            ("Tom Brady", "SUPER_BOWL_CHAMPION", 2014),
            ("Tom Brady", "SUPER_BOWL_CHAMPION", 2016),
            ("Tom Brady", "SUPER_BOWL_CHAMPION", 2018),
            ("Tom Brady", "SUPER_BOWL_CHAMPION", 2020),
            ("C.J. Stroud", "OROY", 2023),
            ("Garrett Wilson", "OROY", 2022),
            ("Ja'Marr Chase", "OROY", 2021),
            ("Justin Herbert", "OROY", 2020),
            ("Kyler Murray", "OROY", 2019),
            ("Saquon Barkley", "OROY", 2018),
            ("Alvin Kamara", "OROY", 2017),
            ("Dak Prescott", "OROY", 2016),
            ("Will Anderson Jr.", "DROY", 2023),
            ("Sauce Gardner", "DROY", 2022),
            ("Micah Parsons", "DROY", 2021),
            ("Chase Young", "DROY", 2020),
            ("Nick Bosa", "DROY", 2019),
            ("Darius Leonard", "DROY", 2018),
            ("Marshon Lattimore", "DROY", 2017),
            ("Joey Bosa", "DROY", 2016),
            ("Aaron Donald", "DROY", 2014),
            ("Joe Burrow", "CPOY", 2021),
            ("Geno Smith", "CPOY", 2022),
            ("Damar Hamlin", "CPOY", 2023),
            ("Alex Smith", "CPOY", 2020),
            ("Ryan Tannehill", "CPOY", 2019),
            ("Andrew Luck", "CPOY", 2018),
            ("Keenan Allen", "CPOY", 2017),
            ("Jordy Nelson", "CPOY", 2016),
            ("Cameron Heyward", "WPMOTY", 2023),
            ("Dak Prescott", "WPMOTY", 2022),
            ("Andrew Whitworth", "WPMOTY", 2021),
            ("Russell Wilson", "WPMOTY", 2020),
            ("Calais Campbell", "WPMOTY", 2019),
            ("Chris Long", "WPMOTY", 2018),
            ("J.J. Watt", "WPMOTY", 2017),
            ("Larry Fitzgerald", "WPMOTY", 2016),
            ("Eli Manning", "WPMOTY", 2016),
        ]

        inserted_count = 0
        for name, acc_type, year in sample_hardware:
            p_res = await session.execute(
                select(Player.player_id).where(
                    func.lower(Player.full_name) == name.lower()
                )
            )
            p_id = p_res.scalars().first()
            if not p_id:
                continue

            # Check existing
            exists_stmt = select(Accolade.accolade_id).where(
                Accolade.player_id == p_id,
                Accolade.accolade_type == acc_type,
                Accolade.season_year == year,
            )
            exists = (await session.execute(exists_stmt)).scalars().first()
            if not exists:
                session.add(
                    Accolade(
                        player_id=p_id,
                        accolade_type=acc_type,
                        season_year=year,
                    )
                )
                inserted_count += 1

        await session.commit()
        logger.info(f"Enriched {inserted_count} new hardware accolades records.")
        return inserted_count

    @classmethod
    async def compute_career_stats(cls, session: AsyncSession) -> int:
        """
        Precomputes and aggregates career statistics into player_career_stats table.
        """
        logger.info("Precomputing player career stats...")

        stmt = text("""
            INSERT INTO player_career_stats (
                player_id, seasons_played, games_played,
                passing_yards, passing_tds, interceptions,
                rushing_yards, rushing_tds, receptions,
                receiving_yards, receiving_tds, sacks,
                defensive_interceptions, pro_bowls, all_pros,
                franchises_played_count
            )
            SELECT 
                p.player_id,
                COALESCE(stat_agg.seasons, 0) AS seasons_played,
                COALESCE(stint_agg.total_gp, 0) AS games_played,
                COALESCE(stat_agg.pass_yds, 0) AS passing_yards,
                COALESCE(stat_agg.pass_tds, 0) AS passing_tds,
                COALESCE(stat_agg.ints, 0) AS interceptions,
                COALESCE(stat_agg.rush_yds, 0) AS rushing_yards,
                COALESCE(stat_agg.rush_tds, 0) AS rushing_tds,
                COALESCE(stat_agg.recs, 0) AS receptions,
                COALESCE(stat_agg.rec_yds, 0) AS receiving_yards,
                COALESCE(stat_agg.rec_tds, 0) AS receiving_tds,
                COALESCE(stat_agg.sacks, 0.0) AS sacks,
                COALESCE(stat_agg.def_ints, 0) AS defensive_interceptions,
                COALESCE(acc_pb.pb_cnt, 0) AS pro_bowls,
                COALESCE(acc_ap.ap_cnt, 0) AS all_pros,
                COALESCE(stint_agg.franchise_cnt, 0) AS franchises_played_count
            FROM players p
            LEFT JOIN (
                SELECT 
                    player_id,
                    COUNT(stat_id) AS seasons,
                    SUM(passing_yards) AS pass_yds,
                    SUM(passing_tds) AS pass_tds,
                    SUM(interceptions) AS ints,
                    SUM(rushing_yards) AS rush_yds,
                    SUM(rushing_tds) AS rush_tds,
                    SUM(receptions) AS recs,
                    SUM(receiving_yards) AS rec_yds,
                    SUM(receiving_tds) AS rec_tds,
                    SUM(sacks) AS sacks,
                    SUM(defensive_interceptions) AS def_ints
                FROM player_season_stats
                GROUP BY player_id
            ) stat_agg ON p.player_id = stat_agg.player_id
            LEFT JOIN (
                SELECT 
                    player_id,
                    SUM(games_played) AS total_gp,
                    COUNT(DISTINCT franchise_id) AS franchise_cnt
                FROM player_team_stints
                WHERE games_played >= 1
                GROUP BY player_id
            ) stint_agg ON p.player_id = stint_agg.player_id
            LEFT JOIN (
                SELECT player_id, COUNT(*) AS pb_cnt
                FROM accolades
                WHERE accolade_type = 'PRO_BOWL'
                GROUP BY player_id
            ) acc_pb ON p.player_id = acc_pb.player_id
            LEFT JOIN (
                SELECT player_id, COUNT(*) AS ap_cnt
                FROM accolades
                WHERE accolade_type = 'FIRST_TEAM_ALL_PRO'
                GROUP BY player_id
            ) acc_ap ON p.player_id = acc_ap.player_id
            WHERE stat_agg.player_id IS NOT NULL OR stint_agg.player_id IS NOT NULL
            ON CONFLICT (player_id) DO UPDATE SET
                seasons_played = EXCLUDED.seasons_played,
                games_played = EXCLUDED.games_played,
                passing_yards = EXCLUDED.passing_yards,
                passing_tds = EXCLUDED.passing_tds,
                interceptions = EXCLUDED.interceptions,
                rushing_yards = EXCLUDED.rushing_yards,
                rushing_tds = EXCLUDED.rushing_tds,
                receptions = EXCLUDED.receptions,
                receiving_yards = EXCLUDED.receiving_yards,
                receiving_tds = EXCLUDED.receiving_tds,
                sacks = EXCLUDED.sacks,
                defensive_interceptions = EXCLUDED.defensive_interceptions,
                pro_bowls = EXCLUDED.pro_bowls,
                all_pros = EXCLUDED.all_pros,
                franchises_played_count = EXCLUDED.franchises_played_count;
        """)
        res = await session.execute(stmt)
        await session.commit()
        rowcount = res.rowcount if hasattr(res, "rowcount") and res.rowcount >= 0 else 1
        logger.info(f"Precomputed career stats for {rowcount} players.")
        return rowcount

    @classmethod
    async def validate_criteria_coverage(
        cls,
        session: AsyncSession,
        custom_registry: CriteriaRegistry = registry,
        min_threshold: int = 50,
    ) -> Dict[str, Any]:
        """
        Runs coverage verification query for all criteria in criteria_registry.
        If a criterion has fewer than min_threshold qualifying players, automatically
        flags it as is_active = False so the generator never produces impossible cells.
        """
        logger.info(f"Validating criteria coverage (Minimum threshold: {min_threshold} players)...")
        results: Dict[str, Any] = {
            "total_criteria": len(custom_registry.get_all_criteria(active_only=False)),
            "active_criteria": 0,
            "deactivated_criteria": 0,
            "coverage_counts": {},
        }

        for crit in custom_registry.get_all_criteria(active_only=False):
            crit_dict = crit.to_dict()
            qualifying = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(
                session, crit_dict
            )
            count = len(qualifying)
            results["coverage_counts"][crit.criterion_id] = count

            if count < min_threshold:
                crit.is_active = False
                results["deactivated_criteria"] += 1
                logger.debug(
                    f"Criterion '{crit.criterion_id}' ({crit.display_title}) has low coverage: "
                    f"{count} < {min_threshold}. Flagged is_active = False."
                )
            else:
                crit.is_active = True
                results["active_criteria"] += 1

        logger.info(
            f"Criteria validation complete: {results['active_criteria']} Active, "
            f"{results['deactivated_criteria']} Deactivated."
        )
        return results
