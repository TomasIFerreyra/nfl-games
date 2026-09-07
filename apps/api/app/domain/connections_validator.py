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
        items = puzzle_data.get("items", [])

        # Build mapping for text -> id and id -> id
        id_map: Dict[str, str] = {}
        for item in items:
            if isinstance(item, dict):
                iid = item.get("item_id")
                dtext = item.get("display_text")
                if iid:
                    id_map[iid] = iid
                    if dtext:
                        id_map[dtext] = iid
                        id_map[dtext.lower().strip()] = iid

        # Normalize selected_item_ids to canonical item_ids
        canonical_selected = set()
        for s in selected_item_ids:
            if s in id_map:
                canonical_selected.add(id_map[s])
            elif s.lower().strip() in id_map:
                canonical_selected.add(id_map[s.lower().strip()])
            else:
                canonical_selected.add(s)

        # Check for exact match
        for group in groups:
            target_set = set(group.get("item_ids", []))
            if canonical_selected == target_set or selected_set == target_set:
                return True, group, False, 4

        # Check for "one away" (exactly 3 items match any group)
        max_overlap = 0
        for group in groups:
            target_set = set(group.get("item_ids", []))
            overlap = max(
                len(canonical_selected.intersection(target_set)),
                len(selected_set.intersection(target_set)),
            )
            if overlap > max_overlap:
                max_overlap = overlap

        is_one_away = (max_overlap == 3)
        return False, None, is_one_away, max_overlap
