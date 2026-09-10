"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Top10Entry, Top10UserState } from "@nfl-games/contracts";
import { GameStateManager } from "@/lib/storage/gameState";

const TOP10_STORAGE_KEY_PREFIX = "nfl_top10_state_";

export function getTop10StorageKey(puzzleId: string): string {
  return `${TOP10_STORAGE_KEY_PREFIX}${puzzleId}`;
}

export function getInitialTop10State(puzzleId: string): Top10UserState {
  return {
    puzzle_id: puzzleId,
    revealed_slots: {},
    strikes: 0,
    strikes_remaining: 3,
    submitted_player_ids: [],
    missed_guesses: [],
    is_completed: false,
    is_resigned: false,
  };
}

export function loadTop10UserState(puzzleId: string): Top10UserState {
  if (typeof window === "undefined" || !puzzleId) {
    return getInitialTop10State(puzzleId);
  }

  try {
    const key = getTop10StorageKey(puzzleId);
    const raw = localStorage.getItem(key);

    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.puzzle_id === puzzleId) {
        return {
          puzzle_id: puzzleId,
          revealed_slots: parsed.revealed_slots && typeof parsed.revealed_slots === "object" ? parsed.revealed_slots : {},
          strikes: typeof parsed.strikes === "number" ? parsed.strikes : (3 - (parsed.strikes_remaining ?? 3)),
          strikes_remaining: typeof parsed.strikes_remaining === "number" ? parsed.strikes_remaining : 3,
          submitted_player_ids: Array.isArray(parsed.submitted_player_ids) ? parsed.submitted_player_ids : [],
          missed_guesses: Array.isArray(parsed.missed_guesses) ? parsed.missed_guesses : [],
          is_completed: Boolean(parsed.is_completed),
          is_resigned: Boolean(parsed.is_resigned),
        };
      }
    }

    // Check fallback in global state if same puzzleId and revealed_slots exists
    const globalState = GameStateManager.loadState();
    if (globalState.games.top10.puzzle_id === puzzleId) {
      const g = globalState.games.top10;
      const initialFromGlobal: Top10UserState = {
        puzzle_id: puzzleId,
        revealed_slots: g.revealed_slots && typeof g.revealed_slots === "object" ? g.revealed_slots : {},
        strikes: typeof g.strikes === "number" ? g.strikes : (3 - (g.strikes_remaining ?? 3)),
        strikes_remaining: typeof g.strikes_remaining === "number" ? g.strikes_remaining : 3,
        submitted_player_ids: Array.isArray(g.submitted_player_ids) ? g.submitted_player_ids : [],
        missed_guesses: Array.isArray(g.missed_guesses) ? g.missed_guesses : [],
        is_completed: Boolean(g.is_completed),
        is_resigned: Boolean(g.is_resigned),
      };
      saveTop10UserState(initialFromGlobal);
      return initialFromGlobal;
    }
  } catch (err) {
    console.warn(`[useTop10GameState] Failed to load state for puzzle ${puzzleId}:`, err);
  }

  const fresh = getInitialTop10State(puzzleId);
  saveTop10UserState(fresh);
  return fresh;
}

export function saveTop10UserState(state: Top10UserState): void {
  if (typeof window === "undefined" || !state.puzzle_id) return;

  try {
    const key = getTop10StorageKey(state.puzzle_id);
    localStorage.setItem(key, JSON.stringify(state));

    // Synchronize with global GameStateManager for streaks & dashboard
    const globalState = GameStateManager.loadState();
    globalState.games.top10.puzzle_id = state.puzzle_id;
    globalState.games.top10.strikes = state.strikes;
    globalState.games.top10.strikes_remaining = state.strikes_remaining;
    globalState.games.top10.is_completed = state.is_completed;
    globalState.games.top10.is_resigned = state.is_resigned;
    globalState.games.top10.revealed_slots = state.revealed_slots;
    globalState.games.top10.revealed_ranks = Object.keys(state.revealed_slots).map(Number);
    globalState.games.top10.missed_guesses = state.missed_guesses;
    globalState.games.top10.submitted_player_ids = state.submitted_player_ids;
    GameStateManager.saveState(globalState);
  } catch (err) {
    console.error(`[useTop10GameState] Failed to save state for puzzle ${state.puzzle_id}:`, err);
  }
}

