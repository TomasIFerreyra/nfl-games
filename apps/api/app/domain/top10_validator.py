"""
NFL Top 10 Leaderboard Guess Validation Engine.
Per Section 1.1.4 and Section 3.2.5 of SPECIFICATION.md:
- O(1) matching against precomputed ranked slots.
- Tie-breaker awareness: matches direct player_id, tied_player_ids, and normalized name variants.
- Repeated guess deduplication to prevent penalizing identical redundant inputs.
"""

from typing import Any, Dict, List, Optional, Set, Tuple


def _normalize_name(name: str) -> str:
    """Normalizes player name string for resilient fuzzy matching."""
    if not name:
        return ""
    return name.lower().replace(".", "").replace("-", " ").replace("'", "").strip()


class Top10Validator:
    """
    Evaluates player guesses against the daily Top 10 Leaderboard.
    """

    @classmethod
    def evaluate_guess(
        cls,
        puzzle_data: Dict[str, Any],
        player_id: str,
        previous_guesses: Optional[List[str]] = None,
        guessed_player_name: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], bool, int, Optional[str]]:
        """
        Evaluates a submitted player guess against the Top 10 leaderboard.

        Returns tuple:
            (is_hit, matched_entry_dict, is_repeated, strikes_added, reason)
        """
        leaderboard: List[Dict[str, Any]] = puzzle_data.get("leaderboard", [])
        clean_input_id = str(player_id).strip()
        norm_input_id = _normalize_name(clean_input_id)
        norm_input_name = _normalize_name(guessed_player_name or clean_input_id)

        # 1. Check for duplicate / repeated guess in session
        if previous_guesses:
            prev_set = {str(g).strip().lower() for g in previous_guesses}
            if clean_input_id.lower() in prev_set or norm_input_id in prev_set:
                return False, None, True, 0, "Player has already been submitted in this session."

        # 2. Evaluate against leaderboard entries
        for entry in leaderboard:
            entry_pid = str(entry.get("player_id", "")).strip()
            entry_name = str(entry.get("player_name", "")).strip()
            norm_entry_name = _normalize_name(entry_name)
            tied_pids: List[str] = entry.get("tied_player_ids", []) or []

            # Direct player_id match
            if entry_pid and (entry_pid == clean_input_id or entry_pid.lower() == clean_input_id.lower()):
                return True, entry, False, 0, None

            # Tied player IDs match
            if clean_input_id in tied_pids or clean_input_id.lower() in [t.lower() for t in tied_pids]:
                return True, entry, False, 0, None

            # Name matching (handling punctuation differences like "T.J. Watt" vs "TJ Watt")
            if norm_entry_name and (norm_entry_name == norm_input_name or norm_entry_name == norm_input_id):
                return True, entry, False, 0, None

        # Miss / Strike
        return False, None, False, 1, "Player is not in the Top 10 for this category."
