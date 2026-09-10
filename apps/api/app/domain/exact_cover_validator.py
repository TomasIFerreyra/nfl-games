"""
Knuth's Algorithm X Exact Cover Solver and Uniqueness Verifier for NFL Connections 4x4.
Per Section 4.3 of SPECIFICATION.md:
- Given a candidate 16-player board and four labeled target groups:
  * Identifies all valid 4-player categories that could apply to any 4 players within the selected 16.
  * Checks that there is STRICTLY ONE unique 4-way disjoint partition of the 16 items.
  * Rejects any candidate board where distractors allow an alternate valid 4x4 solution partition.
- Implements both:
  1. Dancing Links (DLX) matrix representation with quadruply linked circular lists.
  2. Bitset-accelerated Algorithm X with Minimum Remaining Values (MRV) column selection for sub-millisecond execution.
"""

from dataclasses import dataclass, field
import time
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


@dataclass(eq=False)
class DLXNode:
    """Cell node in Dancing Links matrix."""
    left: "DLXNode" = field(init=False)
    right: "DLXNode" = field(init=False)
    up: "DLXNode" = field(init=False)
    down: "DLXNode" = field(init=False)
    column: "DLXColumn" = field(init=False)
    row_id: int = -1

    def __post_init__(self) -> None:
        self.left = self
        self.right = self
        self.up = self
        self.down = self


@dataclass(eq=False)
class DLXColumn(DLXNode):
    """Column header in Dancing Links matrix."""
    name: str = ""
    size: int = 0

    def __post_init__(self) -> None:
        super().__post_init__()
        self.column = self


class DancingLinks:
    """
    Classic Dancing Links (DLX) implementation of Knuth's Algorithm X.
    """

    def __init__(self, column_names: List[str]) -> None:
        self.header = DLXColumn(name="root")
        self.columns: Dict[str, DLXColumn] = {}

        prev = self.header
        for col_name in column_names:
            col = DLXColumn(name=col_name)
            col.left = prev
            col.right = self.header
            prev.right = col
            self.header.left = col
            self.columns[col_name] = col
            prev = col

    def add_row(self, row_id: int, column_indices: List[str]) -> None:
        """Adds a candidate row covering the specified column names."""
        first_node: Optional[DLXNode] = None
        for col_name in column_indices:
            col = self.columns[col_name]
            node = DLXNode(row_id=row_id)
            node.column = col

            # Link vertically into column list
            node.down = col
            node.up = col.up
            col.up.down = node
            col.up = node
            col.size += 1

            # Link horizontally into row list
            if first_node is None:
                first_node = node
            else:
                node.left = first_node.left
                node.right = first_node
                first_node.left.right = node
                first_node.left = node

    def cover(self, col: DLXColumn) -> None:
        """Removes column and all rows containing a 1 in this column."""
        col.right.left = col.left
        col.left.right = col.right

        row = col.down
        while row is not col:
            node = row.right
            while node is not row:
                node.down.up = node.up
                node.up.down = node.down
                node.column.size -= 1
                node = node.right
            row = row.down

    def uncover(self, col: DLXColumn) -> None:
        """Restores column and all associated rows."""
        row = col.up
        while row is not col:
            node = row.left
            while node is not row:
                node.column.size += 1
                node.down.up = node
                node.up.down = node
                node = node.left
            row = row.up

        col.right.left = col
        col.left.right = col

    def solve(self, max_solutions: int = 10) -> List[List[int]]:
        """Finds exact covers using Knuth's Algorithm X with MRV heuristic."""
        solutions: List[List[int]] = []
        current_solution: List[int] = []

        def search() -> None:
            if len(solutions) >= max_solutions:
                return

            if self.header.right is self.header:
                solutions.append(list(current_solution))
                return

            # Choose column with minimum remaining rows (MRV heuristic)
            chosen_col = self.header.right
            min_size = chosen_col.size

            curr = self.header.right
            while curr is not self.header:
                if curr.size < min_size:
                    min_size = curr.size
                    chosen_col = curr
                curr = curr.right

            if min_size == 0:
                # Dead end
                return

            self.cover(chosen_col)

            row = chosen_col.down
            while row is not chosen_col:
                current_solution.append(row.row_id)
                node = row.right
                while node is not row:
                    self.cover(node.column)
                    node = node.right

                search()

                # Backtrack
                node = row.left
                while node is not row:
                    self.uncover(node.column)
                    node = node.left
                current_solution.pop()

                row = row.down

            self.uncover(chosen_col)

        search()
        return solutions