export function useTop10GameState(puzzleId: string) {
  const [state, setState] = useState<Top10UserState>(() => getInitialTop10State(puzzleId));
  const [isHydrated, setIsHydrated] = useState(false);
  const activePuzzleRef = useRef(puzzleId);

  // Sync ref with current puzzleId
  useEffect(() => {
    activePuzzleRef.current = puzzleId;
  }, [puzzleId]);

  // Hydrate or synchronize when puzzleId changes
  useEffect(() => {
    if (!puzzleId) return;
    const loaded = loadTop10UserState(puzzleId);
    setState(loaded);
    setIsHydrated(true);
  }, [puzzleId]);

  const recordHit = useCallback((entry: Top10Entry, playerId: string) => {
    setState((prev) => {
      // Guard against stale state from another puzzle
      if (prev.puzzle_id !== activePuzzleRef.current) return prev;

      const nextRevealed = {
        ...prev.revealed_slots,
        [entry.rank]: entry,
      };

      const nextSubmitted = prev.submitted_player_ids.includes(playerId)
        ? prev.submitted_player_ids
        : [...prev.submitted_player_ids, playerId];

      const isWin = Object.keys(nextRevealed).length === 10;
      const isCompleted = isWin || prev.strikes_remaining <= 0 || Boolean(prev.is_resigned);

      const nextState: Top10UserState = {
        ...prev,
        revealed_slots: nextRevealed,
        submitted_player_ids: nextSubmitted,
        is_completed: isCompleted,
      };

      saveTop10UserState(nextState);

      if (isWin) {
        GameStateManager.updateStreak("top10", true);
      }

      return nextState;
    });
  }, []);

  const recordMiss = useCallback((playerName: string, playerId: string) => {
    setState((prev) => {
      // Guard against stale state from another puzzle
      if (prev.puzzle_id !== activePuzzleRef.current) return prev;

      const nextStrikes = Math.min(3, prev.strikes + 1);
      const nextStrikesRemaining = Math.max(0, prev.strikes_remaining - 1);
      const nextMisses = prev.missed_guesses.includes(playerName)
        ? prev.missed_guesses
        : [...prev.missed_guesses, playerName];
      const nextSubmitted = prev.submitted_player_ids.includes(playerId)
        ? prev.submitted_player_ids
        : [...prev.submitted_player_ids, playerId];

      const isLoss = nextStrikesRemaining <= 0;
      const isCompleted = isLoss || Object.keys(prev.revealed_slots).length === 10 || Boolean(prev.is_resigned);

      const nextState: Top10UserState = {
        ...prev,
        strikes: nextStrikes,
        strikes_remaining: nextStrikesRemaining,
        missed_guesses: nextMisses,
        submitted_player_ids: nextSubmitted,
        is_completed: isCompleted,
      };

      saveTop10UserState(nextState);

      if (isLoss) {
        GameStateManager.updateStreak("top10", false);
      }

      return nextState;
    });
  }, []);

  const recordResign = useCallback(() => {
    setState((prev) => {
      if (prev.puzzle_id !== activePuzzleRef.current) return prev;

      const nextState: Top10UserState = {
        ...prev,
        strikes: 3,
        strikes_remaining: 0,
        is_completed: true,
        is_resigned: true,
      };

      saveTop10UserState(nextState);
      GameStateManager.updateStreak("top10", false);

      return nextState;
    });
  }, []);

  const restart = useCallback(() => {
    const fresh = getInitialTop10State(puzzleId);
    setState(fresh);
    saveTop10UserState(fresh);
  }, [puzzleId]);

  return {
    state,
    isHydrated,
    recordHit,
    recordMiss,
    recordResign,
    restart,
  };
}
