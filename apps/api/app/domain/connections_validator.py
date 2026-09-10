"""
Connections 4x4 Selection Validator and Domain State Evaluator.
Per Section 1.1.3 and Section 3.2.4 of SPECIFICATION.md:
- Evaluates submitted 4-item selections against puzzle groups.
- Detects exact matches and 'one-away' (|G_guess ∩ G_target| == 3) advisory states.
"""

from typing import Any, Dict, List, Optional, Set, Tuple


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
        
        Returns:
            Tuple[is_match, matched_group_dict, is_one_away, max_matched_count]
        """
        selected_set = set(selected_item_ids)
        groups = puzzle_data.get("groups", [])
        items = puzzle_data.get("items", [])

        # Build comprehensive mapping for id -> id and display_text -> id
        id_map: Dict[str, str] = {}
        valid_board_ids: Set[str] = set()

        for item in items:
            if isinstance(item, dict):
                iid = str(item.get("item_id", ""))
                dtext = str(item.get("display_text", ""))
                if iid:
                    valid_board_ids.add(iid)
                    id_map[iid] = iid
                    id_map[iid.lower().strip()] = iid
                    if dtext:
                        id_map[dtext] = iid
                        id_map[dtext.lower().strip()] = iid

        # Normalize selected_item_ids to canonical item_ids
        canonical_selected: Set[str] = set()
        for s in selected_item_ids:
            s_str = str(s).strip()
            if s_str in id_map:
                canonical_selected.add(id_map[s_str])
            elif s_str.lower() in id_map:
                canonical_selected.add(id_map[s_str.lower()])
            else:
                canonical_selected.add(s_str)

        # Check for exact match against any group
        for group in groups:
            target_set = set(group.get("item_ids", []))
            if canonical_selected == target_set or selected_set == target_set:
                return True, group, False, 4

        # Check for "one away" (max overlap of 3 items against any group)
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
