"""
Expanded Criteria Registry and Taxonomy Engine.
Models an extensible, strongly typed catalog of criteria categorized across 6 distinct archetypes.
Supports dynamic coverage validation, active/inactive toggling, and fast parameter extraction.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class CriterionType(str, Enum):
    FRANCHISE = "FRANCHISE"
    DIVISION = "DIVISION"
    CONFERENCE = "CONFERENCE"
    JOURNEYMAN = "JOURNEYMAN"
    STAT_SEASON = "STAT_SEASON"
    STAT_CAREER = "STAT_CAREER"
    STAT_POSITIONAL = "STAT_POSITIONAL"
    ACCOLADE = "ACCOLADE"
    ACCOLADE_COUNT = "ACCOLADE_COUNT"
    DRAFT_ROUND = "DRAFT_ROUND"
    DRAFT_OVERALL = "DRAFT_OVERALL"
    COLLEGE = "COLLEGE"


class CriterionArchetype(str, Enum):
    ERA_FRANCHISE = "ERA_FRANCHISE"
    HARDWARE_ACCOLADE = "HARDWARE_ACCOLADE"
    COLLEGE_DRAFT = "COLLEGE_DRAFT"
    CAREER_TOTAL = "CAREER_TOTAL"
    SEASON_MILESTONE = "SEASON_MILESTONE"
    POSITIONAL_QUIRK = "POSITIONAL_QUIRK"


@dataclass
class CriterionDefinition:
    criterion_id: str
    type: CriterionType
    archetype: CriterionArchetype
    display_title: str
    subtitle: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    min_sample_size: int = 50
    tags: Set[str] = field(default_factory=set)
    incompatible_criteria: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "type": self.type.value if isinstance(self.type, Enum) else self.type,
            "archetype": self.archetype.value if isinstance(self.archetype, Enum) else self.archetype,
            "display_title": self.display_title,
            "subtitle": self.subtitle,
            "parameters": self.parameters,
        }


# =====================================================================
# Canonical NFL Division & Conference Mappings
# =====================================================================
DIVISION_MAP: Dict[str, List[str]] = {
    "DIV_AFC_EAST": ["BUF", "MIA", "NWE", "NYJ"],
    "DIV_AFC_NORTH": ["BAL", "CIN", "CLE", "PIT"],
    "DIV_AFC_SOUTH": ["HOU", "IND", "JAX", "TEN"],
    "DIV_AFC_WEST": ["DEN", "KC", "LAC", "LVR"],
    "DIV_NFC_EAST": ["DAL", "NYG", "PHI", "WAS"],
    "DIV_NFC_NORTH": ["CHI", "DET", "GNB", "MIN"],
    "DIV_NFC_SOUTH": ["ATL", "CAR", "NOR", "TAM"],
    "DIV_NFC_WEST": ["ARI", "LAR", "SEA", "SFO"],
}

CONFERENCE_MAP: Dict[str, List[str]] = {
    "CONF_AFC": [
        "BUF", "MIA", "NWE", "NYJ",
        "BAL", "CIN", "CLE", "PIT",
        "HOU", "IND", "JAX", "TEN",
        "DEN", "KC", "LAC", "LVR",
    ],
    "CONF_NFC": [
        "DAL", "NYG", "PHI", "WAS",
        "CHI", "DET", "GNB", "MIN",
        "ATL", "CAR", "NOR", "TAM",
        "ARI", "LAR", "SEA", "SFO",
    ],
}

FRANCHISE_METADATA: Dict[str, Dict[str, str]] = {
    "ARI": {"name": "Arizona Cardinals", "div": "DIV_NFC_WEST", "conf": "CONF_NFC"},
    "ATL": {"name": "Atlanta Falcons", "div": "DIV_NFC_SOUTH", "conf": "CONF_NFC"},
    "BAL": {"name": "Baltimore Ravens", "div": "DIV_AFC_NORTH", "conf": "CONF_AFC"},
    "BUF": {"name": "Buffalo Bills", "div": "DIV_AFC_EAST", "conf": "CONF_AFC"},
    "CAR": {"name": "Carolina Panthers", "div": "DIV_NFC_SOUTH", "conf": "CONF_NFC"},
    "CHI": {"name": "Chicago Bears", "div": "DIV_NFC_NORTH", "conf": "CONF_NFC"},
    "CIN": {"name": "Cincinnati Bengals", "div": "DIV_AFC_NORTH", "conf": "CONF_AFC"},
    "CLE": {"name": "Cleveland Browns", "div": "DIV_AFC_NORTH", "conf": "CONF_AFC"},
    "DAL": {"name": "Dallas Cowboys", "div": "DIV_NFC_EAST", "conf": "CONF_NFC"},
    "DEN": {"name": "Denver Broncos", "div": "DIV_AFC_WEST", "conf": "CONF_AFC"},
    "DET": {"name": "Detroit Lions", "div": "DIV_NFC_NORTH", "conf": "CONF_NFC"},
    "GNB": {"name": "Green Bay Packers", "div": "DIV_NFC_NORTH", "conf": "CONF_NFC"},
    "HOU": {"name": "Houston Texans", "div": "DIV_AFC_SOUTH", "conf": "CONF_AFC"},
    "IND": {"name": "Indianapolis Colts", "div": "DIV_AFC_SOUTH", "conf": "CONF_AFC"},
    "JAX": {"name": "Jacksonville Jaguars", "div": "DIV_AFC_SOUTH", "conf": "CONF_AFC"},
    "KC":  {"name": "Kansas City Chiefs", "div": "DIV_AFC_WEST", "conf": "CONF_AFC"},
    "LAC": {"name": "Los Angeles Chargers", "div": "DIV_AFC_WEST", "conf": "CONF_AFC"},
    "LAR": {"name": "Los Angeles Rams", "div": "DIV_NFC_WEST", "conf": "CONF_NFC"},
    "LVR": {"name": "Las Vegas Raiders", "div": "DIV_AFC_WEST", "conf": "CONF_AFC"},
    "MIA": {"name": "Miami Dolphins", "div": "DIV_AFC_EAST", "conf": "CONF_AFC"},
    "MIN": {"name": "Minnesota Vikings", "div": "DIV_NFC_NORTH", "conf": "CONF_NFC"},
    "NWE": {"name": "New England Patriots", "div": "DIV_AFC_EAST", "conf": "CONF_AFC"},
    "NOR": {"name": "New Orleans Saints", "div": "DIV_NFC_SOUTH", "conf": "CONF_NFC"},
    "NYG": {"name": "New York Giants", "div": "DIV_NFC_EAST", "conf": "CONF_NFC"},
    "NYJ": {"name": "New York Jets", "div": "DIV_AFC_EAST", "conf": "CONF_AFC"},
    "PHI": {"name": "Philadelphia Eagles", "div": "DIV_NFC_EAST", "conf": "CONF_NFC"},
    "PIT": {"name": "Pittsburgh Steelers", "div": "DIV_AFC_NORTH", "conf": "CONF_AFC"},
    "SEA": {"name": "Seattle Seahawks", "div": "DIV_NFC_WEST", "conf": "CONF_NFC"},
    "SFO": {"name": "San Francisco 49ers", "div": "DIV_NFC_WEST", "conf": "CONF_NFC"},
    "TAM": {"name": "Tampa Bay Buccaneers", "div": "DIV_NFC_SOUTH", "conf": "CONF_NFC"},
    "TEN": {"name": "Tennessee Titans", "div": "DIV_AFC_SOUTH", "conf": "CONF_AFC"},
    "WAS": {"name": "Washington Commanders", "div": "DIV_NFC_EAST", "conf": "CONF_NFC"},
}


class CriteriaRegistry:
    """
    Central criteria registry cataloging all valid puzzle criteria.
    Includes built-in taxonomy and provides filtering by archetype and coverage.
    """

    def __init__(self):
        self._criteria: Dict[str, CriterionDefinition] = {}
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        """Initializes the baseline taxonomy with 60+ production criteria."""

        # -------------------------------------------------------------
        # 1. ARCHETYPE: ERA_FRANCHISE (32 Franchises + Divisions + Journeymen)
        # -------------------------------------------------------------
        for f_id, meta in FRANCHISE_METADATA.items():
            self.register(
                CriterionDefinition(
                    criterion_id=f"FRAN_{f_id}",
                    type=CriterionType.FRANCHISE,
                    archetype=CriterionArchetype.ERA_FRANCHISE,
                    display_title=meta["name"],
                    subtitle="Played >= 1 Game",
                    parameters={"franchise_id": f_id},
                    tags={"franchise", f_id.lower(), meta["div"].lower(), meta["conf"].lower()},
                )
            )

        division_titles = {
            "DIV_AFC_EAST": "AFC East",
            "DIV_AFC_NORTH": "AFC North",
            "DIV_AFC_SOUTH": "AFC South",
            "DIV_AFC_WEST": "AFC West",
            "DIV_NFC_EAST": "NFC East",
            "DIV_NFC_NORTH": "NFC North",
            "DIV_NFC_SOUTH": "NFC South",
            "DIV_NFC_WEST": "NFC West",
        }
        for div_id, div_name in division_titles.items():
            franchises = DIVISION_MAP[div_id]
            self.register(
                CriterionDefinition(
                    criterion_id=div_id,
                    type=CriterionType.DIVISION,
                    archetype=CriterionArchetype.ERA_FRANCHISE,
                    display_title=f"Played in {div_name}",
                    subtitle="Any Division Franchise",
                    parameters={"division_id": div_id, "franchise_ids": franchises},
                    tags={"division", div_id.lower()},
                )
            )

        self.register(
            CriterionDefinition(
                criterion_id="CONF_AFC",
                type=CriterionType.CONFERENCE,
                archetype=CriterionArchetype.ERA_FRANCHISE,
                display_title="Played in AFC",
                subtitle="Any AFC Franchise",
                parameters={"conference": "AFC", "franchise_ids": CONFERENCE_MAP["CONF_AFC"]},
                tags={"conference", "afc"},
            )
        )
        self.register(
            CriterionDefinition(
                criterion_id="CONF_NFC",
                type=CriterionType.CONFERENCE,
                archetype=CriterionArchetype.ERA_FRANCHISE,
                display_title="Played in NFC",
                subtitle="Any NFC Franchise",
                parameters={"conference": "NFC", "franchise_ids": CONFERENCE_MAP["CONF_NFC"]},
                tags={"conference", "nfc"},
            )
        )
        self.register(
            CriterionDefinition(
                criterion_id="JOURNEYMAN_3_PLUS",
                type=CriterionType.JOURNEYMAN,
                archetype=CriterionArchetype.ERA_FRANCHISE,
                display_title="3+ NFL Franchises",
                subtitle="Career Journeyman",
                parameters={"min_franchises": 3},
                tags={"journeyman"},
            )
        )
        self.register(
            CriterionDefinition(
                criterion_id="JOURNEYMAN_4_PLUS",
                type=CriterionType.JOURNEYMAN,
                archetype=CriterionArchetype.ERA_FRANCHISE,
                display_title="4+ NFL Franchises",
                subtitle="Career Journeyman",
                parameters={"min_franchises": 4},
                tags={"journeyman"},
            )
        )

        # -------------------------------------------------------------
        # 2. ARCHETYPE: HARDWARE_ACCOLADE
        # -------------------------------------------------------------
        accolades = [
            ("ACCOLADE_HOF", "HALL_OF_FAME", "Pro Football Hall of Fame", "Inducted as Player", {}),
            ("ACCOLADE_MVP", "MVP", "NFL Most Valuable Player", "AP MVP Winner", {}),
            ("ACCOLADE_SB_MVP", "SUPER_BOWL_MVP", "Super Bowl MVP", "Pete Rozelle Trophy", {}),
            ("ACCOLADE_SB_CHAMP", "SUPER_BOWL_CHAMPION", "Super Bowl Champion", "Roster Winner", {}),
            ("ACCOLADE_OROY", "OROY", "Offensive Rookie of the Year", "AP OROY Winner", {}),
            ("ACCOLADE_DROY", "DROY", "Defensive Rookie of the Year", "AP DROY Winner", {}),
            ("ACCOLADE_CPOY", "CPOY", "Comeback Player of the Year", "AP Award", {}),
            ("ACCOLADE_WPMOTY", "WPMOTY", "Walter Payton Man of the Year", "NFL Honor", {}),
            ("ACCOLADE_ALL_PRO", "FIRST_TEAM_ALL_PRO", "AP First-Team All-Pro", "1+ Career Selection", {}),
            ("ACCOLADE_PRO_BOWL", "PRO_BOWL", "Pro Bowl Selection", "1+ Career Selection", {}),
        ]
        for c_id, acc_type, title, sub, extra in accolades:
            self.register(
                CriterionDefinition(
                    criterion_id=c_id,
                    type=CriterionType.ACCOLADE,
                    archetype=CriterionArchetype.HARDWARE_ACCOLADE,
                    display_title=title,
                    subtitle=sub,
                    parameters={"accolade_type": acc_type, **extra},
                    tags={"accolade", acc_type.lower()},
                )
            )

        # Multi-time accolades
        self.register(
            CriterionDefinition(
                criterion_id="ACCOLADE_ALL_PRO_3_PLUS",
                type=CriterionType.ACCOLADE_COUNT,
                archetype=CriterionArchetype.HARDWARE_ACCOLADE,
                display_title="3+ AP 1st-Team All-Pros",
                subtitle="Career Total",
                parameters={"accolade_type": "FIRST_TEAM_ALL_PRO", "min_count": 3},
                tags={"accolade", "all_pro_multi"},
            )
        )
        self.register(
            CriterionDefinition(
                criterion_id="ACCOLADE_PRO_BOWL_3_PLUS",
                type=CriterionType.ACCOLADE_COUNT,
                archetype=CriterionArchetype.HARDWARE_ACCOLADE,
                display_title="3+ Pro Bowl Selections",
                subtitle="Career Total",
                parameters={"accolade_type": "PRO_BOWL", "min_count": 3},
                tags={"accolade", "pro_bowl_multi"},
            )
        )
        self.register(
            CriterionDefinition(
                criterion_id="ACCOLADE_PRO_BOWL_5_PLUS",
                type=CriterionType.ACCOLADE_COUNT,
                archetype=CriterionArchetype.HARDWARE_ACCOLADE,
                display_title="5+ Pro Bowl Selections",
                subtitle="Career Total",
                parameters={"accolade_type": "PRO_BOWL", "min_count": 5},
                tags={"accolade", "pro_bowl_multi"},
            )
        )

        # -------------------------------------------------------------
        # 3. ARCHETYPE: COLLEGE_DRAFT
        # -------------------------------------------------------------
        colleges = [
            ("COLLEGE_ALABAMA", "Alabama", "Crimson Tide"),
            ("COLLEGE_OHIO_STATE", "Ohio State", "Buckeyes"),
            ("COLLEGE_LSU", "LSU", "Tigers"),
            ("COLLEGE_USC", "USC", "Trojans"),
            ("COLLEGE_GEORGIA", "Georgia", "Bulldogs"),
            ("COLLEGE_MICHIGAN", "Michigan", "Wolverines"),
            ("COLLEGE_NOTRE_DAME", "Notre Dame", "Fighting Irish"),
            ("COLLEGE_OKLAHOMA", "Oklahoma", "Sooners"),
            ("COLLEGE_CLEMSON", "Clemson", "Tigers"),
            ("COLLEGE_TEXAS", "Texas", "Longhorns"),
            ("COLLEGE_PENN_STATE", "Penn State", "Nittany Lions"),
            ("COLLEGE_FLORIDA", "Florida", "Gators"),
            ("COLLEGE_MIAMI", "Miami (FL)", "Hurricanes"),
            ("COLLEGE_WISCONSIN", "Wisconsin", "Badgers"),
            ("COLLEGE_IOWA", "Iowa", "Hawkeyes"),
            ("COLLEGE_OREGON", "Oregon", "Ducks"),
            ("COLLEGE_TENNESSEE", "Tennessee", "Volunteers"),
        ]
        for c_id, col_name, sub in colleges:
            self.register(
                CriterionDefinition(
                    criterion_id=c_id,
                    type=CriterionType.COLLEGE,
                    archetype=CriterionArchetype.COLLEGE_DRAFT,
                    display_title=f"{col_name}",
                    subtitle=f"{sub} (College)",
                    parameters={"college": col_name},
                    tags={"college", col_name.lower()},
                )
            )

        draft_quirks = [
            ("DRAFT_RD1", CriterionType.DRAFT_ROUND, "1st Round Draft Pick", "NFL Common Draft", {"round": 1}),
            ("DRAFT_TOP5", CriterionType.DRAFT_OVERALL, "Top 5 Overall Draft Pick", "Picks 1 through 5", {"max_overall": 5}),
            ("DRAFT_DAY2", CriterionType.DRAFT_ROUND, "Drafted Round 2 or 3", "Day 2 Draft Pick", {"rounds": [2, 3]}),
            ("DRAFT_RD4_PLUS", CriterionType.DRAFT_ROUND, "Drafted 4th Round or Later", "Rounds 4-7 / Day 3", {"min_round": 4}),
            ("DRAFT_UNDRAFTED", CriterionType.DRAFT_ROUND, "Undrafted Free Agent", "Never Drafted", {"is_undrafted": True}),
        ]
        for c_id, c_type, title, sub, params in draft_quirks:
            self.register(
                CriterionDefinition(
                    criterion_id=c_id,
                    type=c_type,
                    archetype=CriterionArchetype.COLLEGE_DRAFT,
                    display_title=title,
                    subtitle=sub,
                    parameters=params,
                    tags={"draft", c_id.lower()},
                )
            )

        # -------------------------------------------------------------
        # 4. ARCHETYPE: CAREER_TOTAL
        # -------------------------------------------------------------
        career_stats = [
            ("CAREER_RUSH_10K", "rushing_yards", 10000, "10,000+ Career Rush Yds", "Career Regular Season"),
            ("CAREER_RUSH_5K", "rushing_yards", 5000, "5,000+ Career Rush Yds", "Career Regular Season"),
            ("CAREER_PASS_40K", "passing_yards", 40000, "40,000+ Career Pass Yds", "Career Regular Season"),
            ("CAREER_PASS_300TD", "passing_tds", 300, "300+ Career Pass TDs", "Career Regular Season"),
            ("CAREER_PASS_100TD", "passing_tds", 100, "100+ Career Pass TDs", "Career Regular Season"),
            ("CAREER_REC_10K", "receiving_yards", 10000, "10,000+ Career Rec Yds", "Career Regular Season"),
            ("CAREER_REC_5K", "receiving_yards", 5000, "5,000+ Career Rec Yds", "Career Regular Season"),
            ("CAREER_REC_500", "receptions", 500, "500+ Career Receptions", "Career Regular Season"),
            ("CAREER_REC_100TD", "receiving_tds", 100, "100+ Career Rec TDs", "Career Regular Season"),
            ("CAREER_RUSH_50TD", "rushing_tds", 50, "50+ Career Rush TDs", "Career Regular Season"),
            ("CAREER_SACK_100", "sacks", 100.0, "100.0+ Career Sacks", "Post-1982 Career"),
            ("CAREER_SACK_50", "sacks", 50.0, "50.0+ Career Sacks", "Post-1982 Career"),
            ("CAREER_INT_30", "defensive_interceptions", 30, "30+ Career Def INTs", "Career Regular Season"),
        ]
        for c_id, stat_name, thresh, title, sub in career_stats:
            self.register(
                CriterionDefinition(
                    criterion_id=c_id,
                    type=CriterionType.STAT_CAREER,
                    archetype=CriterionArchetype.CAREER_TOTAL,
                    display_title=title,
                    subtitle=sub,
                    parameters={"stat_name": stat_name, "threshold": thresh},
                    tags={"career_stat", stat_name},
                )
            )

        # -------------------------------------------------------------
        # 5. ARCHETYPE: SEASON_MILESTONE
        # -------------------------------------------------------------
        season_stats = [
            ("STAT_PASS_5000", "passing_yards", 5000, "5,000+ Pass Yds Season", "Single Regular Season"),
            ("STAT_PASS_4000", "passing_yards", 4000, "4,000+ Pass Yds Season", "Single Regular Season"),
            ("STAT_PASS_3000", "passing_yards", 3000, "3,000+ Pass Yds Season", "Single Regular Season"),
            ("STAT_PASS_TD_30", "passing_tds", 30, "30+ Pass TDs Season", "Single Regular Season"),
            ("STAT_RUSH_1000", "rushing_yards", 1000, "1,000+ Rush Yds Season", "Single Regular Season"),
            ("STAT_RUSH_1500", "rushing_yards", 1500, "1,500+ Rush Yds Season", "Single Regular Season"),
            ("STAT_RUSH_TD_10", "rushing_tds", 10, "10+ Rush TDs Season", "Single Regular Season"),
            ("STAT_RUSH_TD_15", "rushing_tds", 15, "15+ Rush TDs Season", "Single Regular Season"),
            ("STAT_REC_1000", "receiving_yards", 1000, "1,000+ Rec Yds Season", "Single Regular Season"),
            ("STAT_REC_1500", "receiving_yards", 1500, "1,500+ Rec Yds Season", "Single Regular Season"),
            ("STAT_REC_TD_10", "receiving_tds", 10, "10+ Rec TDs Season", "Single Regular Season"),
            ("STAT_REC_100", "receptions", 100, "100+ Receptions Season", "Single Regular Season"),
            ("STAT_SACK_10", "sacks", 10.0, "10.0+ Sacks Season", "Single Regular Season"),
            ("STAT_SACK_15", "sacks", 15.0, "15.0+ Sacks Season", "Single Regular Season"),
            ("STAT_INT_6", "defensive_interceptions", 6, "6+ Def INTs Season", "Single Regular Season"),
        ]
        for c_id, stat_name, thresh, title, sub in season_stats:
            self.register(
                CriterionDefinition(
                    criterion_id=c_id,
                    type=CriterionType.STAT_SEASON,
                    archetype=CriterionArchetype.SEASON_MILESTONE,
                    display_title=title,
                    subtitle=sub,
                    parameters={"stat_name": stat_name, "threshold": thresh},
                    tags={"season_stat", stat_name},
                )
            )

        # -------------------------------------------------------------
        # 6. ARCHETYPE: POSITIONAL_QUIRK
        # -------------------------------------------------------------
        pos_quirks = [
            ("POS_QB_RUSH_500", "QB", "rushing_yards", 500, "500+ Rush Yds Season (QB)", "Dual-Threat Quarterback"),
            ("POS_TE_REC_1000", "TE", "receiving_yards", 1000, "1,000+ Rec Yds Season (TE)", "Tight End Milestone"),
            ("POS_TE_REC_TD_10", "TE", "receiving_tds", 10, "10+ Rec TDs Season (TE)", "Tight End Milestone"),
            ("POS_RB_REC_50", "RB", "receptions", 50, "50+ Receptions Season (RB)", "Pass-Catching Back"),
            ("POS_RB_REC_500", "RB", "receiving_yards", 500, "500+ Rec Yds Season (RB)", "Pass-Catching Back"),
        ]
        for c_id, pos, stat_name, thresh, title, sub in pos_quirks:
            self.register(
                CriterionDefinition(
                    criterion_id=c_id,
                    type=CriterionType.STAT_POSITIONAL,
                    archetype=CriterionArchetype.POSITIONAL_QUIRK,
                    display_title=title,
                    subtitle=sub,
                    parameters={"position": pos, "stat_name": stat_name, "threshold": thresh},
                    tags={"positional", pos.lower(), stat_name},
                )
            )

    def register(self, criterion: CriterionDefinition) -> None:
        """Registers a criterion definition."""
        self._criteria[criterion.criterion_id] = criterion

    def get_criterion(self, criterion_id: str) -> Optional[CriterionDefinition]:
        return self._criteria.get(criterion_id)

    def get_all_criteria(self, active_only: bool = True) -> List[CriterionDefinition]:
        if active_only:
            return [c for c in self._criteria.values() if c.is_active]
        return list(self._criteria.values())

    def get_criteria_by_archetype(
        self, archetype: CriterionArchetype, active_only: bool = True
    ) -> List[CriterionDefinition]:
        return [
            c for c in self._criteria.values()
            if c.archetype == archetype and (not active_only or c.is_active)
        ]

    def set_active_status(self, criterion_id: str, is_active: bool) -> bool:
        crit = self.get_criterion(criterion_id)
        if crit:
            crit.is_active = is_active
            return True
        return False

    def disable_criteria_by_ids(self, criterion_ids: Set[str]) -> int:
        count = 0
        for cid in criterion_ids:
            if self.set_active_status(cid, False):
                count += 1
        return count


# Global Singleton Registry Instance
registry = CriteriaRegistry()
