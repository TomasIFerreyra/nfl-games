from typing import Any, Dict, List, Optional, Tuple


class ConnectionsValidator:
    """
    Validates Connections 4x4 selections and detects 'one-away' advisory states.
    """

    @classmethod
    def validate_group(
        cls,
        puzzle_data: Dict[str, Any],
        selected_item_ids: List[str],
    ) -> Tuple[bool, Optional[Dict[str, Any]], bool, int]:
        """
        Evaluates a submitted 4-item guess.
        Returns: (is_match, matched_group_dict, is_one_away, max_matched_count)
        """
        selected_set = set(selected_item_ids)
        groups = puzzle_data.get("groups", [])

        # Check for exact match
        for group in groups:
            target_set = set(group.get("item_ids", []))
            if selected_set == target_set:
                return True, group, False, 4

        # Check for "one away" (exactly 3 items match any group)
        max_overlap = 0
        for group in groups:
            target_set = set(group.get("item_ids", []))
            overlap = len(selected_set.intersection(target_set))
            if overlap > max_overlap:
                max_overlap = overlap

        is_one_away = (max_overlap == 3)
        return False, None, is_one_away, max_overlap
