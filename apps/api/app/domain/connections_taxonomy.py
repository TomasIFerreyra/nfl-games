"""
Connections Category Taxonomy and Candidate Generator.
Defines candidate category generators querying PostgreSQL/nflverse relational schema across 4 graded tiers:
- Tier 1 (Bronze / Straightforward): Colleges, draft origins, single-franchise tenure, obvious awards.
- Tier 2 (Silver / Statistical Milestones): Single-season or career metrics (5,000+ pass yds, 100+ rush TDs, etc.).
- Tier 3 (Gold / Overlaps & Journeymen): Dual-franchise tenures, draft round origins, award combos.
- Tier 4 (Lombardi Platinum / Obscure & Quirky): Demographic/name quirks, rare pedigree, unique statistical quirks.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.franchise import Franchise, TeamSeason
from app.db.models.player import Player, PlayerTeamStint
from app.db.models.stats import Accolade, PlayerCareerStat, PlayerSeasonStat

logger = logging.getLogger(__name__)


class ConnectionsTier(int, Enum):
    BRONZE = 1      # Straightforward: Colleges, 1st round draft, single-team, Heisman/HOF
    SILVER = 2      # Statistical Milestones: 5k pass yds, 1k rush yds, 100 sacks, etc.
    GOLD = 3        # Overlaps & Journeymen: Dual-franchise tenure, Day 3 / UDFA, MVP combos
    PLATINUM = 4    # Lombardi Platinum: Name quirks, unique trivia, obscure cross-era combos


class ConnectionsCategoryArchetype(str, Enum):
    DEMOGRAPHIC_NAME = "DEMOGRAPHIC_NAME"
    COLLEGE = "COLLEGE"
    DRAFT_ORIGIN = "DRAFT_ORIGIN"
    FRANCHISE_TENURE = "FRANCHISE_TENURE"
    DUAL_FRANCHISE = "DUAL_FRANCHISE"
    ACCOLADE = "ACCOLADE"
    ACCOLADE_COMBO = "ACCOLADE_COMBO"
    STAT_SEASON = "STAT_SEASON"
    STAT_CAREER = "STAT_CAREER"
    PEDIGREE_QUIRK = "PEDIGREE_QUIRK"


@dataclass
class ConnectionsCategoryDefinition:
    """
    Metadata and resolver definition for a candidate Connections category.
    """
    category_id: str
    tier: ConnectionsTier
    title: str
    explanation: str
    archetype: ConnectionsCategoryArchetype
    parameters: Dict[str, Any] = field(default_factory=dict)
    min_players_required: int = 4
    is_active: bool = True

    @property
    def tier_name(self) -> str:
        names = {
            ConnectionsTier.BRONZE: "Bronze",
            ConnectionsTier.SILVER: "Silver",
            ConnectionsTier.GOLD: "Gold",
            ConnectionsTier.PLATINUM: "Lombardi Platinum",
        }
        return names.get(self.tier, "Bronze")


class ConnectionsTaxonomyRegistry:
    """
    Registry and execution engine for Connections categories.
    Queries the database schema to fetch matching player pools.
    """

    def __init__(self) -> None:
        self._categories: Dict[str, ConnectionsCategoryDefinition] = {}
        self._register_default_categories()

    def register(self, category: ConnectionsCategoryDefinition) -> None:
        self._categories[category.category_id] = category

    def get_category(self, category_id: str) -> Optional[ConnectionsCategoryDefinition]:
        return self._categories.get(category_id)

    def get_all_categories(self, active_only: bool = True) -> List[ConnectionsCategoryDefinition]:
        if active_only:
            return [c for c in self._categories.values() if c.is_active]
        return list(self._categories.values())

    def get_categories_by_tier(
        self, tier: ConnectionsTier, active_only: bool = True
    ) -> List[ConnectionsCategoryDefinition]:
        return [
            c for c in self.get_all_categories(active_only=active_only)
            if c.tier == tier
        ]

    async def resolve_player_pool(
        self,
        category: ConnectionsCategoryDefinition,
        session: AsyncSession,
    ) -> List[Player]:
        """
        Executes a targeted SQLAlchemy query against PostgreSQL to return
        all qualifying Player records for this category.
        """
        arch = category.archetype
        p = category.parameters

        if arch == ConnectionsCategoryArchetype.COLLEGE:
            college_name = p.get("college")
            query = select(Player).where(
                func.lower(Player.college) == func.lower(college_name)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME:
            first_names = [fn.lower() for fn in p.get("first_names", [])]
            query = select(Player).where(
                func.lower(Player.first_name).in_(first_names)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.DRAFT_ORIGIN:
            draft_round = p.get("draft_round")
            draft_round_min = p.get("draft_round_min")
            draft_round_max = p.get("draft_round_max")
            draft_overall = p.get("draft_overall")
            draft_year = p.get("draft_year")
            is_undrafted = p.get("is_undrafted", False)

            conditions = []
            if draft_round is not None:
                conditions.append(Player.draft_round == draft_round)
            if draft_round_min is not None:
                conditions.append(Player.draft_round >= draft_round_min)
            if draft_round_max is not None:
                conditions.append(Player.draft_round <= draft_round_max)
            if draft_overall is not None:
                conditions.append(Player.draft_overall == draft_overall)
            if draft_year is not None:
                conditions.append(Player.draft_year == draft_year)
            if is_undrafted:
                conditions.append(or_(Player.draft_round.is_(None), Player.draft_round == 0))

            query = select(Player).where(*conditions)
            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.FRANCHISE_TENURE:
            franchise_id = p.get("franchise_id")
            single_team_only = p.get("single_team_only", False)

            if single_team_only:
                subq = (
                    select(PlayerTeamStint.player_id)
                    .where(PlayerTeamStint.games_played >= 1)
                    .group_by(PlayerTeamStint.player_id)
                    .having(func.count(distinct(PlayerTeamStint.franchise_id)) == 1)
                )
                query = select(Player).where(Player.player_id.in_(subq))
            else:
                subq = (
                    select(PlayerTeamStint.player_id)
                    .where(
                        PlayerTeamStint.franchise_id == franchise_id,
                        PlayerTeamStint.games_played >= 1,
                    )
                )
                query = select(Player).where(Player.player_id.in_(subq))

            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.DUAL_FRANCHISE:
            fran_a = p.get("franchise_a")
            fran_b = p.get("franchise_b")
            subq_a = (
                select(PlayerTeamStint.player_id)
                .where(PlayerTeamStint.franchise_id == fran_a, PlayerTeamStint.games_played >= 1)
            )
            subq_b = (
                select(PlayerTeamStint.player_id)
                .where(PlayerTeamStint.franchise_id == fran_b, PlayerTeamStint.games_played >= 1)
            )
            query = select(Player).where(
                Player.player_id.in_(subq_a),
                Player.player_id.in_(subq_b),
            )
            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.ACCOLADE:
            accolade_type = p.get("accolade_type")
            min_count = p.get("min_count", 1)

            if min_count > 1:
                subq = (
                    select(Accolade.player_id)
                    .where(Accolade.accolade_type == accolade_type)
                    .group_by(Accolade.player_id)
                    .having(func.count(Accolade.accolade_id) >= min_count)
                )
            else:
                subq = (
                    select(Accolade.player_id)
                    .where(Accolade.accolade_type == accolade_type)
                )

            query = select(Player).where(Player.player_id.in_(subq))
            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.ACCOLADE_COMBO:
            accolades = p.get("accolades", [])
            subqueries = [
                select(Accolade.player_id).where(Accolade.accolade_type == acc)
                for acc in accolades
            ]
            conditions = [Player.player_id.in_(sq) for sq in subqueries]
            query = select(Player).where(*conditions)
            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.STAT_SEASON:
            stat_col = p.get("stat_column")
            min_val = p.get("min_val", 0)
            pos = p.get("position")

            stat_field = getattr(PlayerSeasonStat, stat_col, None)
            if stat_field is None:
                return []

            conditions = [stat_field >= min_val]
            if pos:
                conditions.append(Player.primary_position == pos)

            query = (
                select(Player)
                .join(PlayerSeasonStat, Player.player_id == PlayerSeasonStat.player_id)
                .where(*conditions)
                .distinct()
            )
            result = await session.execute(query)
            return list(result.scalars().all())

        elif arch == ConnectionsCategoryArchetype.STAT_CAREER:
            stat_col = p.get("stat_column")
            min_val = p.get("min_val", 0)
            journeyman_franchises = p.get("min_franchises")

            if journeyman_franchises:
                subq = (
                    select(PlayerTeamStint.player_id)
                    .where(PlayerTeamStint.games_played >= 1)
                    .group_by(PlayerTeamStint.player_id)
                    .having(func.count(distinct(PlayerTeamStint.franchise_id)) >= journeyman_franchises)
                )
                query = select(Player).where(Player.player_id.in_(subq))
            else:
                season_col = getattr(PlayerSeasonStat, stat_col, None)
                if season_col is not None:
                    subq = (
                        select(PlayerSeasonStat.player_id)
                        .group_by(PlayerSeasonStat.player_id)
                        .having(func.sum(season_col) >= min_val)
                    )
                    query = select(Player).where(Player.player_id.in_(subq))
                else:
                    return []

            result = await session.execute(query)
            return list(result.scalars().all())


        elif arch == ConnectionsCategoryArchetype.PEDIGREE_QUIRK:
            is_first_overall = p.get("first_overall", False)
            has_super_bowl = p.get("super_bowl", False)
            conditions = []
            if is_first_overall:
                conditions.append(Player.draft_overall == 1)
            if has_super_bowl:
                sb_subq = select(Accolade.player_id).where(Accolade.accolade_type == "SUPER_BOWL_CHAMPION")
                conditions.append(Player.player_id.in_(sb_subq))

            query = select(Player).where(*conditions)
            result = await session.execute(query)
            return list(result.scalars().all())

        return []

    def _register_default_categories(self) -> None:
        tier1_defs = [
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_ALABAMA",
                tier=ConnectionsTier.BRONZE,
                title="Attended the University of Alabama",
                explanation="All 4 players played college football for the Alabama Crimson Tide.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "Alabama"},
            ),
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_OHIO_STATE",
                tier=ConnectionsTier.BRONZE,
                title="Attended Ohio State University",
                explanation="All 4 players played college football for Ohio State Buckeyes.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "Ohio State"},
            ),
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_LSU",
                tier=ConnectionsTier.BRONZE,
                title="Attended LSU (Louisiana State)",
                explanation="All 4 players played college football for the LSU Tigers.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "LSU"},
            ),
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_GEORGIA",
                tier=ConnectionsTier.BRONZE,
                title="Attended the University of Georgia",
                explanation="All 4 players played college football for the Georgia Bulldogs.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "Georgia"},
            ),
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_MICHIGAN",
                tier=ConnectionsTier.BRONZE,
                title="Attended the University of Michigan",
                explanation="All 4 players played college football for the Michigan Wolverines.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "Michigan"},
            ),
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_USC",
                tier=ConnectionsTier.BRONZE,
                title="Attended USC (Southern California)",
                explanation="All 4 players played college football for the USC Trojans.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "USC"},
            ),
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_OKLAHOMA",
                tier=ConnectionsTier.BRONZE,
                title="Attended the University of Oklahoma",
                explanation="All 4 players played college football for the Oklahoma Sooners.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "Oklahoma"},
            ),
            ConnectionsCategoryDefinition(
                category_id="COLLEGE_NOTRE_DAME",
                tier=ConnectionsTier.BRONZE,
                title="Attended the University of Notre Dame",
                explanation="All 4 players played college football for the Notre Dame Fighting Irish.",
                archetype=ConnectionsCategoryArchetype.COLLEGE,
                parameters={"college": "Notre Dame"},
            ),
            ConnectionsCategoryDefinition(
                category_id="DRAFT_ROUND_1",
                tier=ConnectionsTier.BRONZE,
                title="1st Round NFL Draft Picks",
                explanation="All 4 players were selected in the 1st Round of the NFL Draft.",
                archetype=ConnectionsCategoryArchetype.DRAFT_ORIGIN,
                parameters={"draft_round": 1},
            ),
            ConnectionsCategoryDefinition(
                category_id="DRAFT_FIRST_OVERALL",
                tier=ConnectionsTier.BRONZE,
                title="#1 Overall NFL Draft Picks",
                explanation="All 4 players were selected with the 1st overall pick in the NFL Draft.",
                archetype=ConnectionsCategoryArchetype.DRAFT_ORIGIN,
                parameters={"draft_overall": 1},
            ),
            ConnectionsCategoryDefinition(
                category_id="ACCOLADE_HEISMAN",
                tier=ConnectionsTier.BRONZE,
                title="Heisman Trophy Winners",
                explanation="All 4 players won the prestigious Heisman Trophy in college football.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE,
                parameters={"accolade_type": "HEISMAN_TROPHY"},
            ),
            ConnectionsCategoryDefinition(
                category_id="ACCOLADE_HOF",
                tier=ConnectionsTier.BRONZE,
                title="Pro Football Hall of Fame Inductees",
                explanation="All 4 players have been inducted into the Pro Football Hall of Fame in Canton.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE,
                parameters={"accolade_type": "HALL_OF_FAME"},
            ),
            ConnectionsCategoryDefinition(
                category_id="FRAN_ONE_CLUB",
                tier=ConnectionsTier.BRONZE,
                title="Played for Only One NFL Franchise",
                explanation="All 4 players spent their entire NFL playing careers with a single franchise.",
                archetype=ConnectionsCategoryArchetype.FRANCHISE_TENURE,
                parameters={"single_team_only": True},
            ),
        ]
        for c in tier1_defs:
            self.register(c)

        tier2_defs = [
            ConnectionsCategoryDefinition(
                category_id="STAT_PASS_5000_SEASON",
                tier=ConnectionsTier.SILVER,
                title="5,000+ Passing Yards in a Single Season",
                explanation="All 4 quarterbacks recorded 5,000 or more passing yards in a single regular season.",
                archetype=ConnectionsCategoryArchetype.STAT_SEASON,
                parameters={"stat_column": "passing_yards", "min_val": 5000},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_PASS_4500_SEASON",
                tier=ConnectionsTier.SILVER,
                title="4,500+ Passing Yards in a Single Season",
                explanation="All 4 quarterbacks threw for at least 4,500 passing yards in a single regular season.",
                archetype=ConnectionsCategoryArchetype.STAT_SEASON,
                parameters={"stat_column": "passing_yards", "min_val": 4500},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_RUSH_1500_SEASON",
                tier=ConnectionsTier.SILVER,
                title="1,500+ Rushing Yards in a Single Season",
                explanation="All 4 running backs rushed for at least 1,500 yards in a single regular season.",
                archetype=ConnectionsCategoryArchetype.STAT_SEASON,
                parameters={"stat_column": "rushing_yards", "min_val": 1500},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_RUSH_1000_SEASON",
                tier=ConnectionsTier.SILVER,
                title="1,000+ Rushing Yards in a Single Season",
                explanation="All 4 players rushed for at least 1,000 yards in a single regular season.",
                archetype=ConnectionsCategoryArchetype.STAT_SEASON,
                parameters={"stat_column": "rushing_yards", "min_val": 1000},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_REC_1500_SEASON",
                tier=ConnectionsTier.SILVER,
                title="1,500+ Receiving Yards in a Single Season",
                explanation="All 4 receivers recorded at least 1,500 receiving yards in a single regular season.",
                archetype=ConnectionsCategoryArchetype.STAT_SEASON,
                parameters={"stat_column": "receiving_yards", "min_val": 1500},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_REC_100_SEASON",
                tier=ConnectionsTier.SILVER,
                title="100+ Receptions in a Single Season",
                explanation="All 4 players caught 100 or more passes in a single regular season.",
                archetype=ConnectionsCategoryArchetype.STAT_SEASON,
                parameters={"stat_column": "receptions", "min_val": 100},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_SACKS_15_SEASON",
                tier=ConnectionsTier.SILVER,
                title="15+ Sacks in a Single Season",
                explanation="All 4 defensive players registered 15.0 or more sacks in a single regular season.",
                archetype=ConnectionsCategoryArchetype.STAT_SEASON,
                parameters={"stat_column": "sacks", "min_val": 15.0},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_SACKS_100_CAREER",
                tier=ConnectionsTier.SILVER,
                title="100+ Career Sacks",
                explanation="All 4 pass rushers accumulated 100.0 or more official career sacks.",
                archetype=ConnectionsCategoryArchetype.STAT_CAREER,
                parameters={"stat_column": "sacks", "min_val": 100.0},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_RUSH_10000_CAREER",
                tier=ConnectionsTier.SILVER,
                title="10,000+ Career Rushing Yards",
                explanation="All 4 running backs surpassed 10,000 career rushing yards in the NFL.",
                archetype=ConnectionsCategoryArchetype.STAT_CAREER,
                parameters={"stat_column": "rushing_yards", "min_val": 10000},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_REC_10000_CAREER",
                tier=ConnectionsTier.SILVER,
                title="10,000+ Career Receiving Yards",
                explanation="All 4 receivers surpassed 10,000 career receiving yards in the NFL.",
                archetype=ConnectionsCategoryArchetype.STAT_CAREER,
                parameters={"stat_column": "receiving_yards", "min_val": 10000},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_PASS_50000_CAREER",
                tier=ConnectionsTier.SILVER,
                title="50,000+ Career Passing Yards",
                explanation="All 4 quarterbacks accumulated over 50,000 career passing yards.",
                archetype=ConnectionsCategoryArchetype.STAT_CAREER,
                parameters={"stat_column": "passing_yards", "min_val": 50000},
            ),
            ConnectionsCategoryDefinition(
                category_id="STAT_RUSH_TD_100_CAREER",
                tier=ConnectionsTier.SILVER,
                title="100+ Career Rushing Touchdowns",
                explanation="All 4 players scored 100 or more regular season rushing touchdowns.",
                archetype=ConnectionsCategoryArchetype.STAT_CAREER,
                parameters={"stat_column": "rushing_tds", "min_val": 100},
            ),
            ConnectionsCategoryDefinition(
                category_id="ACCOLADE_PRO_BOWL_5",
                tier=ConnectionsTier.SILVER,
                title="5+ Pro Bowl Selections",
                explanation="All 4 players earned at least 5 Pro Bowl selections during their NFL careers.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE,
                parameters={"accolade_type": "PRO_BOWL", "min_count": 5},
            ),
        ]
        for c in tier2_defs:
            self.register(c)

        tier3_defs = [
            ConnectionsCategoryDefinition(
                category_id="DUAL_FRAN_NE_NYJ",
                tier=ConnectionsTier.GOLD,
                title="Played for both NE Patriots & NY Jets",
                explanation="All 4 players appeared in regular season games for both New England and the New York Jets.",
                archetype=ConnectionsCategoryArchetype.DUAL_FRANCHISE,
                parameters={"franchise_a": "NE", "franchise_b": "NYJ"},
            ),
            ConnectionsCategoryDefinition(
                category_id="DUAL_FRAN_GNB_MIN",
                tier=ConnectionsTier.GOLD,
                title="Played for both GB Packers & MIN Vikings",
                explanation="All 4 players appeared in regular season games for both Green Bay and Minnesota.",
                archetype=ConnectionsCategoryArchetype.DUAL_FRANCHISE,
                parameters={"franchise_a": "GNB", "franchise_b": "MIN"},
            ),
            ConnectionsCategoryDefinition(
                category_id="DUAL_FRAN_SFO_KC",
                tier=ConnectionsTier.GOLD,
                title="Played for both SF 49ers & KC Chiefs",
                explanation="All 4 players appeared in regular season games for both San Francisco and Kansas City.",
                archetype=ConnectionsCategoryArchetype.DUAL_FRANCHISE,
                parameters={"franchise_a": "SFO", "franchise_b": "KC"},
            ),
            ConnectionsCategoryDefinition(
                category_id="DUAL_FRAN_IND_DEN",
                tier=ConnectionsTier.GOLD,
                title="Played for both IND Colts & DEN Broncos",
                explanation="All 4 players appeared in regular season games for both Indianapolis and Denver.",
                archetype=ConnectionsCategoryArchetype.DUAL_FRANCHISE,
                parameters={"franchise_a": "IND", "franchise_b": "DEN"},
            ),
            ConnectionsCategoryDefinition(
                category_id="DUAL_FRAN_DAL_PHI",
                tier=ConnectionsTier.GOLD,
                title="Played for both DAL Cowboys & PHI Eagles",
                explanation="All 4 players appeared in regular season games for both Dallas and Philadelphia.",
                archetype=ConnectionsCategoryArchetype.DUAL_FRANCHISE,
                parameters={"franchise_a": "DAL", "franchise_b": "PHI"},
            ),
            ConnectionsCategoryDefinition(
                category_id="DUAL_FRAN_CHI_DET",
                tier=ConnectionsTier.GOLD,
                title="Played for both CHI Bears & DET Lions",
                explanation="All 4 players appeared in regular season games for both Chicago and Detroit.",
                archetype=ConnectionsCategoryArchetype.DUAL_FRANCHISE,
                parameters={"franchise_a": "CHI", "franchise_b": "DET"},
            ),
            ConnectionsCategoryDefinition(
                category_id="DUAL_FRAN_PIT_BAL",
                tier=ConnectionsTier.GOLD,
                title="Played for both PIT Steelers & BAL Ravens",
                explanation="All 4 players appeared in regular season games for both Pittsburgh and Baltimore.",
                archetype=ConnectionsCategoryArchetype.DUAL_FRANCHISE,
                parameters={"franchise_a": "PIT", "franchise_b": "BAL"},
            ),
            ConnectionsCategoryDefinition(
                category_id="JOURNEYMAN_4_FRANCHISES",
                tier=ConnectionsTier.GOLD,
                title="Played for 4+ Different NFL Franchises",
                explanation="All 4 players appeared in regular season games for at least 4 distinct NFL franchises.",
                archetype=ConnectionsCategoryArchetype.STAT_CAREER,
                parameters={"min_franchises": 4},
            ),
            ConnectionsCategoryDefinition(
                category_id="DRAFT_DAY3_UDFA",
                tier=ConnectionsTier.GOLD,
                title="Drafted in Round 4 or Later / Undrafted",
                explanation="All 4 players entered the NFL as Day 3 draft selections (Round 4+) or undrafted free agents.",
                archetype=ConnectionsCategoryArchetype.DRAFT_ORIGIN,
                parameters={"draft_round_min": 4},
            ),
            ConnectionsCategoryDefinition(
                category_id="DRAFT_DAY2",
                tier=ConnectionsTier.GOLD,
                title="Day 2 Draft Picks (Rounds 2-3)",
                explanation="All 4 players were selected in either Round 2 or Round 3 of the NFL Draft.",
                archetype=ConnectionsCategoryArchetype.DRAFT_ORIGIN,
                parameters={"draft_round_min": 2, "draft_round_max": 3},
            ),
            ConnectionsCategoryDefinition(
                category_id="ACCOLADE_AP_MVP",
                tier=ConnectionsTier.GOLD,
                title="AP NFL Most Valuable Player (MVP) Winners",
                explanation="All 4 players won the Associated Press NFL MVP award.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE,
                parameters={"accolade_type": "MVP"},
            ),
            ConnectionsCategoryDefinition(
                category_id="ACCOLADE_SUPER_BOWL_MVP",
                tier=ConnectionsTier.GOLD,
                title="Super Bowl MVPs",
                explanation="All 4 players were awarded the Pete Rozelle Super Bowl Most Valuable Player Award.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE,
                parameters={"accolade_type": "SUPER_BOWL_MVP"},
            ),
            ConnectionsCategoryDefinition(
                category_id="ACCOLADE_OROY_DROY",
                tier=ConnectionsTier.GOLD,
                title="AP NFL Rookie of the Year Winners (OROY / DROY)",
                explanation="All 4 players won either Offensive or Defensive Rookie of the Year.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE,
                parameters={"accolade_type": "ROOKIE_OF_YEAR"},
            ),
        ]
        for c in tier3_defs:
            self.register(c)

        tier4_defs = [
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_MICHAEL",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'Michael' or 'Mike'",
                explanation="All 4 players share the canonical first name Michael or Mike.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["Michael", "Mike"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_CHRIS",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'Chris' or 'Christopher'",
                explanation="All 4 players share the canonical first name Chris or Christopher.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["Chris", "Christopher"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_JOHN",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'John', 'Johnny', or 'Jonathan'",
                explanation="All 4 players share the canonical first name John, Johnny, or Jonathan.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["John", "Johnny", "Jonathan"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_MATT",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'Matt' or 'Matthew'",
                explanation="All 4 players share the canonical first name Matt or Matthew.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["Matt", "Matthew"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_DAVID",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'David' or 'Dave'",
                explanation="All 4 players share the canonical first name David or Dave.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["David", "Dave"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_BRIAN",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'Brian' or 'Bryan'",
                explanation="All 4 players share the canonical first name Brian or Bryan.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["Brian", "Bryan"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_RYAN",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'Ryan'",
                explanation="All 4 players share the canonical first name Ryan.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["Ryan"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_BRANDON",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'Brandon'",
                explanation="All 4 players share the canonical first name Brandon.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["Brandon"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_JAMES",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'James', 'Jim', or 'Jimmy'",
                explanation="All 4 players share the canonical first name James, Jim, or Jimmy.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["James", "Jim", "Jimmy"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="NAME_FIRST_JUSTIN",
                tier=ConnectionsTier.PLATINUM,
                title="Shared First Name 'Justin'",
                explanation="All 4 players share the canonical first name Justin.",
                archetype=ConnectionsCategoryArchetype.DEMOGRAPHIC_NAME,
                parameters={"first_names": ["Justin"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="PEDIGREE_FIRST_OVERALL_SB",
                tier=ConnectionsTier.PLATINUM,
                title="Drafted #1 Overall and Won a Super Bowl",
                explanation="All 4 players were selected #1 overall in the NFL draft and won a Super Bowl championship.",
                archetype=ConnectionsCategoryArchetype.PEDIGREE_QUIRK,
                parameters={"first_overall": True, "super_bowl": True},
            ),
            ConnectionsCategoryDefinition(
                category_id="PEDIGREE_HEISMAN_AND_MVP",
                tier=ConnectionsTier.PLATINUM,
                title="Won both Heisman Trophy and NFL MVP",
                explanation="All 4 legends won both the college Heisman Trophy and the AP NFL Most Valuable Player award.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE_COMBO,
                parameters={"accolades": ["HEISMAN_TROPHY", "MVP"]},
            ),
            ConnectionsCategoryDefinition(
                category_id="PEDIGREE_SB_MVP_AND_LEAGUE_MVP",
                tier=ConnectionsTier.PLATINUM,
                title="Won both Super Bowl MVP and NFL MVP",
                explanation="All 4 players captured both the AP NFL MVP and Super Bowl MVP awards during their careers.",
                archetype=ConnectionsCategoryArchetype.ACCOLADE_COMBO,
                parameters={"accolades": ["SUPER_BOWL_MVP", "MVP"]},
            ),
        ]
        for c in tier4_defs:
            self.register(c)


# Singleton instance of the Connections taxonomy registry
connections_registry = ConnectionsTaxonomyRegistry()
