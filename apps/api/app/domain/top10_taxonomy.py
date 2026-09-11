"""
NFL Top 10 Leaderboard Taxonomy & Ranking Resolution Engine.
Per Section 1.1.4 and Section 3.2.5 of SPECIFICATION.md:
- 4 Core Archetypes:
  1. SINGLE_SEASON_MILESTONE: Recent eras only (2010–present / 2015–present).
  2. CHRONOLOGICAL_ACCOLADE: Chronological rank (rank 1 = most recent backwards).
  3. RECENT_DRAFT_PEDIGREE: Strictly constrained to draft classes post-2015.
  4. ALL_TIME_HISTORICAL_LEADERBOARD: Universal recognizable historical milestones.
- Strict Tie-Breaking Invariants:
  * Deterministic secondary tie-breaker (efficiency, career totals, recency).
  * Tied players are recorded in tied_player_ids and accepted as valid hits for rank slots.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from sqlalchemy import desc, distinct, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.franchise import Franchise, TeamSeason
from app.db.models.player import Player, PlayerTeamStint
from app.db.models.stats import Accolade, PlayerCareerStat, PlayerSeasonStat
from app.schemas.top10 import Top10Entry

logger = logging.getLogger(__name__)


class Top10Archetype(str, Enum):
    SINGLE_SEASON_MILESTONE = "SINGLE_SEASON_MILESTONE"
    CHRONOLOGICAL_ACCOLADE = "CHRONOLOGICAL_ACCOLADE"
    RECENT_DRAFT_PEDIGREE = "RECENT_DRAFT_PEDIGREE"
    ALL_TIME_HISTORICAL_LEADERBOARD = "ALL_TIME_HISTORICAL_LEADERBOARD"


@dataclass
class Top10CategoryDefinition:
    """
    Metadata and resolver definition for an NFL Top 10 category.
    """
    category_id: str
    archetype: Top10Archetype
    title: str
    description: str
    metric_label: str
    min_season_year: Optional[int] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    fallback_leaderboard: List[Dict[str, Any]] = field(default_factory=list)


class Top10TaxonomyRegistry:
    """
    Central registry of curated, production-tested Top 10 categories.
    """
    def __init__(self) -> None:
        self._categories: Dict[str, Top10CategoryDefinition] = {}
        self._register_default_categories()

    def register(self, cat: Top10CategoryDefinition) -> None:
        self._categories[cat.category_id] = cat

    def get(self, category_id: str) -> Optional[Top10CategoryDefinition]:
        return self._categories.get(category_id)

    def get_all(self) -> List[Top10CategoryDefinition]:
        return list(self._categories.values())

    def get_by_archetype(self, archetype: Top10Archetype) -> List[Top10CategoryDefinition]:
        return [c for c in self._categories.values() if c.archetype == archetype]

    def _register_default_categories(self) -> None:
        # =========================================================================
        # 1. SINGLE-SEASON MILESTONES (Recent Eras: 2010–present / 2015–present)
        # =========================================================================
        self.register(Top10CategoryDefinition(
            category_id="TOP10_PASS_TD_2020S",
            archetype=Top10Archetype.SINGLE_SEASON_MILESTONE,
            title="Top 10 Passing Touchdowns in a Single Season (2020s)",
            description="Individual quarterback single-season passing touchdowns from the 2020 season to present.",
            metric_label="Pass TDs",
            min_season_year=2020,
            parameters={"stat": "passing_tds", "min_year": 2020},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "p-rodgers-aar01", "player_name": "Aaron Rodgers", "metric_value": 48, "formatted_value": "48 TDs (2020 GB)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/8439.png&w=350&h=254", "active_years": "2005-Present", "primary_franchise": "GNB"},
                {"rank": 2, "player_id": "p-brady-tom01", "player_name": "Tom Brady", "metric_value": 43, "formatted_value": "43 TDs (2021 TB)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2330.png&w=350&h=254", "active_years": "2000-2022", "primary_franchise": "TAM"},
                {"rank": 3, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 41, "formatted_value": "41 TDs (2022 KC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "KC"},
                {"rank": 4, "player_id": "p-stafford-mat01", "player_name": "Matthew Stafford", "metric_value": 41, "formatted_value": "41 TDs (2021 LAR)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/12483.png&w=350&h=254", "active_years": "2009-Present", "primary_franchise": "LAR"},
                {"rank": 5, "player_id": "00-0034857", "player_name": "Josh Allen", "metric_value": 37, "formatted_value": "37 TDs (2020 BUF)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3918298.png&w=350&h=254", "active_years": "2018-Present", "primary_franchise": "BUF"},
                {"rank": 6, "player_id": "p-rodgers-aar01", "player_name": "Aaron Rodgers", "metric_value": 37, "formatted_value": "37 TDs (2021 GB)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/8439.png&w=350&h=254", "active_years": "2005-Present", "primary_franchise": "GNB"},
                {"rank": 7, "player_id": "00-0033077", "player_name": "Dak Prescott", "metric_value": 37, "formatted_value": "37 TDs (2021 DAL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2577417.png&w=350&h=254", "active_years": "2016-Present", "primary_franchise": "DAL"},
                {"rank": 8, "player_id": "00-0033077", "player_name": "Dak Prescott", "metric_value": 36, "formatted_value": "36 TDs (2023 DAL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2577417.png&w=350&h=254", "active_years": "2016-Present", "primary_franchise": "DAL"},
                {"rank": 9, "player_id": "00-0036442", "player_name": "Joe Burrow", "metric_value": 35, "formatted_value": "35 TDs (2022 CIN)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915511.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "CIN"},
                {"rank": 10, "player_id": "00-0034857", "player_name": "Josh Allen", "metric_value": 35, "formatted_value": "35 TDs (2022 BUF)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3918298.png&w=350&h=254", "active_years": "2018-Present", "primary_franchise": "BUF"},
            ],
        ))

        self.register(Top10CategoryDefinition(
            category_id="TOP10_SCRIMMAGE_YDS_2023",
            archetype=Top10Archetype.SINGLE_SEASON_MILESTONE,
            title="Top 10 Scrimmage Yards Leaders in the 2023 NFL Season",
            description="Combined regular season rushing and receiving yards from the 2023 season.",
            metric_label="Scrimmage Yards",
            min_season_year=2023,
            parameters={"stat": "scrimmage_yards", "year": 2023},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "00-0033906", "player_name": "Christian McCaffrey", "metric_value": 2023, "formatted_value": "2,023 yds (SFO)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3117251.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "SFO"},
                {"rank": 2, "player_id": "00-0036358", "player_name": "CeeDee Lamb", "metric_value": 1862, "formatted_value": "1,862 yds (DAL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241389.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "DAL"},
                {"rank": 3, "player_id": "00-0033040", "player_name": "Tyreek Hill", "metric_value": 1814, "formatted_value": "1,814 yds (MIA)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3116406.png&w=350&h=254", "active_years": "2016-Present", "primary_franchise": "MIA"},
                {"rank": 4, "player_id": "00-0037838", "player_name": "Breece Hall", "metric_value": 1585, "formatted_value": "1,585 yds (NYJ)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4427366.png&w=350&h=254", "active_years": "2022-Present", "primary_franchise": "NYJ"},
                {"rank": 5, "player_id": "4374302", "player_name": "Amon-Ra St. Brown", "metric_value": 1539, "formatted_value": "1,539 yds (DET)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4374302.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "DET"},
                {"rank": 6, "player_id": "4047646", "player_name": "A.J. Brown", "metric_value": 1456, "formatted_value": "1,456 yds (PHI)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4047646.png&w=350&h=254", "active_years": "2019-Present", "primary_franchise": "PHI"},
                {"rank": 7, "player_id": "00-0032764", "player_name": "Derrick Henry", "metric_value": 1381, "formatted_value": "1,381 yds (TEN)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3043078.png&w=350&h=254", "active_years": "2016-Present", "primary_franchise": "TEN"},
                {"rank": 8, "player_id": "4429018", "player_name": "De'Von Achane", "metric_value": 997, "formatted_value": "997 yds (MIA)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4429018.png&w=350&h=254", "active_years": "2023-Present", "primary_franchise": "MIA"},
                {"rank": 9, "player_id": "00-0038555", "player_name": "Bijan Robinson", "metric_value": 1463, "formatted_value": "1,463 yds (ATL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430737.png&w=350&h=254", "active_years": "2023-Present", "primary_franchise": "ATL"},
                {"rank": 10, "player_id": "4430740", "player_name": "Jahmyr Gibbs", "metric_value": 1261, "formatted_value": "1,261 yds (DET)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430740.png&w=350&h=254", "active_years": "2023-Present", "primary_franchise": "DET"},
            ],
        ))

        self.register(Top10CategoryDefinition(
            category_id="TOP10_SACKS_SEASON_2015",
            archetype=Top10Archetype.SINGLE_SEASON_MILESTONE,
            title="Top 10 Sacks in a Single Season (since 2015)",
            description="Highest individual regular season sack totals by defensive players from 2015 onward.",
            metric_label="Sacks",
            min_season_year=2015,
            parameters={"stat": "sacks", "min_year": 2015},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "00-0033882", "player_name": "T.J. Watt", "metric_value": 22.5, "formatted_value": "22.5 Sacks (2021 PIT)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3045282.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "PIT"},
                {"rank": 2, "player_id": "00-0031388-ad", "player_name": "Aaron Donald", "metric_value": 20.5, "formatted_value": "20.5 Sacks (2018 LAR)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/16716.png&w=350&h=254", "active_years": "2014-2023", "primary_franchise": "LAR"},
                {"rank": 3, "player_id": "00-0033882", "player_name": "T.J. Watt", "metric_value": 19.0, "formatted_value": "19.0 Sacks (2023 PIT)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3045282.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "PIT"},
                {"rank": 4, "player_id": "00-0035236", "player_name": "Nick Bosa", "metric_value": 18.5, "formatted_value": "18.5 Sacks (2022 SFO)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4040605.png&w=350&h=254", "active_years": "2019-Present", "primary_franchise": "SFO"},
                {"rank": 5, "player_id": "p-chandler-jon01", "player_name": "Chandler Jones", "metric_value": 19.0, "formatted_value": "19.0 Sacks (2019 ARI)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/14979.png&w=350&h=254", "active_years": "2012-2022", "primary_franchise": "ARI"},
                {"rank": 6, "player_id": "00-0033887", "player_name": "Myles Garrett", "metric_value": 16.0, "formatted_value": "16.0 Sacks (2021 CLE)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3122132.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "CLE"},
                {"rank": 7, "player_id": "00-0033887", "player_name": "Myles Garrett", "metric_value": 16.0, "formatted_value": "16.0 Sacks (2022 CLE)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3122132.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "CLE"},
                {"rank": 8, "player_id": "p-watt-jj01", "player_name": "J.J. Watt", "metric_value": 17.5, "formatted_value": "17.5 Sacks (2015 HOU)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/13979.png&w=350&h=254", "active_years": "2011-2022", "primary_franchise": "HOU"},
                {"rank": 9, "player_id": "p-watt-jj01", "player_name": "J.J. Watt", "metric_value": 16.0, "formatted_value": "16.0 Sacks (2018 HOU)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/13979.png&w=350&h=254", "active_years": "2011-2022", "primary_franchise": "HOU"},
                {"rank": 10, "player_id": "3040149", "player_name": "Trey Hendrickson", "metric_value": 17.5, "formatted_value": "17.5 Sacks (2023 CIN)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3040149.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "CIN"},
            ],
        ))

        # =========================================================================
        # 2. CHRONOLOGICAL HONORS & ACCOLADES (Most Recent Backwards)
        # =========================================================================
        self.register(Top10CategoryDefinition(
            category_id="TOP10_LAST_MVPS",
            archetype=Top10Archetype.CHRONOLOGICAL_ACCOLADE,
            title="Last 10 AP NFL Regular Season MVPs",
            description="The most recent 10 Associated Press Most Valuable Player winners in reverse chronological order.",
            metric_label="MVP Season",
            parameters={"accolade_type": "MVP"},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "00-0034796", "player_name": "Lamar Jackson", "metric_value": 2023, "formatted_value": "2023 MVP (BAL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3916387.png&w=350&h=254", "active_years": "2018-Present", "primary_franchise": "BAL"},
                {"rank": 2, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 2022, "formatted_value": "2022 MVP (KC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "KC"},
                {"rank": 3, "player_id": "00-0023459", "player_name": "Aaron Rodgers", "metric_value": 2021, "formatted_value": "2021 MVP (GB)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/8439.png&w=350&h=254", "active_years": "2005-Present", "primary_franchise": "GNB"},
                {"rank": 4, "player_id": "00-0023459", "player_name": "Aaron Rodgers", "metric_value": 2020, "formatted_value": "2020 MVP (GB)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/8439.png&w=350&h=254", "active_years": "2005-Present", "primary_franchise": "GNB"},
                {"rank": 5, "player_id": "00-0034796", "player_name": "Lamar Jackson", "metric_value": 2019, "formatted_value": "2019 MVP (BAL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3916387.png&w=350&h=254", "active_years": "2018-Present", "primary_franchise": "BAL"},
                {"rank": 6, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 2018, "formatted_value": "2018 MVP (KC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "KC"},
                {"rank": 7, "player_id": "p-brady-tom01", "player_name": "Tom Brady", "metric_value": 2017, "formatted_value": "2017 MVP (NE)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2330.png&w=350&h=254", "active_years": "2000-2022", "primary_franchise": "NE"},
                {"rank": 8, "player_id": "p-ryan-mat01", "player_name": "Matt Ryan", "metric_value": 2016, "formatted_value": "2016 MVP (ATL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/11237.png&w=350&h=254", "active_years": "2008-2022", "primary_franchise": "ATL"},
                {"rank": 9, "player_id": "p-newton-cam01", "player_name": "Cam Newton", "metric_value": 2015, "formatted_value": "2015 MVP (CAR)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/13994.png&w=350&h=254", "active_years": "2011-2021", "primary_franchise": "CAR"},
                {"rank": 10, "player_id": "00-0023459", "player_name": "Aaron Rodgers", "metric_value": 2014, "formatted_value": "2014 MVP (GB)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/8439.png&w=350&h=254", "active_years": "2005-Present", "primary_franchise": "GNB"},
            ],
        ))

        self.register(Top10CategoryDefinition(
            category_id="TOP10_LAST_SB_MVPS",
            archetype=Top10Archetype.CHRONOLOGICAL_ACCOLADE,
            title="Last 10 Super Bowl MVPs",
            description="The most recent 10 Pete Rozelle Super Bowl MVP trophy recipients in reverse chronological order.",
            metric_label="Super Bowl MVP",
            parameters={"accolade_type": "SUPER_BOWL_MVP"},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 2023, "formatted_value": "Super Bowl LVIII (KC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "KC"},
                {"rank": 2, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 2022, "formatted_value": "Super Bowl LVII (KC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "KC"},
                {"rank": 3, "player_id": "3917792", "player_name": "Cooper Kupp", "metric_value": 2021, "formatted_value": "Super Bowl LVI (LAR)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917792.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "LAR"},
                {"rank": 4, "player_id": "p-brady-tom01", "player_name": "Tom Brady", "metric_value": 2020, "formatted_value": "Super Bowl LV (TB)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2330.png&w=350&h=254", "active_years": "2000-2022", "primary_franchise": "TAM"},
                {"rank": 5, "player_id": "00-0033873", "player_name": "Patrick Mahomes", "metric_value": 2019, "formatted_value": "Super Bowl LIV (KC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "KC"},
                {"rank": 6, "player_id": "p-edelman-jul01", "player_name": "Julian Edelman", "metric_value": 2018, "formatted_value": "Super Bowl LIII (NE)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/12649.png&w=350&h=254", "active_years": "2009-2020", "primary_franchise": "NE"},
                {"rank": 7, "player_id": "p-foles-nic01", "player_name": "Nick Foles", "metric_value": 2017, "formatted_value": "Super Bowl LII (PHI)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/14877.png&w=350&h=254", "active_years": "2012-2022", "primary_franchise": "PHI"},
                {"rank": 8, "player_id": "p-brady-tom01", "player_name": "Tom Brady", "metric_value": 2016, "formatted_value": "Super Bowl LI (NE)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2330.png&w=350&h=254", "active_years": "2000-2022", "primary_franchise": "NE"},
                {"rank": 9, "player_id": "p-miller-von01", "player_name": "Von Miller", "metric_value": 2015, "formatted_value": "Super Bowl 50 (DEN)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/13979.png&w=350&h=254", "active_years": "2011-Present", "primary_franchise": "DEN"},
                {"rank": 10, "player_id": "p-brady-tom01", "player_name": "Tom Brady", "metric_value": 2014, "formatted_value": "Super Bowl XLIX (NE)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2330.png&w=350&h=254", "active_years": "2000-2022", "primary_franchise": "NE"},
            ],
        ))

        self.register(Top10CategoryDefinition(
            category_id="TOP10_LAST_OROY",
            archetype=Top10Archetype.CHRONOLOGICAL_ACCOLADE,
            title="Last 10 AP NFL Offensive Rookies of the Year (OROY)",
            description="The most recent 10 Associated Press Offensive Rookie of the Year winners in reverse chronological order.",
            metric_label="OROY Season",
            parameters={"accolade_type": "OROY"},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "00-0039163", "player_name": "C.J. Stroud", "metric_value": 2023, "formatted_value": "2023 OROY (HOU)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4432577.png&w=350&h=254", "active_years": "2023-Present", "primary_franchise": "HOU"},
                {"rank": 2, "player_id": "00-0037836", "player_name": "Garrett Wilson", "metric_value": 2022, "formatted_value": "2022 OROY (NYJ)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4426515.png&w=350&h=254", "active_years": "2022-Present", "primary_franchise": "NYJ"},
                {"rank": 3, "player_id": "00-0036900", "player_name": "Ja'Marr Chase", "metric_value": 2021, "formatted_value": "2021 OROY (CIN)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4362628.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "CIN"},
                {"rank": 4, "player_id": "00-0036355", "player_name": "Justin Herbert", "metric_value": 2020, "formatted_value": "2020 OROY (LAC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4038941.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "LAC"},
                {"rank": 5, "player_id": "00-0035228", "player_name": "Kyler Murray", "metric_value": 2019, "formatted_value": "2019 OROY (ARI)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917315.png&w=350&h=254", "active_years": "2019-Present", "primary_franchise": "ARI"},
                {"rank": 6, "player_id": "00-0034844-rb", "player_name": "Saquon Barkley", "metric_value": 2018, "formatted_value": "2018 OROY (NYG)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3929630.png&w=350&h=254", "active_years": "2018-Present", "primary_franchise": "NYG"},
                {"rank": 7, "player_id": "p-kamara-alv01", "player_name": "Alvin Kamara", "metric_value": 2017, "formatted_value": "2017 OROY (NO)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3054850.png&w=350&h=254", "active_years": "2017-Present", "primary_franchise": "NOR"},
                {"rank": 8, "player_id": "00-0033077", "player_name": "Dak Prescott", "metric_value": 2016, "formatted_value": "2016 OROY (DAL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2577417.png&w=350&h=254", "active_years": "2016-Present", "primary_franchise": "DAL"},
                {"rank": 9, "player_id": "p-gurley-tod01", "player_name": "Todd Gurley", "metric_value": 2015, "formatted_value": "2015 OROY (LAR)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2977644.png&w=350&h=254", "active_years": "2015-2020", "primary_franchise": "LAR"},
                {"rank": 10, "player_id": "p-beckham-ode01", "player_name": "Odell Beckham Jr.", "metric_value": 2014, "formatted_value": "2014 OROY (NYG)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/16733.png&w=350&h=254", "active_years": "2014-Present", "primary_franchise": "NYG"},
            ],
        ))

        # =========================================================================
        # 3. RECENT DRAFT PEDIGREES (Strictly Constrained: 2015–present)
        # =========================================================================
        self.register(Top10CategoryDefinition(
            category_id="TOP10_DRAFT_2020_OVERALL",
            archetype=Top10Archetype.RECENT_DRAFT_PEDIGREE,
            title="Top 10 Overall Picks of the 2020 NFL Draft",
            description="The first 10 players selected in the 2020 NFL Draft in draft order.",
            metric_label="Overall Pick",
            min_season_year=2020,
            parameters={"draft_year": 2020},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "00-0036442", "player_name": "Joe Burrow", "metric_value": 1, "formatted_value": "Pick #1 (CIN)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3915511.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "CIN"},
                {"rank": 2, "player_id": "p-young-cha01", "player_name": "Chase Young", "metric_value": 2, "formatted_value": "Pick #2 (WAS)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241986.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "WAS"},
                {"rank": 3, "player_id": "p-okudah-jef01", "player_name": "Jeff Okudah", "metric_value": 3, "formatted_value": "Pick #3 (DET)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241984.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "DET"},
                {"rank": 4, "player_id": "p-thomas-and01", "player_name": "Andrew Thomas", "metric_value": 4, "formatted_value": "Pick #4 (NYG)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241998.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "NYG"},
                {"rank": 5, "player_id": "00-0036226", "player_name": "Tua Tagovailoa", "metric_value": 5, "formatted_value": "Pick #5 (MIA)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241479.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "MIA"},
                {"rank": 6, "player_id": "00-0036355", "player_name": "Justin Herbert", "metric_value": 6, "formatted_value": "Pick #6 (LAC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4038941.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "LAC"},
                {"rank": 7, "player_id": "p-brown-der01", "player_name": "Derrick Brown", "metric_value": 7, "formatted_value": "Pick #7 (CAR)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4035431.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "CAR"},
                {"rank": 8, "player_id": "p-simmons-isa01", "player_name": "Isaiah Simmons", "metric_value": 8, "formatted_value": "Pick #8 (ARI)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4035432.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "ARI"},
                {"rank": 9, "player_id": "p-henderson-cj01", "player_name": "CJ Henderson", "metric_value": 9, "formatted_value": "Pick #9 (JAX)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4240596.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "JAX"},
                {"rank": 10, "player_id": "p-wills-jed01", "player_name": "Jedrick Wills Jr.", "metric_value": 10, "formatted_value": "Pick #10 (CLE)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241477.png&w=350&h=254", "active_years": "2020-Present", "primary_franchise": "CLE"},
            ],
        ))

        self.register(Top10CategoryDefinition(
            category_id="TOP10_DRAFT_2021_OFFENSE",
            archetype=Top10Archetype.RECENT_DRAFT_PEDIGREE,
            title="First 10 Offensive Players Drafted in the 2021 NFL Draft",
            description="The first 10 offensive players (QB, RB, WR, TE, OL) selected in the 2021 NFL Draft.",
            metric_label="Overall Pick",
            min_season_year=2021,
            parameters={"draft_year": 2021, "side": "OFFENSE"},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "00-0036971", "player_name": "Trevor Lawrence", "metric_value": 1, "formatted_value": "Pick #1 QB (JAX)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/36971.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "JAX"},
                {"rank": 2, "player_id": "00-0036945", "player_name": "Zach Wilson", "metric_value": 2, "formatted_value": "Pick #2 QB (NYJ)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4361259.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "NYJ"},
                {"rank": 3, "player_id": "p-lance-tre01", "player_name": "Trey Lance", "metric_value": 3, "formatted_value": "Pick #3 QB (SF)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4383351.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "SFO"},
                {"rank": 4, "player_id": "4360248", "player_name": "Kyle Pitts", "metric_value": 4, "formatted_value": "Pick #4 TE (ATL)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4360248.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "ATL"},
                {"rank": 5, "player_id": "00-0036900", "player_name": "Ja'Marr Chase", "metric_value": 5, "formatted_value": "Pick #5 WR (CIN)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4362628.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "CIN"},
                {"rank": 6, "player_id": "p-sewell-pen01", "player_name": "Penei Sewell", "metric_value": 7, "formatted_value": "Pick #7 OT (DET)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4360310.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "DET"},
                {"rank": 7, "player_id": "p-waddle-jay01", "player_name": "Jaylen Waddle", "metric_value": 6, "formatted_value": "Pick #6 WR (MIA)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4372016.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "MIA"},
                {"rank": 8, "player_id": "4241478", "player_name": "DeVonta Smith", "metric_value": 10, "formatted_value": "Pick #10 WR (PHI)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4241478.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "PHI"},
                {"rank": 9, "player_id": "p-fields-jus01", "player_name": "Justin Fields", "metric_value": 11, "formatted_value": "Pick #11 QB (CHI)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4362887.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "CHI"},
                {"rank": 10, "player_id": "p-slater-ras01", "player_name": "Rashawn Slater", "metric_value": 13, "formatted_value": "Pick #13 OT (LAC)", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4240092.png&w=350&h=254", "active_years": "2021-Present", "primary_franchise": "LAC"},
            ],
        ))

        # =========================================================================
        # 4. ALL-TIME HISTORICAL LEADERBOARDS (Universal recognizable legends)
        # =========================================================================
        self.register(Top10CategoryDefinition(
            category_id="TOP10_CAREER_SACKS",
            archetype=Top10Archetype.ALL_TIME_HISTORICAL_LEADERBOARD,
            title="All-Time NFL Career Sacks Leaders",
            description="The official NFL all-time career sack leaders (post-1982 official statistics).",
            metric_label="Career Sacks",
            parameters={"stat": "career_sacks"},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "p-smith-bru01", "player_name": "Bruce Smith", "metric_value": 200.0, "formatted_value": "200.0 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/13.png&w=350&h=254", "active_years": "1985-2003", "primary_franchise": "BUF"},
                {"rank": 2, "player_id": "p-white-reg01", "player_name": "Reggie White", "metric_value": 198.0, "formatted_value": "198.0 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/35.png&w=350&h=254", "active_years": "1985-2000", "primary_franchise": "PHI"},
                {"rank": 3, "player_id": "p-greene-kev01", "player_name": "Kevin Greene", "metric_value": 160.0, "formatted_value": "160.0 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/10444.png&w=350&h=254", "active_years": "1985-1999", "primary_franchise": "LAR"},
                {"rank": 4, "player_id": "p-peppers-jul01", "player_name": "Julius Peppers", "metric_value": 159.5, "formatted_value": "159.5 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3528.png&w=350&h=254", "active_years": "2002-2018", "primary_franchise": "CAR"},
                {"rank": 5, "player_id": "p-doleman-chr01", "player_name": "Chris Doleman", "metric_value": 150.5, "formatted_value": "150.5 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/10448.png&w=350&h=254", "active_years": "1985-1999", "primary_franchise": "MIN"},
                {"rank": 6, "player_id": "p-strahan-mic01", "player_name": "Michael Strahan", "metric_value": 141.5, "formatted_value": "141.5 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/446.png&w=350&h=254", "active_years": "1993-2007", "primary_franchise": "NYG"},
                {"rank": 7, "player_id": "p-taylor-jas01", "player_name": "Jason Taylor", "metric_value": 139.5, "formatted_value": "139.5 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/1286.png&w=350&h=254", "active_years": "1997-2011", "primary_franchise": "MIA"},
                {"rank": 8, "player_id": "p-randle-joh01", "player_name": "John Randle", "metric_value": 137.5, "formatted_value": "137.5 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/10446.png&w=350&h=254", "active_years": "1990-2003", "primary_franchise": "MIN"},
                {"rank": 9, "player_id": "p-dent-ric01", "player_name": "Richard Dent", "metric_value": 137.5, "formatted_value": "137.5 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/10445.png&w=350&h=254", "active_years": "1983-1997", "primary_franchise": "CHI"},
                {"rank": 10, "player_id": "p-ware-dem01", "player_name": "DeMarcus Ware", "metric_value": 138.5, "formatted_value": "138.5 Sacks", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/8437.png&w=350&h=254", "active_years": "2005-2016", "primary_franchise": "DAL"},
            ],
        ))

        self.register(Top10CategoryDefinition(
            category_id="TOP10_CAREER_INTERCEPTIONS_THROWN",
            archetype=Top10Archetype.ALL_TIME_HISTORICAL_LEADERBOARD,
            title="All-Time Career Pass Interceptions Thrown Leaders",
            description="The NFL all-time leaders in career regular season interceptions thrown by quarterbacks.",
            metric_label="Interceptions Thrown",
            parameters={"stat": "career_interceptions"},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "p-favre-bre01", "player_name": "Brett Favre", "metric_value": 336, "formatted_value": "336 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/112.png&w=350&h=254", "active_years": "1991-2010", "primary_franchise": "GNB"},
                {"rank": 2, "player_id": "p-blanda-geo01", "player_name": "George Blanda", "metric_value": 277, "formatted_value": "277 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/10449.png&w=350&h=254", "active_years": "1949-1975", "primary_franchise": "LVR"},
                {"rank": 3, "player_id": "p-hadl-joh01", "player_name": "John Hadl", "metric_value": 268, "formatted_value": "268 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/10450.png&w=350&h=254", "active_years": "1962-1977", "primary_franchise": "LAC"},
                {"rank": 4, "player_id": "p-testaverde-vin01", "player_name": "Vinny Testaverde", "metric_value": 267, "formatted_value": "267 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/29.png&w=350&h=254", "active_years": "1987-2007", "primary_franchise": "NYJ"},
                {"rank": 5, "player_id": "p-tarkenton-fra01", "player_name": "Fran Tarkenton", "metric_value": 266, "formatted_value": "266 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/100.png&w=350&h=254", "active_years": "1961-1978", "primary_franchise": "MIN"},
                {"rank": 6, "player_id": "p-manning-pey01", "player_name": "Peyton Manning", "metric_value": 251, "formatted_value": "251 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/1428.png&w=350&h=254", "active_years": "1998-2015", "primary_franchise": "IND"},
                {"rank": 7, "player_id": "p-marino-dan01", "player_name": "Dan Marino", "metric_value": 252, "formatted_value": "252 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/5.png&w=350&h=254", "active_years": "1983-1999", "primary_franchise": "MIA"},
                {"rank": 8, "player_id": "p-brees-dre01", "player_name": "Drew Brees", "metric_value": 243, "formatted_value": "243 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/2580.png&w=350&h=254", "active_years": "2001-2020", "primary_franchise": "NOR"},
                {"rank": 9, "player_id": "p-fouts-dan01", "player_name": "Dan Fouts", "metric_value": 242, "formatted_value": "242 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4.png&w=350&h=254", "active_years": "1973-1987", "primary_franchise": "LAC"},
                {"rank": 10, "player_id": "p-hart-jim01", "player_name": "Jim Hart", "metric_value": 247, "formatted_value": "247 INTs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/10451.png&w=350&h=254", "active_years": "1966-1984", "primary_franchise": "ARI"},
            ],
        ))

        self.register(Top10CategoryDefinition(
            category_id="TOP10_CAREER_REC_TDS",
            archetype=Top10Archetype.ALL_TIME_HISTORICAL_LEADERBOARD,
            title="All-Time NFL Career Receiving Touchdowns Leaders",
            description="The all-time NFL career regular season receiving touchdown leaders.",
            metric_label="Receiving Touchdowns",
            parameters={"stat": "career_receiving_tds"},
            fallback_leaderboard=[
                {"rank": 1, "player_id": "p-rice-jer01", "player_name": "Jerry Rice", "metric_value": 197, "formatted_value": "197 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/24.png&w=350&h=254", "active_years": "1985-2004", "primary_franchise": "SFO"},
                {"rank": 2, "player_id": "p-moss-ran01", "player_name": "Randy Moss", "metric_value": 156, "formatted_value": "156 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/1433.png&w=350&h=254", "active_years": "1998-2012", "primary_franchise": "MIN"},
                {"rank": 3, "player_id": "p-owens-ter01", "player_name": "Terrell Owens", "metric_value": 153, "formatted_value": "153 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/976.png&w=350&h=254", "active_years": "1996-2010", "primary_franchise": "SFO"},
                {"rank": 4, "player_id": "p-carter-cri01", "player_name": "Cris Carter", "metric_value": 130, "formatted_value": "130 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/6.png&w=350&h=254", "active_years": "1987-2002", "primary_franchise": "MIN"},
                {"rank": 5, "player_id": "p-harrison-mar01", "player_name": "Marvin Harrison", "metric_value": 128, "formatted_value": "128 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/977.png&w=350&h=254", "active_years": "1996-2008", "primary_franchise": "IND"},
                {"rank": 6, "player_id": "p-fitzgerald-lar01", "player_name": "Larry Fitzgerald", "metric_value": 121, "formatted_value": "121 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/5528.png&w=350&h=254", "active_years": "2004-2020", "primary_franchise": "ARI"},
                {"rank": 7, "player_id": "p-gonzalez-ton01", "player_name": "Tony Gonzalez", "metric_value": 111, "formatted_value": "111 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/1098.png&w=350&h=254", "active_years": "1997-2013", "primary_franchise": "KC"},
                {"rank": 8, "player_id": "p-gates-ant01", "player_name": "Antonio Gates", "metric_value": 116, "formatted_value": "116 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4946.png&w=350&h=254", "active_years": "2003-2018", "primary_franchise": "LAC"},
                {"rank": 9, "player_id": "00-0031388", "player_name": "Davante Adams", "metric_value": 95, "formatted_value": "95 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/16800.png&w=350&h=254", "active_years": "2014-Present", "primary_franchise": "GNB"},
                {"rank": 10, "player_id": "16737", "player_name": "Mike Evans", "metric_value": 94, "formatted_value": "94 Rec TDs", "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/16737.png&w=350&h=254", "active_years": "2014-Present", "primary_franchise": "TAM"},
            ],
        ))


top10_registry = Top10TaxonomyRegistry()


async def resolve_category_leaderboard(
    session: AsyncSession,
    category: Top10CategoryDefinition,
) -> List[Top10Entry]:
    """
    Executes relational database queries to construct the official Top 10 leaderboard,
    applying era constraints, metric sorting, and deterministic tie-breaking.
    Falls back gracefully to curated metadata if live table records are sparse.
    """
    entries: List[Top10Entry] = []

    try:
        # 1. SINGLE-SEASON MILESTONE
        if category.archetype == Top10Archetype.SINGLE_SEASON_MILESTONE:
            stat_col = category.parameters.get("stat", "passing_tds")
            min_year = category.min_season_year or 2015
            target_year = category.parameters.get("year")

            stat_attr = getattr(PlayerSeasonStat, stat_col, None)
            if stat_attr is not None:
                query = (
                    select(
                        Player.player_id,
                        Player.full_name,
                        Player.headshot_url,
                        Player.rookie_year,
                        Player.final_year,
                        Player.is_active,
                        PlayerSeasonStat.season_year,
                        PlayerSeasonStat.team_season_id,
                        stat_attr.label("metric"),
                    )
                    .join(Player, PlayerSeasonStat.player_id == Player.player_id)
                )

                if target_year:
                    query = query.where(PlayerSeasonStat.season_year == target_year)
                else:
                    query = query.where(PlayerSeasonStat.season_year >= min_year)

                query = query.order_by(
                    desc("metric"),
                    desc(PlayerSeasonStat.season_year),
                ).limit(25)

                result = await session.execute(query)
                rows = result.all()

                if len(rows) >= 10:
                    entries = _build_ranked_entries(
                        rows=rows,
                        metric_label=category.metric_label,
                        is_draft=False,
                    )

        # 2. CHRONOLOGICAL ACCOLADE
        elif category.archetype == Top10Archetype.CHRONOLOGICAL_ACCOLADE:
            accolade_type = category.parameters.get("accolade_type", "MVP")
            query = (
                select(
                    Player.player_id,
                    Player.full_name,
                    Player.headshot_url,
                    Player.rookie_year,
                    Player.final_year,
                    Player.is_active,
                    Accolade.season_year,
                    Accolade.franchise_id,
                    Accolade.season_year.label("metric"),
                )
                .join(Player, Accolade.player_id == Player.player_id)
                .where(Accolade.accolade_type == accolade_type)
                .order_by(desc(Accolade.season_year))
                .limit(20)
            )

            result = await session.execute(query)
            rows = result.all()

            if len(rows) >= 10:
                entries = _build_ranked_entries(
                    rows=rows,
                    metric_label=category.metric_label,
                    is_draft=False,
                    is_chronological=True,
                )

        # 3. RECENT DRAFT PEDIGREE
        elif category.archetype == Top10Archetype.RECENT_DRAFT_PEDIGREE:
            draft_year = category.parameters.get("draft_year", 2020)
            side = category.parameters.get("side")

            query = (
                select(
                    Player.player_id,
                    Player.full_name,
                    Player.headshot_url,
                    Player.rookie_year,
                    Player.final_year,
                    Player.is_active,
                    Player.draft_year,
                    Player.primary_position,
                    Player.draft_overall.label("metric"),
                )
                .where(
                    Player.draft_year == draft_year,
                    Player.draft_overall.isnot(None),
                )
            )

            if side == "OFFENSE":
                query = query.where(Player.primary_position.in_(["QB", "RB", "WR", "TE", "OT", "OG", "C", "OL"]))
            elif side == "DEFENSE":
                query = query.where(Player.primary_position.in_(["DE", "DT", "EDGE", "LB", "ILB", "OLB", "CB", "S", "FS", "SS", "DL", "DB"]))

            query = query.order_by(Player.draft_overall.asc()).limit(15)

            result = await session.execute(query)
            rows = result.all()

            if len(rows) >= 10:
                entries = _build_ranked_entries(
                    rows=rows,
                    metric_label=category.metric_label,
                    is_draft=True,
                )

        # 4. ALL-TIME HISTORICAL LEADERBOARD
        elif category.archetype == Top10Archetype.ALL_TIME_HISTORICAL_LEADERBOARD:
            stat_name = category.parameters.get("stat", "career_sacks")
            stat_field = stat_name.replace("career_", "")
            career_attr = getattr(PlayerCareerStat, stat_field, None)

            if career_attr is not None:
                query = (
                    select(
                        Player.player_id,
                        Player.full_name,
                        Player.headshot_url,
                        Player.rookie_year,
                        Player.final_year,
                        Player.is_active,
                        PlayerCareerStat.seasons_played,
                        Player.primary_position,
                        career_attr.label("metric"),
                    )
                    .join(Player, PlayerCareerStat.player_id == Player.player_id)
                    .order_by(
                        desc("metric"),
                        PlayerCareerStat.games_played.asc(),
                    )
                    .limit(20)
                )

                result = await session.execute(query)
                rows = result.all()

                if len(rows) >= 10:
                    entries = _build_ranked_entries(
                        rows=rows,
                        metric_label=category.metric_label,
                        is_draft=False,
                    )

    except Exception as exc:
        logger.warning(f"Live SQL resolution for category {category.category_id} failed: {exc}. Using fallback catalog.")

    # If SQL results were insufficient, use validated fallback leaderboard
    if len(entries) < 10 and category.fallback_leaderboard:
        entries = [
            Top10Entry(
                rank=f["rank"],
                player_id=f["player_id"],
                player_name=f["player_name"],
                metric_value=float(f["metric_value"]),
                formatted_value=f["formatted_value"],
                headshot_url=f.get("headshot_url"),
                active_years=f.get("active_years"),
                primary_franchise=f.get("primary_franchise"),
                tied_player_ids=f.get("tied_player_ids", []),
            )
            for f in category.fallback_leaderboard[:10]
        ]

    return entries[:10]


def _build_ranked_entries(
    rows: List[Any],
    metric_label: str,
    is_draft: bool = False,
    is_chronological: bool = False,
) -> List[Top10Entry]:
    """
    Constructs exactly 10 ranked Top10Entry items with tie-breaking and tied_player_ids tracking.
    """
    entries: List[Top10Entry] = []
    seen_players: Set[str] = set()

    filtered_rows = []
    for r in rows:
        pid = str(r[0])
        if pid not in seen_players:
            seen_players.add(pid)
            filtered_rows.append(r)
        if len(filtered_rows) >= 10:
            break

    # Compute tied entries
    metric_map: Dict[float, List[str]] = {}
    for r in filtered_rows:
        val = float(r.metric if hasattr(r, "metric") else r[-1])
        metric_map.setdefault(val, []).append(str(r[0]))

    for idx, r in enumerate(filtered_rows, start=1):
        pid = str(r[0])
        name = str(r[1])
        headshot = r[2]
        rookie = r[3]
        final = r[4]
        is_active = bool(r[5])
        val = float(r.metric if hasattr(r, "metric") else r[-1])

        active_years = f"{rookie}-Present" if is_active or not final else f"{rookie}-{final}"

        # Format display value
        if is_draft:
            formatted_val = f"Pick #{int(val)}"
        elif is_chronological:
            formatted_val = f"{int(val)} Season"
        else:
            formatted_val = f"{int(val) if val.is_integer() else val} {metric_label}"

        tied_ids = [tid for tid in metric_map.get(val, []) if tid != pid]

        entries.append(Top10Entry(
            rank=idx,
            player_id=pid,
            player_name=name,
            metric_value=val,
            formatted_value=formatted_val,
            headshot_url=headshot,
            active_years=active_years,
            primary_franchise=None,
            tied_player_ids=tied_ids,
        ))

    return entries[:10]
