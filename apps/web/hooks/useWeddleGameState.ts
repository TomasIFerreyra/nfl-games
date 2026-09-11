"use client";

import { useState, useEffect, useCallback } from "react";
import { WeddleUserState, WeddleGuessComparison, WeddleGuessResponse, WeddlePlayer } from "@nfl-games/contracts";

const getStorageKey = (puzzleId: string) => `nfl_weddle_state_${puzzleId}`;

export function useWeddleGameState(puzzleId: string) {
  const [isHydrated, setIsHydrated] = useState(false);
  const [state, setState] = useState<WeddleUserState>(() => ({
    puzzle_id: puzzleId,
    attempts: [],
    is_completed: false,
    is_won: false,
    is_resigned: false,
    revealed_target: null,
    guesses_remaining: 6,
  }));

  // Hydrate from localStorage on client mount or puzzleId change
  useEffect(() => {
    if (!puzzleId || typeof window === "undefined") return;

    try {
      const raw = localStorage.getItem(getStorageKey(puzzleId));
      if (raw) {
        const parsed: WeddleUserState = JSON.parse(raw);
        if (parsed.puzzle_id === puzzleId) {
          setState(parsed);
          setIsHydrated(true);
          return;
        }
      }
    } catch (err) {
      console.warn("Failed to load Weddle state from localStorage:", err);
    }

    // Default state if not in localStorage
    setState({
      puzzle_id: puzzleId,
      attempts: [],
      is_completed: false,
      is_won: false,
      is_resigned: false,
      revealed_target: null,
      guesses_remaining: 6,
    });
    setIsHydrated(true);
  }, [puzzleId]);

  // Persist state updates to localStorage
  const saveState = useCallback((nextState: WeddleUserState) => {
    setState(nextState);
    if (typeof window !== "undefined" && nextState.puzzle_id) {
      try {
        localStorage.setItem(getStorageKey(nextState.puzzle_id), JSON.stringify(nextState));
      } catch (err) {
        console.warn("Failed to persist Weddle state to localStorage:", err);
      }
    }
  }, []);

  const recordGuess = useCallback(
    (response: WeddleGuessResponse) => {
      setState((prev) => {
        const attempts = [...prev.attempts, response.comparison];
        const isWon = response.is_correct;
        const isCompleted = response.is_game_over || isWon || response.guesses_remaining === 0;

        const nextState: WeddleUserState = {
          ...prev,
          attempts,
          is_won: isWon,
          is_completed: isCompleted,
          revealed_target: response.revealed_target ?? prev.revealed_target,
          guesses_remaining: response.guesses_remaining,
        };

        if (typeof window !== "undefined" && prev.puzzle_id) {
          try {
            localStorage.setItem(getStorageKey(prev.puzzle_id), JSON.stringify(nextState));
          } catch (err) {
            console.warn("Failed to persist Weddle state:", err);
          }
        }

        return nextState;
      });
    },
    []
  );

  const recordResign = useCallback(
    (target: WeddlePlayer) => {
      setState((prev) => {
        const nextState: WeddleUserState = {
          ...prev,
          is_resigned: true,
          is_completed: true,
          revealed_target: target,
          guesses_remaining: 0,
        };

        if (typeof window !== "undefined" && prev.puzzle_id) {
          try {
            localStorage.setItem(getStorageKey(prev.puzzle_id), JSON.stringify(nextState));
          } catch (err) {
            console.warn("Failed to persist Weddle state:", err);
          }
        }

        return nextState;
      });
    },
    []
  );

  const restart = useCallback(() => {
    const freshState: WeddleUserState = {
      puzzle_id: puzzleId,
      attempts: [],
      is_completed: false,
      is_won: false,
      is_resigned: false,
      revealed_target: null,
      guesses_remaining: 6,
    };
    if (typeof window !== "undefined" && puzzleId) {
      try {
        localStorage.removeItem(getStorageKey(puzzleId));
      } catch (err) {
        console.warn("Failed to remove Weddle state:", err);
      }
    }
    setState(freshState);
  }, [puzzleId]);

  return {
    state,
    isHydrated,
    recordGuess,
    recordResign,
    restart,
  };
}
