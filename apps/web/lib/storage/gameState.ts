import { ClientLocalStorageState } from "@nfl-games/contracts";

const STORAGE_KEY = "nfl_games_state_v1";

function getTodayUtcString(): string {
  return new Date().toISOString().split("T")[0];
}

export function getDefaultState(): ClientLocalStorageState {
  const today = getTodayUtcString();
  return {
    version: 1,
    client_id: "c-" + Math.random().toString(36).substring(2, 10),
    games: {
      grid: {
        active_date: today,
        puzzle_id: "",
        guesses_remaining: 9,
        is_completed: false,
        is_surrendered: false,
        cells: {
          r0_c0: null,
          r0_c1: null,
          r0_c2: null,
          r1_c0: null,
          r1_c1: null,
          r1_c2: null,
          r2_c0: null,
          r2_c1: null,
          r2_c2: null,
        },
        used_player_ids: [],
        summary_checksum: "",
      },
      connections: {
        active_date: today,
        puzzle_id: "",
        strikes_remaining: 4,
        is_completed: false,
        solved_groups: [],
        guess_history: [],
      },
      top10: {
        active_date: today,
        puzzle_id: "",
        strikes_remaining: 3,
        strikes: 0,
        is_completed: false,
        revealed_ranks: [],
        revealed_slots: {},
        missed_guesses: [],
        submitted_player_ids: [],
      },
    },
    streaks: {
      grid: { current: 0, max: 0, last_played: "" },
      connections: { current: 0, max: 0, last_played: "" },
      top10: { current: 0, max: 0, last_played: "" },
    },
  };
}

export class GameStateManager {
  public static loadState(): ClientLocalStorageState {
    if (typeof window === "undefined") {
      return getDefaultState();
    }

    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        const initial = getDefaultState();
        localStorage.setItem(STORAGE_KEY, JSON.stringify(initial));
        return initial;
      }

      const state: ClientLocalStorageState = JSON.parse(raw);
      const today = getTodayUtcString();

      // Check daily date transitions
      let hasChanges = false;
      if (state.games.grid.active_date !== today) {
        state.games.grid = getDefaultState().games.grid;
        hasChanges = true;
      }
      if (state.games.connections.active_date !== today) {
        state.games.connections = getDefaultState().games.connections;
        hasChanges = true;
      }
      if (state.games.top10.active_date !== today) {
        state.games.top10 = getDefaultState().games.top10;
        hasChanges = true;
      }

      if (hasChanges) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      }

      return state;
    } catch (err) {
      console.warn("Failed to load local storage state, resetting to default:", err);
      const fallback = getDefaultState();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(fallback));
      return fallback;
    }
  }

  public static saveState(state: ClientLocalStorageState): void {
    if (typeof window === "undefined") return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (err) {
      console.error("Failed to save state to localStorage:", err);
    }
  }

  public static updateStreak(
    game: "grid" | "connections" | "top10",
    isWin: boolean,
  ): void {
    const state = this.loadState();
    const today = getTodayUtcString();
    const streak = state.streaks[game];

    if (streak.last_played === today) {
      return; // Already recorded today
    }

    if (isWin) {
      streak.current += 1;
      if (streak.current > streak.max) {
        streak.max = streak.current;
      }
    } else {
      streak.current = 0;
    }

    streak.last_played = today;
    this.saveState(state);
  }
}
