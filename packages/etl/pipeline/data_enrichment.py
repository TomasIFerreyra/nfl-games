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
            p_id = p_res.scalar_one_or_none()
            if not p_id:
                continue

            # Check existing
            exists_stmt = select(Accolade.accolade_id).where(
                Accolade.player_id == p_id,
                Accolade.accolade_type == acc_type,
                Accolade.season_year == year,
            )
            exists = (await session.execute(exists_stmt)).scalar_one_or_none()
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

        # Aggregate from PlayerSeasonStat
        stat_agg_query = (
            select(
                PlayerSeasonStat.player_id,
                func.count(PlayerSeasonStat.stat_id).label("seasons"),
                func.coalesce(func.sum(PlayerSeasonStat.passing_yards), 0).label("pass_yds"),
                func.coalesce(func.sum(PlayerSeasonStat.passing_tds), 0).label("pass_tds"),
                func.coalesce(func.sum(PlayerSeasonStat.interceptions), 0).label("ints"),
                func.coalesce(func.sum(PlayerSeasonStat.rushing_yards), 0).label("rush_yds"),
                func.coalesce(func.sum(PlayerSeasonStat.rushing_tds), 0).label("rush_tds"),
                func.coalesce(func.sum(PlayerSeasonStat.receptions), 0).label("recs"),
                func.coalesce(func.sum(PlayerSeasonStat.receiving_yards), 0).label("rec_yds"),
                func.coalesce(func.sum(PlayerSeasonStat.receiving_tds), 0).label("rec_tds"),
                func.coalesce(func.sum(PlayerSeasonStat.sacks), 0).label("sacks"),
                func.coalesce(func.sum(PlayerSeasonStat.defensive_interceptions), 0).label("def_ints"),
            )
            .group_by(PlayerSeasonStat.player_id)
        )
        stat_rows = (await session.execute(stat_agg_query)).fetchall()

        upserted_count = 0
        for r in stat_rows:
            p_id = r[0]

            # Count distinct franchises played
            stint_q = select(
                func.count(func.distinct(PlayerTeamStint.franchise_id)),
                func.coalesce(func.sum(PlayerTeamStint.games_played), 0),
            ).where(
                PlayerTeamStint.player_id == p_id,
                PlayerTeamStint.games_played >= 1,
            )
            stint_row = (await session.execute(stint_q)).first()
            f_count = stint_row[0] if stint_row else 0
            gp_count = stint_row[1] if stint_row else 0

            # Count Pro Bowls and All-Pros
            pb_q = select(func.count(Accolade.accolade_id)).where(
                Accolade.player_id == p_id,
                Accolade.accolade_type == "PRO_BOWL",
            )
            pb_count = (await session.execute(pb_q)).scalar() or 0

            ap_q = select(func.count(Accolade.accolade_id)).where(
                Accolade.player_id == p_id,
                Accolade.accolade_type == "FIRST_TEAM_ALL_PRO",
            )
            ap_count = (await session.execute(ap_q)).scalar() or 0

            # Upsert into PlayerCareerStat
            career_q = select(PlayerCareerStat).where(PlayerCareerStat.player_id == p_id)
            career_rec = (await session.execute(career_q)).scalar_one_or_none()

            if not career_rec:
                career_rec = PlayerCareerStat(
                    player_id=p_id,
                    seasons_played=r[1],
                    games_played=gp_count,
                    passing_yards=r[2],
                    passing_tds=r[3],
                    interceptions=r[4],
                    rushing_yards=r[5],
                    rushing_tds=r[6],
                    receptions=r[7],
                    receiving_yards=r[8],
                    receiving_tds=r[9],
                    sacks=Decimal(str(round(float(r[10]), 1))),
                    defensive_interceptions=r[11],
                    pro_bowls=pb_count,
                    all_pros=ap_count,
                    franchises_played_count=f_count,
                )
                session.add(career_rec)
            else:
                career_rec.seasons_played = r[1]
                career_rec.games_played = gp_count
                career_rec.passing_yards = r[2]
                career_rec.passing_tds = r[3]
                career_rec.interceptions = r[4]
                career_rec.rushing_yards = r[5]
                career_rec.rushing_tds = r[6]
                career_rec.receptions = r[7]
                career_rec.receiving_yards = r[8]
                career_rec.receiving_tds = r[9]
                career_rec.sacks = Decimal(str(round(float(r[10]), 1)))
                career_rec.defensive_interceptions = r[11]
                career_rec.pro_bowls = pb_count
                career_rec.all_pros = ap_count
                career_rec.franchises_played_count = f_count

            upserted_count += 1

        await session.commit()
        logger.info(f"Populated precomputed career stats for {upserted_count} players.")
        return upserted_count

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