@dataclass
class ExactCoverValidationResult:
    """Detailed diagnostic results from Knuth's Algorithm X exact cover validation."""
    is_unique: bool
    solution_count: int
    solutions: List[List[FrozenSet[str]]]
    all_valid_candidate_groups: List[Tuple[str, FrozenSet[str]]]
    solve_time_ms: float
    rejection_reason: Optional[str] = None


class ExactCoverValidator:
    """
    Production Knuth's Algorithm X Exact Cover Solver for Connections 4x4 boards.
    
    Given a board of 16 player items and an active category taxonomy:
    1. Discovers every valid 4-player subset of the 16 players that satisfies any category.
    2. Runs bitset-accelerated exact cover search (and DLX) to find all disjoint 4-way partitions.
    3. Confirms that the target partition is the STRICTLY UNIQUE solution.
    """

    @classmethod
    def solve_exact_cover_bitset(
        cls,
        candidate_masks: List[int],
        universe_size: int = 16,
        max_solutions: int = 10,
    ) -> List[List[int]]:
        """
        Ultra high-speed bitset Algorithm X with MRV heuristic for universe of size 16.
        Each mask represents a 4-player group as a 16-bit integer.
        Returns indices of the candidate_masks that form exact covers.
        """
        full_mask = (1 << universe_size) - 1
        solutions: List[List[int]] = []
        current: List[int] = []

        # Precompute inverted index: player_bit -> list of mask indices covering that bit
        bit_to_mask_indices: List[List[int]] = [[] for _ in range(universe_size)]
        for idx, m in enumerate(candidate_masks):
            for bit in range(universe_size):
                if (m >> bit) & 1:
                    bit_to_mask_indices[bit].append(idx)

        def backtrack(covered_mask: int) -> None:
            if len(solutions) >= max_solutions:
                return

            if covered_mask == full_mask:
                if len(current) == 4:
                    solutions.append(list(current))
                return

            # MRV heuristic: find uncovered bit with fewest available candidate masks
            uncovered_bits = [b for b in range(universe_size) if not ((covered_mask >> b) & 1)]
            if not uncovered_bits:
                return

            best_bit = -1
            best_count = float("inf")
            for b in uncovered_bits:
                # Count available masks for this bit that don't collide with covered_mask
                count = sum(1 for m_idx in bit_to_mask_indices[b] if (candidate_masks[m_idx] & covered_mask) == 0)
                if count < best_count:
                    best_count = count
                    best_bit = b
                if count == 0:
                    # Dead end: this uncovered item cannot be covered by any remaining mask
                    return

            # Branch on candidate masks covering best_bit
            for m_idx in bit_to_mask_indices[best_bit]:
                m = candidate_masks[m_idx]
                if (m & covered_mask) == 0:
                    current.append(m_idx)
                    backtrack(covered_mask | m)
                    current.pop()

        backtrack(0)
        return solutions

    @classmethod
    def validate_puzzle_uniqueness(
        cls,
        item_ids: List[str],
        category_player_pools: Dict[str, Set[str]],
        target_groups: Optional[List[Set[str]]] = None,
    ) -> ExactCoverValidationResult:
        """
        Validates whether a 16-player candidate board has strictly one unique 4-way disjoint partition.

        Args:
            item_ids: Exactly 16 unique item IDs representing the puzzle board.
            category_player_pools: Mapping of category_id -> set of all player_ids satisfying that category.
            target_groups: Optional list of 4 sets representing the intended target answer groups.

        Returns:
            ExactCoverValidationResult with uniqueness verdict and diagnostics.
        """
        start_time = time.perf_counter()

        if len(item_ids) != 16:
            return ExactCoverValidationResult(
                is_unique=False,
                solution_count=0,
                solutions=[],
                all_valid_candidate_groups=[],
                solve_time_ms=(time.perf_counter() - start_time) * 1000,
                rejection_reason=f"Board must have exactly 16 items, got {len(item_ids)}.",
            )

        if len(set(item_ids)) != 16:
            return ExactCoverValidationResult(
                is_unique=False,
                solution_count=0,
                solutions=[],
                all_valid_candidate_groups=[],
                solve_time_ms=(time.perf_counter() - start_time) * 1000,
                rejection_reason="Duplicate items found on candidate board.",
            )

        item_to_bit = {item: i for i, item in enumerate(item_ids)}
        board_set = set(item_ids)

        # 1. Discover all candidate 4-element groups on this 16-item board
        from itertools import combinations

        unique_4groups: Dict[FrozenSet[str], List[str]] = {}
        for cat_id, pool in category_player_pools.items():
            matching_on_board = board_set.intersection(pool)
            if len(matching_on_board) >= 4:
                for comb in combinations(matching_on_board, 4):
                    f_comb = frozenset(comb)
                    if f_comb not in unique_4groups:
                        unique_4groups[f_comb] = []
                    unique_4groups[f_comb].append(cat_id)

        candidate_list: List[FrozenSet[str]] = list(unique_4groups.keys())
        candidate_masks: List[int] = []
        for grp in candidate_list:
            mask = 0
            for item in grp:
                mask |= (1 << item_to_bit[item])
            candidate_masks.append(mask)

        # 2. Run bitset Algorithm X solver
        raw_solutions = cls.solve_exact_cover_bitset(
            candidate_masks=candidate_masks,
            universe_size=16,
            max_solutions=10,
        )

        # Convert solutions to set of 4-groups (deduplicating group ordering within partition)
        distinct_partitions: List[List[FrozenSet[str]]] = []
        seen_partition_keys: Set[FrozenSet[FrozenSet[str]]] = set()

        for sol_indices in raw_solutions:
            partition = [candidate_list[idx] for idx in sol_indices]
            part_key = frozenset(partition)
            if part_key not in seen_partition_keys:
                seen_partition_keys.add(part_key)
                distinct_partitions.append(partition)

        solve_time = (time.perf_counter() - start_time) * 1000
        solution_count = len(distinct_partitions)

        all_candidate_tuples = [
            (cats[0], grp) for grp, cats in unique_4groups.items()
        ]

        if solution_count == 0:
            return ExactCoverValidationResult(
                is_unique=False,
                solution_count=0,
                solutions=[],
                all_valid_candidate_groups=all_candidate_tuples,
                solve_time_ms=solve_time,
                rejection_reason="No valid 4x4 exact cover partition found for candidate board.",
            )

        if solution_count > 1:
            return ExactCoverValidationResult(
                is_unique=False,
                solution_count=solution_count,
                solutions=distinct_partitions,
                all_valid_candidate_groups=all_candidate_tuples,
                solve_time_ms=solve_time,
                rejection_reason=(
                    f"Ambiguous board: {solution_count} distinct 4x4 exact cover partitions exist "
                    f"due to overlapping distractor categories."
                ),
            )

        # If target_groups provided, verify that the single solution matches target groups
        if target_groups is not None:
            target_frozensets = {frozenset(g) for g in target_groups}
            sol_frozensets = set(distinct_partitions[0])
            if target_frozensets != sol_frozensets:
                return ExactCoverValidationResult(
                    is_unique=False,
                    solution_count=solution_count,
                    solutions=distinct_partitions,
                    all_valid_candidate_groups=all_candidate_tuples,
                    solve_time_ms=solve_time,
                    rejection_reason="Single solution partition does not match intended target groups.",
                )

        return ExactCoverValidationResult(
            is_unique=True,
            solution_count=1,
            solutions=distinct_partitions,
            all_valid_candidate_groups=all_candidate_tuples,
            solve_time_ms=solve_time,
            rejection_reason=None,
        )
