"""
Recency & Fatigue Tracker (Rotation Memory).
Prevents repetitive rolls of the same category archetypes and franchises
by tracking recent daily puzzle history over the previous 7 to 14 days and applying decay penalties.
"""

from datetime import date, timedelta
import logging
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from app.domain.criteria_registry import CriterionDefinition

logger = logging.getLogger(__name__)


class RotationTracker:
    """
    Tracks criterion usage history across recent daily puzzles
    and applies cooldown and probability decay factors.
    """

    def __init__(self, cooldown_days: int = 3, fatigue_window_days: int = 14):
        self.cooldown_days = cooldown_days
        self.fatigue_window_days = fatigue_window_days
        # Maps criterion_id -> list of recent usage dates
        self._history: Dict[str, List[date]] = {}

    def clear(self) -> None:
        self._history.clear()

    def record_usage(self, criterion_id: str, puzzle_date: date) -> None:
        if criterion_id not in self._history:
            self._history[criterion_id] = []
        if puzzle_date not in self._history[criterion_id]:
            self._history[criterion_id].append(puzzle_date)
            self._history[criterion_id].sort(reverse=True)

    def record_puzzle(self, puzzle_data: Dict[str, Any], puzzle_date: date) -> None:
        """Extracts all row and column criterion IDs and records them."""
        for r in puzzle_data.get("rows", []):
            cid = r.get("criterion_id")
            if cid:
                self.record_usage(cid, puzzle_date)
        for c in puzzle_data.get("columns", []):
            cid = c.get("criterion_id")
            if cid:
                self.record_usage(cid, puzzle_date)

    def load_from_puzzles(self, puzzles: List[Any]) -> None:
        """Loads historical puzzle data from SQLAlchemy DailyPuzzle records."""
        for p in puzzles:
            p_date = getattr(p, "target_date", None)
            p_data = getattr(p, "puzzle_data", {})
            if isinstance(p_data, str):
                import json
                try:
                    p_data = json.loads(p_data)
                except Exception:
                    p_data = {}
            if p_date and p_data:
                self.record_puzzle(p_data, p_date)

    def get_fatigue_multiplier(self, criterion_id: str, target_date: date) -> float:
        """
        Calculates selection probability decay factor:
          - Used within <= cooldown_days (1-3 days): 0.0 (strictly excluded)
          - Used within 4-7 days: 0.25 (strong penalty)
          - Used within 8-14 days: 0.60 (moderate penalty)
          - Not used in 14+ days: 1.00 (neutral/full weight)
        """
        dates = self._history.get(criterion_id, [])
        if not dates:
            return 1.0

        # Find most recent date prior to target_date
        past_dates = [d for d in dates if d < target_date]
        if not past_dates:
            return 1.0

        most_recent = past_dates[0]
        days_diff = (target_date - most_recent).days

        if days_diff <= self.cooldown_days:
            return 0.0
        elif days_diff <= 7:
            return 0.25
        elif days_diff <= self.fatigue_window_days:
            return 0.60
        return 1.0

    def sample_candidates(
        self,
        candidates: List[CriterionDefinition],
        target_date: date,
        rng: random.Random,
        k: int = 1,
        allow_cooldown_fallback: bool = False,
    ) -> List[CriterionDefinition]:
        """
        Samples candidates using weighted probabilities derived from fatigue multipliers.
        """
        if not candidates:
            return []

        weighted_pool: List[Tuple[CriterionDefinition, float]] = []
        for c in candidates:
            w = self.get_fatigue_multiplier(c.criterion_id, target_date)
            if w > 0.0 or allow_cooldown_fallback:
                effective_weight = max(w, 0.05 if allow_cooldown_fallback else 0.0)
                weighted_pool.append((c, effective_weight))

        if not weighted_pool:
            # Fallback if all candidates are on cooldown
            weighted_pool = [(c, 1.0) for c in candidates]

        # Shuffle deterministically
        pool_items = [item[0] for item in weighted_pool]
        weights = [item[1] for item in weighted_pool]

        # Weighted sampling without replacement
        selected: List[CriterionDefinition] = []
        remaining_items = list(pool_items)
        remaining_weights = list(weights)

        for _ in range(min(k, len(remaining_items))):
            total_w = sum(remaining_weights)
            if total_w <= 0:
                idx = rng.randint(0, len(remaining_items) - 1)
            else:
                r_val = rng.uniform(0, total_w)
                cum = 0.0
                idx = 0
                for i, w in enumerate(remaining_weights):
                    cum += w
                    if r_val <= cum:
                        idx = i
                        break
            selected.append(remaining_items.pop(idx))
            remaining_weights.pop(idx)

        return selected
