from typing import Any, Dict, List, Optional, Tuple


class Top10Validator:
    """
    Evaluates player guesses against the daily Top 10 Leaderboard.
    """

    @classmethod
    def evaluate_guess(
        cls,
        puzzle_data: Dict[str, Any],
        player_id: str,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Searches the leaderboard for the guessed player.
        Returns: (is_hit, leaderboard_entry_dict)
        """
        leaderboard: List[Dict[str, Any]] = puzzle_data.get("leaderboard", [])

        for entry in leaderboard:
            if entry.get("player_id") == player_id:
                return True, entry

        return False, None
