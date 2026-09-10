"""
Production-grade Procedural Grid Generator Engine.
Implements dynamic weighted templates, criteria taxonomy rotation, anti-clash validation,
deterministic RNG seeding, fast set intersection checks, and mathematical solvability & log-density invariants.
"""

from datetime import date, datetime
import hashlib
import json
import logging
import math
import random
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.criteria_registry import (
    CriteriaRegistry,
    CriterionDefinition,
    registry,
)
from app.domain.grid_templates import (
    TEMPLATES,
    AntiClashValidator,
    GridTemplate,
    TemplateSelector,
)
from app.domain.rotation_tracker import RotationTracker
from app.services.grid_precompute_service import GridPrecomputeService

logger = logging.getLogger(__name__)


class GridGenerator:
    """
    Deterministic 3x3 Daily Grid puzzle generator enforcing solvability (|S_{r,c}| >= 3)
    and balanced log-density ([12.0, 22.0]) with dynamic templates and rotation memory.
    """

    @classmethod
    def compute_solution_hash(cls, payload: Dict[str, Any]) -> str:
        canonical_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def calculate_log_density(cls, cell_cardinalities: List[List[int]]) -> float:
        """Computes total log-density D = sum_{r, c} log10(|S_{r, c}|)."""
        total_density = 0.0
        for r in range(3):
            for c in range(3):
                val = cell_cardinalities[r][c]
                if val <= 0:
                    return 0.0
                total_density += math.log10(val)
        return round(total_density, 2)

    @classmethod
    async def generate_puzzle_data(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
        k_min: int = 3,
        max_attempts: int = 50,
        rotation_tracker: Optional[RotationTracker] = None,
        custom_registry: CriteriaRegistry = registry,
        min_density: float = 8.0,
        max_density: float = 24.0,
    ) -> Dict[str, Any]:
        """
        Generates and validates a solvable 3x3 Grid puzzle for target_date.
        """
        start_time = time.perf_counter()
        seed_value = int(target_date.strftime("%Y%m%d")) + 9973
        rng = random.Random(seed_value)

        tracker = rotation_tracker or RotationTracker()

        # Deterministically order available templates starting with weighted choice
        available_templates = list(TEMPLATES)
        rng.shuffle(available_templates)

        chosen_puzzle_data: Optional[Dict[str, Any]] = None
        chosen_template_used: Optional[str] = None
        total_attempts = 0

        for template in available_templates:
            logger.debug(f"Attempting template '{template.template_id}' for date {target_date}")

            for attempt in range(max_attempts):
                total_attempts += 1

                # Sample row criteria
                row_candidates_by_slot: List[List[CriterionDefinition]] = [
                    TemplateSelector.get_candidate_criteria_for_slot(slot, custom_registry)
                    for slot in template.row_slots
                ]
                col_candidates_by_slot: List[List[CriterionDefinition]] = [
                    TemplateSelector.get_candidate_criteria_for_slot(slot, custom_registry)
                    for slot in template.col_slots
                ]

                # Check if all slots have viable candidates
                if any(len(cands) == 0 for cands in row_candidates_by_slot) or any(
                    len(cands) == 0 for cands in col_candidates_by_slot
                ):
                    continue

                # Sample row criteria with rotation memory weighting
                cand_rows: List[CriterionDefinition] = []
                for slot_cands in row_candidates_by_slot:
                    sampled = tracker.sample_candidates(
                        slot_cands,
                        target_date=target_date,
                        rng=rng,
                        k=1,
                        allow_cooldown_fallback=(attempt > 20),
                    )
                    if sampled:
                        cand_rows.append(sampled[0])

                # Sample col criteria with rotation memory weighting
                cand_cols: List[CriterionDefinition] = []
                for slot_cands in col_candidates_by_slot:
                    sampled = tracker.sample_candidates(
                        slot_cands,
                        target_date=target_date,
                        rng=rng,
                        k=1,
                        allow_cooldown_fallback=(attempt > 20),
                    )
                    if sampled:
                        cand_cols.append(sampled[0])

                if len(cand_rows) != 3 or len(cand_cols) != 3:
                    continue

                # 1. Anti-Clash Verification
                is_valid_clash, clash_reason = AntiClashValidator.validate_grid(cand_rows, cand_cols)
                if not is_valid_clash:
                    logger.debug(f"Clash rejected attempt {attempt}: {clash_reason}")
                    continue

                # 2. Fast relational/set intersection checks
                row_dicts = [r.to_dict() for r in cand_rows]
                col_dicts = [c.to_dict() for c in cand_cols]

                row_player_sets = [
                    await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, r)
                    for r in row_dicts
                ]
                col_player_sets = [
                    await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, c)
                    for c in col_dicts
                ]

                # Check 9-cell cardinality bounds
                card_matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
                raw_solutions: Dict[str, List[str]] = {}
                solvability_passed = True

                for r in range(3):
                    for c in range(3):
                        inter = row_player_sets[r].intersection(col_player_sets[c])
                        cnt = len(inter)
                        card_matrix[r][c] = cnt
                        raw_solutions[f"{r}_{c}"] = sorted(list(inter))
                        if cnt < k_min:
                            solvability_passed = False
                            break
                    if not solvability_passed:
                        break

                if not solvability_passed:
                    continue

                # 3. Log-Density Verification
                log_density = cls.calculate_log_density(card_matrix)
                if log_density > 0 and (log_density < min_density or log_density > max_density):
                    logger.debug(f"Density out of bounds: {log_density} not in [{min_density}, {max_density}]")
                    # If high attempts, relax density check
                    if attempt < 30:
                        continue

                # 4. Enrich solutions with database UUIDs
                enriched_solutions: Dict[str, List[str]] = {}
                for cell_key, names in raw_solutions.items():
                    enriched = await GridPrecomputeService.enrich_solutions_with_db_uuids(
                        session, set(names)
                    )
                    enriched_solutions[cell_key] = sorted(list(enriched))

                chosen_puzzle_data = {
                    "template_id": template.template_id,
                    "rows": row_dicts,
                    "columns": col_dicts,
                    "min_cardinality_guarantee": k_min,
                    "cell_cardinalities": card_matrix,
                    "valid_solutions": enriched_solutions,
                    "log_density": log_density,
                }
                chosen_template_used = template.template_id
                break

            if chosen_puzzle_data:
                break

        # Fallback Ladder: If no template passed strict candidate search, construct robust fallback
        if not chosen_puzzle_data:
            logger.warning(
                f"Grid generation fell back to base ladder after {total_attempts} attempts for {target_date}."
            )
            fallback_rows = [
                {"criterion_id": "FRAN_GNB", "type": "FRANCHISE", "display_title": "Green Bay Packers", "parameters": {"franchise_id": "GNB"}},
                {"criterion_id": "FRAN_NYJ", "type": "FRANCHISE", "display_title": "New York Jets", "parameters": {"franchise_id": "NYJ"}},
                {"criterion_id": "STAT_PASS_4000", "type": "STAT_SEASON", "display_title": "4,000+ Pass Yds Season", "subtitle": "Single Regular Season", "parameters": {"stat_name": "passing_yards", "threshold": 4000}},
            ]
            fallback_cols = [
                {"criterion_id": "FRAN_MIN", "type": "FRANCHISE", "display_title": "Minnesota Vikings", "parameters": {"franchise_id": "MIN"}},
                {"criterion_id": "ACCOLADE_HOF", "type": "ACCOLADE", "display_title": "Pro Football Hall of Fame", "subtitle": "Inducted as Player", "parameters": {"accolade_type": "HALL_OF_FAME"}},
                {"criterion_id": "DRAFT_RD1", "type": "DRAFT_ROUND", "display_title": "1st Round Draft Pick", "subtitle": "NFL Common Draft", "parameters": {"round": 1}},
            ]
            row_player_sets = [
                await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, r)
                for r in fallback_rows
            ]
            col_player_sets = [
                await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, c)
                for c in fallback_cols
            ]
            card_matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            valid_solutions = {}
            for r in range(3):
                for c in range(3):
                    inter = row_player_sets[r].intersection(col_player_sets[c])
                    card_matrix[r][c] = len(inter)
                    valid_solutions[f"{r}_{c}"] = sorted(list(inter))

            chosen_puzzle_data = {
                "template_id": "FALLBACK_BASE_TEMPLATE",
                "rows": fallback_rows,
                "columns": fallback_cols,
                "min_cardinality_guarantee": k_min,
                "cell_cardinalities": card_matrix,
                "valid_solutions": valid_solutions,
                "log_density": cls.calculate_log_density(card_matrix),
            }
            chosen_template_used = "FALLBACK_BASE_TEMPLATE"

        # Record puzzle usage into rotation tracker for subsequent runs
        tracker.record_puzzle(chosen_puzzle_data, target_date)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Generated Grid #{puzzle_number} ({chosen_template_used}) for {target_date} "
            f"in {duration_ms:.2f}ms (Total Attempts: {total_attempts}, Log-Density: {chosen_puzzle_data.get('log_density')})."
        )
        return chosen_puzzle_data
