"""
Weighted Dynamic Grid Templates and Anti-Clash Engine.
Defines dynamic templates for 3x3 Daily Grid generation with strict anti-clash verification rules.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from app.domain.criteria_registry import (
    CONFERENCE_MAP,
    DIVISION_MAP,
    FRANCHISE_METADATA,
    CriteriaRegistry,
    CriterionArchetype,
    CriterionDefinition,
    CriterionType,
    registry,
)

logger = logging.getLogger(__name__)


@dataclass
class SlotRequirement:
    """Defines constraints for a single row or column slot."""
    archetype: CriterionArchetype
    criterion_type: Optional[CriterionType] = None
    sub_category: Optional[str] = None  # e.g., "franchise_only", "division_only", "draft_only", "college_only"


@dataclass
class GridTemplate:
    template_id: str
    name: str
    description: str
    weight: int  # Weighted probability selection (sum of weights ~ 100)
    row_slots: List[SlotRequirement]
    col_slots: List[SlotRequirement]


# =====================================================================
# Weighted Grid Template Catalog
# =====================================================================
TEMPLATES: List[GridTemplate] = [
    GridTemplate(
        template_id="TEMPLATE_A_FRANCHISE_HEAVY",
        name="Franchise Heavy + Accolade & Stat",
        description="2 Franchises + 1 Division/Journeyman on Rows; 1 Franchise + 1 Accolade + 1 Stat on Columns",
        weight=35,
        row_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, sub_category="division_or_journeyman"),
        ],
        col_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.HARDWARE_ACCOLADE),
            SlotRequirement(archetype=CriterionArchetype.SEASON_MILESTONE),
        ],
    ),
    GridTemplate(
        template_id="TEMPLATE_B_COLLEGE_DRAFT",
        name="College & Draft Quirks Focus",
        description="1 Franchise + 1 College + 1 Career Stat on Rows; 2 Franchises + 1 Draft Status on Columns",
        weight=25,
        row_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.COLLEGE_DRAFT, criterion_type=CriterionType.COLLEGE),
            SlotRequirement(archetype=CriterionArchetype.CAREER_TOTAL),
        ],
        col_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.COLLEGE_DRAFT, sub_category="draft_only"),
        ],
    ),
    GridTemplate(
        template_id="TEMPLATE_C_ACCOLADE_MILESTONE",
        name="Accolade & Hardware Milestone",
        description="2 Franchises + 1 Hardware on Rows; 1 Division/Conference + 1 Season Milestone + 1 College on Columns",
        weight=25,
        row_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.HARDWARE_ACCOLADE),
        ],
        col_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, sub_category="division_or_conf"),
            SlotRequirement(archetype=CriterionArchetype.SEASON_MILESTONE),
            SlotRequirement(archetype=CriterionArchetype.COLLEGE_DRAFT, criterion_type=CriterionType.COLLEGE),
        ],
    ),
    GridTemplate(
        template_id="TEMPLATE_D_JOURNEYMAN_DUAL_THREAT",
        name="Journeyman & Positional Quirks",
        description="1 Franchise + 1 Journeyman/Division + 1 Positional Quirk on Rows; 1 Franchise + 1 Career Stat + 1 Draft/Accolade on Columns",
        weight=15,
        row_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, sub_category="division_or_journeyman"),
            SlotRequirement(archetype=CriterionArchetype.POSITIONAL_QUIRK),
        ],
        col_slots=[
            SlotRequirement(archetype=CriterionArchetype.ERA_FRANCHISE, criterion_type=CriterionType.FRANCHISE),
            SlotRequirement(archetype=CriterionArchetype.CAREER_TOTAL),
            SlotRequirement(archetype=CriterionArchetype.HARDWARE_ACCOLADE),
        ],
    ),
]


class AntiClashValidator:
    """
    Evaluates proposed row/col combinations for domain collisions, logical contradictions,
    and trivial or impossible intersections.
    """

    @classmethod
    def get_franchise_id(cls, criterion: CriterionDefinition) -> Optional[str]:
        if criterion.type == CriterionType.FRANCHISE:
            return criterion.parameters.get("franchise_id") or criterion.criterion_id.replace("FRAN_", "")
        return None

    @classmethod
    def get_division_franchises(cls, criterion: CriterionDefinition) -> Set[str]:
        if criterion.type == CriterionType.DIVISION:
            div_id = criterion.parameters.get("division_id") or criterion.criterion_id
            return set(DIVISION_MAP.get(div_id, []))
        elif criterion.type == CriterionType.CONFERENCE:
            conf_id = criterion.criterion_id
            return set(CONFERENCE_MAP.get(conf_id, []))
        return set()

    @classmethod
    def validate_grid(
        cls,
        rows: List[CriterionDefinition],
        cols: List[CriterionDefinition],
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates full 3x3 Grid against all anti-clash rules.
        Returns: (is_valid, clash_reason)
        """
        if len(rows) != 3 or len(cols) != 3:
            return False, "Grid must have exactly 3 rows and 3 columns."

        all_criteria = rows + cols
        all_ids = [c.criterion_id for c in all_criteria]

        # 1. No duplicate criteria across the grid
        if len(all_ids) != len(set(all_ids)):
            return False, "Duplicate criteria detected across rows/columns."

        # 2. Franchise Uniqueness
        franchises_used: List[str] = []
        for c in all_criteria:
            f_id = cls.get_franchise_id(c)
            if f_id:
                if f_id in franchises_used:
                    return False, f"Duplicate franchise '{f_id}' used multiple times in grid."
                franchises_used.append(f_id)

        # 3. Check intersecting cell clashes
        for r_idx, r_crit in enumerate(rows):
            for c_idx, c_crit in enumerate(cols):
                is_cell_valid, reason = cls.validate_cell_intersection(r_crit, c_crit)
                if not is_cell_valid:
                    return False, f"Clash at cell ({r_idx}, {c_idx}): {reason}"

        # 4. Same-axis redundancy checks
        # Avoid 2 divisions on same row axis or col axis
        row_divs = [c for c in rows if c.type in (CriterionType.DIVISION, CriterionType.CONFERENCE)]
        col_divs = [c for c in cols if c.type in (CriterionType.DIVISION, CriterionType.CONFERENCE)]
        if len(row_divs) > 1 or len(col_divs) > 1:
            return False, "Multiple divisions or conferences on the same axis."

        return True, None

    @classmethod
    def validate_cell_intersection(
        cls,
        r: CriterionDefinition,
        c: CriterionDefinition,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates single intersection cell (row, col) for mutual exclusivity or trivial overlap.
        """
        # Rule A: Franchise intersecting with its own Division / Conference
        # e.g., NE Patriots and AFC East -> redundant/trivial
        r_fid = cls.get_franchise_id(r)
        c_fid = cls.get_franchise_id(c)
        r_div_franchises = cls.get_division_franchises(r)
        c_div_franchises = cls.get_division_franchises(c)

        if r_fid and r_fid in c_div_franchises:
            return False, f"Franchise '{r_fid}' belongs to division/conference '{c.criterion_id}'."
        if c_fid and c_fid in r_div_franchises:
            return False, f"Franchise '{c_fid}' belongs to division/conference '{r.criterion_id}'."

        # Rule B: Mutually Exclusive Draft Criteria
        draft_types = (CriterionType.DRAFT_ROUND, CriterionType.DRAFT_OVERALL)
        if r.type in draft_types and c.type in draft_types:
            r_rd = r.parameters.get("round")
            c_rd = c.parameters.get("round")
            r_min_rd = r.parameters.get("min_round")
            c_min_rd = c.parameters.get("min_round")
            r_undrafted = r.parameters.get("is_undrafted")
            c_undrafted = c.parameters.get("is_undrafted")
            r_top5 = r.parameters.get("max_overall")
            c_top5 = c.parameters.get("max_overall")

            if (r_rd == 1 and (c_min_rd and c_min_rd >= 2)) or (c_rd == 1 and (r_min_rd and r_min_rd >= 2)):
                return False, "Round 1 draft pick is mutually exclusive with Round 4+."
            if (r_rd == 1 and c_undrafted) or (c_rd == 1 and r_undrafted):
                return False, "Round 1 draft pick is mutually exclusive with Undrafted."
            if (r_top5 and c_min_rd) or (c_top5 and r_min_rd):
                return False, "Top 5 draft pick is mutually exclusive with Round 4+."
            if (r_top5 and c_undrafted) or (c_top5 and r_undrafted):
                return False, "Top 5 draft pick is mutually exclusive with Undrafted."

        # Rule C: Conflicting Positional Requirements
        # e.g., QB 500+ Rush Yds with TE 10+ Rec TDs
        pos_types = (CriterionType.STAT_POSITIONAL,)
        if r.type in pos_types and c.type in pos_types:
            r_pos = r.parameters.get("position")
            c_pos = c.parameters.get("position")
            if r_pos and c_pos and r_pos != c_pos:
                return False, f"Conflicting positions '{r_pos}' and '{c_pos}'."

        # Rule D: QB passing stat with pure defensive stat
        r_stat = r.parameters.get("stat_name")
        c_stat = c.parameters.get("stat_name")
        passing_stats = {"passing_yards", "passing_tds"}
        defensive_stats = {"sacks", "defensive_interceptions"}
        if (r_stat in passing_stats and c_stat in defensive_stats) or (c_stat in passing_stats and r_stat in defensive_stats):
            return False, f"Passing stat '{r_stat or c_stat}' cannot be reasonably combined with defensive stat."

        return True, None


class TemplateSelector:
    """
    Selects and resolves criteria pools for dynamic templates.
    """

    @classmethod
    def get_candidate_criteria_for_slot(
        cls,
        slot: SlotRequirement,
        reg: CriteriaRegistry = registry,
    ) -> List[CriterionDefinition]:
        """Resolves active criteria matching the slot requirement."""
        pool = reg.get_all_criteria(active_only=True)

        if slot.sub_category == "franchise_only" or slot.criterion_type == CriterionType.FRANCHISE:
            return [c for c in pool if c.type == CriterionType.FRANCHISE]
        elif slot.sub_category == "division_only":
            return [c for c in pool if c.type == CriterionType.DIVISION]
        elif slot.sub_category == "division_or_journeyman":
            return [c for c in pool if c.type in (CriterionType.DIVISION, CriterionType.JOURNEYMAN)]
        elif slot.sub_category == "division_or_conf":
            return [c for c in pool if c.type in (CriterionType.DIVISION, CriterionType.CONFERENCE)]
        elif slot.sub_category == "draft_only":
            return [c for c in pool if c.type in (CriterionType.DRAFT_ROUND, CriterionType.DRAFT_OVERALL)]
        elif slot.sub_category == "college_only" or slot.criterion_type == CriterionType.COLLEGE:
            return [c for c in pool if c.type == CriterionType.COLLEGE]

        if slot.criterion_type:
            return [c for c in pool if c.type == slot.criterion_type]

        if slot.archetype:
            return [c for c in pool if c.archetype == slot.archetype]

        return pool

    @classmethod
    def select_template_by_seed(cls, rng: random.Random) -> GridTemplate:
        """Deterministically selects a template using weights."""
        total_weight = sum(t.weight for t in TEMPLATES)
        rand_val = rng.uniform(0, total_weight)
        cumulative = 0.0
        for t in TEMPLATES:
            cumulative += t.weight
            if rand_val <= cumulative:
                return t
        return TEMPLATES[0]
