"use client";

import React, { useState, useEffect, useCallback } from "react";
import { ConnectionsItem, ConnectionsGroup, ConnectionsValidateResponse } from "@nfl-games/contracts";
import { GameStateManager } from "@/lib/storage/gameState";
import { Shuffle, AlertTriangle, CheckCircle2, RotateCcw, Flag } from "lucide-react";

interface ConnectionsBoardProps {
  puzzleId: string;
  items: ConnectionsItem[];
}

const DEMO_CONNECTIONS_GROUPS: ConnectionsGroup[] = [
  {
    group_id: "grp_heisman",
    tier: 1,
    title: "Heisman Trophy Winning Quarterbacks",
    item_ids: ["i1", "i2", "i3", "i4"],
    explanation: "All 4 won the Heisman Trophy in college football.",
  },
  {
    group_id: "grp_pass_5000",
    tier: 2,
    title: "5,000+ Passing Yards in a Single Season",
    item_ids: ["i5", "i6", "i7", "i8"],
    explanation: "All 4 threw for over 5,000 yards in a single NFL season.",
  },
  {
    group_id: "grp_rec_td_100",
    tier: 3,
    title: "120+ Career Receiving Touchdowns",
    item_ids: ["i9", "i10", "i11", "i12"],
    explanation: "All 4 caught at least 120 regular season receiving touchdowns.",
  },
  {
    group_id: "grp_dpoy_mult",
    tier: 4,
    title: "Multiple AP NFL Defensive Player of the Year Awards",
    item_ids: ["i13", "i14", "i15", "i16"],
    explanation: "Multiple or single-season sack record holders / multi-time DPOY winners.",
  },
];

function fallbackValidateGroup(selectedIds: string[], items: ConnectionsItem[]): ConnectionsValidateResponse {
  const idMap = new Map<string, string>();
  for (const item of items) {
    idMap.set(item.item_id, item.item_id);
    idMap.set(item.display_text.toLowerCase().trim(), item.item_id);
  }

  const normalizedSelected = selectedIds.map(
    (id) => idMap.get(id) || idMap.get(id.toLowerCase().trim()) || id
  );
  const selectedSet = new Set(normalizedSelected);

  for (const g of DEMO_CONNECTIONS_GROUPS) {
    const targetSet = new Set(g.item_ids);
    if (g.item_ids.length === 4 && g.item_ids.every((id) => selectedSet.has(id))) {
      return { is_match: true, group: g, is_one_away: false, matched_count: 4 };
    }
  }

  let maxOverlap = 0;
  for (const g of DEMO_CONNECTIONS_GROUPS) {
    const targetSet = new Set(g.item_ids);
    const overlap = g.item_ids.filter((id) => selectedSet.has(id)).length;
    if (overlap > maxOverlap) maxOverlap = overlap;
  }

  return { is_match: false, group: null, is_one_away: maxOverlap === 3, matched_count: maxOverlap };
}

export const ConnectionsBoard: React.FC<ConnectionsBoardProps> = ({ puzzleId, items }) => {
  const [boardItems, setBoardItems] = useState<ConnectionsItem[]>(items);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [strikesRemaining, setStrikesRemaining] = useState(4);
  const [solvedGroups, setSolvedGroups] = useState<ConnectionsGroup[]>([]);
  const [guessHistory, setGuessHistory] = useState<string[]>([]);
  const [isOneAway, setIsOneAway] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResigned, setIsResigned] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [confirmResign, setConfirmResign] = useState(false);

  /** Fetches and reveals all solutions when player loses, resigns, or finishes */
  const fetchAndRevealAll = useCallback(
    async (currentSolved: ConnectionsGroup[]) => {
      let allGroups: ConnectionsGroup[] = [];
      try {
        const res = await fetch(`/api/v1/connections/solution/${puzzleId}`);
        if (res.ok) {
          allGroups = await res.json();
        }
      } catch {
        // Fallback
      }

      if (!allGroups || allGroups.length === 0) {
        allGroups = DEMO_CONNECTIONS_GROUPS;
      }

      const sorted = [...allGroups].sort((a, b) => a.tier - b.tier);
      setSolvedGroups(sorted);
      setSelectedIds([]);

      const state = GameStateManager.loadState();
      state.games.connections.solved_groups = sorted;
      state.games.connections.is_completed = true;
      GameStateManager.saveState(state);
    },
    [puzzleId]
  );

  const handleRestart = () => {
    if (!confirmRestart) {
      setConfirmRestart(true);
      return;
    }
    setBoardItems([...items]);
    setSelectedIds([]);
    setStrikesRemaining(4);
    setSolvedGroups([]);
    setGuessHistory([]);
    setIsOneAway(false);
    setErrorMessage(null);
    setIsResigned(false);
    setConfirmRestart(false);
    setConfirmResign(false);
    const state = GameStateManager.loadState();
    state.games.connections.puzzle_id = puzzleId;
    state.games.connections.strikes_remaining = 4;
    state.games.connections.solved_groups = [];
    state.games.connections.guess_history = [];
    state.games.connections.is_completed = false;
    GameStateManager.saveState(state);
  };

  const handleResign = async () => {
    if (!confirmResign) {
      setConfirmResign(true);
      return;
    }
    setConfirmResign(false);
    setIsResigned(true);
    setStrikesRemaining(0);
    GameStateManager.updateStreak("connections", false);

    const state = GameStateManager.loadState();
    state.games.connections.strikes_remaining = 0;
    state.games.connections.is_completed = true;
    GameStateManager.saveState(state);

    await fetchAndRevealAll(solvedGroups);
  };

  useEffect(() => {
    const state = GameStateManager.loadState();
    if (state.games.connections.puzzle_id === puzzleId) {
      setStrikesRemaining(state.games.connections.strikes_remaining);
      setSolvedGroups(state.games.connections.solved_groups);
      setGuessHistory(state.games.connections.guess_history.map((g) => [...g].sort().join(",")));
      if (
        (state.games.connections.is_completed || state.games.connections.strikes_remaining <= 0) &&
        state.games.connections.solved_groups.length < 4
      ) {
        fetchAndRevealAll(state.games.connections.solved_groups);
      }
    } else {
      state.games.connections.puzzle_id = puzzleId;
      state.games.connections.strikes_remaining = 4;
      state.games.connections.solved_groups = [];
      state.games.connections.guess_history = [];
      state.games.connections.is_completed = false;
      GameStateManager.saveState(state);
      setStrikesRemaining(4);
      setSolvedGroups([]);
      setGuessHistory([]);
    }
  }, [puzzleId, fetchAndRevealAll]);

  // Exclude solved items from remaining board
  const solvedItemIds = new Set(solvedGroups.flatMap((g) => g.item_ids));
  const activeItems = boardItems.filter((i) => !solvedItemIds.has(i.item_id));

  const handleToggleSelect = (id: string) => {
    setErrorMessage(null);
    setIsOneAway(false);
    setConfirmResign(false);
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter((item) => item !== id));
    } else {
      if (selectedIds.length < 4) {
        setSelectedIds([...selectedIds, id]);
      }
    }
  };

  const handleShuffle = () => {
    setConfirmResign(false);
    const shuffled = [...activeItems].sort(() => Math.random() - 0.5);
    setBoardItems([
      ...solvedGroups.flatMap((g) => g.item_ids.map((id) => items.find((i) => i.item_id === id)!)),
      ...shuffled,
    ]);
  };

  const handleSubmit = async () => {
    if (selectedIds.length !== 4 || strikesRemaining <= 0 || isSubmitting) return;

    // Check if already guessed
    const sortedGuessKey = [...selectedIds].sort().join(",");
    if (guessHistory.includes(sortedGuessKey)) {
      setErrorMessage("Already guessed!");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setIsOneAway(false);
    setConfirmResign(false);

    let data: ConnectionsValidateResponse | null = null;

    try {
      const res = await fetch("/api/v1/connections/validate-group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          puzzle_id: puzzleId,
          selected_item_ids: selectedIds,
        }),
      });

      if (res.ok) {
        data = await res.json();
      }
    } catch (err) {
      // Backend offline: fallback
    }

    if (!data) {
      data = fallbackValidateGroup(selectedIds, items);
    }

    if (data.is_match && data.group) {
      const nextSolved = [...solvedGroups, data.group];
      setSolvedGroups(nextSolved);
      setSelectedIds([]);

      const isWin = nextSolved.length === 4;
      if (isWin) {
        GameStateManager.updateStreak("connections", true);
      }

      const state = GameStateManager.loadState();
      state.games.connections.solved_groups = nextSolved;
      state.games.connections.is_completed = isWin;
      GameStateManager.saveState(state);
    } else {
      const nextStrikes = strikesRemaining - 1;
      const nextGuesses = [...guessHistory, sortedGuessKey];
      setStrikesRemaining(nextStrikes);
      setGuessHistory(nextGuesses);
      setIsOneAway(Boolean(data.is_one_away));

      if (!data.is_one_away) {
        setErrorMessage("Incorrect group.");
      }

      if (nextStrikes <= 0) {
        GameStateManager.updateStreak("connections", false);
        await fetchAndRevealAll(solvedGroups);
      }

      const state = GameStateManager.loadState();
      state.games.connections.strikes_remaining = nextStrikes;
      state.games.connections.guess_history = nextGuesses.map((k) => k.split(","));
      state.games.connections.is_completed = nextStrikes <= 0;
      GameStateManager.saveState(state);
    }

    setIsSubmitting(false);
  };

  const getTierBadgeStyle = (tier: number) => {
    switch (tier) {
      case 1:
        return "bg-amber-400 text-black border border-amber-300";
      case 2:
        return "bg-emerald-500 text-white border border-emerald-400";
      case 3:
        return "bg-blue-500 text-white border border-blue-400";
      case 4:
        return "bg-purple-600 text-white border border-purple-400";
      default:
        return "bg-gray-400 text-black";
    }
  };

  const isGameOver = strikesRemaining <= 0 || solvedGroups.length === 4 || isResigned;

  return (
    <div className="w-full max-w-xl mx-auto flex flex-col items-center">
      {/* Subtitle instructions */}
      <p className="text-xs text-gray-400 text-center mb-5">
        Create four groups of four NFL players or entities that share a common connection.
      </p>

      {/* Solved group banners */}
      <div className="w-full space-y-2 mb-3">
        {solvedGroups.map((g) => (
          <div
            key={g.group_id}
            className={`w-full p-3.5 rounded-lg text-center font-semibold animate-in zoom-in-95 duration-200 shadow-md ${getTierBadgeStyle(
              g.tier
            )}`}
          >
            <div className="text-xs uppercase font-black tracking-wider">{g.title}</div>
            <div className="text-[12px] font-medium opacity-95 mt-1">
              {g.item_ids
                .map((id) => items.find((i) => i.item_id === id)?.display_text || id)
                .join(", ")}
            </div>
            {g.explanation && (
              <div className="text-[10px] opacity-80 mt-0.5 italic">
                {g.explanation}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* One-away or Error Alert */}
      {isOneAway && (
        <div className="w-full mb-3 p-2.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs text-center font-medium flex items-center justify-center space-x-1.5 animate-bounce">
          <AlertTriangle className="h-4 w-4" />
          <span>One away! (3 of 4 match a category)</span>
        </div>
      )}
      {errorMessage && !isOneAway && (
        <div className="w-full mb-3 p-2.5 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs text-center font-medium">
          {errorMessage}
        </div>
      )}

      {/* 4x4 Grid of remaining items */}
      {!isGameOver && (
        <div className="grid grid-cols-4 gap-2.5 w-full select-none mb-6">
          {activeItems.map((item) => {
            const isSelected = selectedIds.includes(item.item_id);
            return (
              <button
                key={item.item_id}
                onClick={() => handleToggleSelect(item.item_id)}
                className={`h-20 p-2 rounded-lg border flex flex-col items-center justify-center text-center font-bold text-xs transition-all ${
                  isSelected
                    ? "bg-gray-200 border-white text-black scale-95 shadow-lg"
                    : "bg-surface border-border text-white hover:bg-surface-raised hover:border-gray-500"
                }`}
              >
                <span className="line-clamp-2">{item.display_text}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Strikes status */}
      {!isGameOver && (
        <div className="flex items-center space-x-2 mb-5">
          <span className="text-xs text-gray-400 font-medium">Mistakes remaining:</span>
          <div className="flex space-x-1.5">
            {[1, 2, 3, 4].map((dot) => (
              <div
                key={dot}
                className={`h-2.5 w-2.5 rounded-full transition-colors ${
                  dot <= strikesRemaining ? "bg-rose-500" : "bg-border/60"
                }`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Action Controls */}
      {!isGameOver && (
        <div className="flex items-center justify-center gap-2 flex-wrap">
          <button
            onClick={handleShuffle}
            className="flex items-center space-x-1.5 px-3.5 py-2 rounded-full border border-border bg-surface hover:bg-surface-raised text-xs font-semibold text-gray-300 transition-colors"
          >
            <Shuffle className="h-3.5 w-3.5" />
            <span>Shuffle</span>
          </button>

          <button
            onClick={() => setSelectedIds([])}
            disabled={selectedIds.length === 0}
            className="px-3.5 py-2 rounded-full border border-border bg-surface hover:bg-surface-raised text-xs font-semibold text-gray-300 transition-colors disabled:opacity-40"
          >
            Deselect All
          </button>

          <button
            onClick={handleSubmit}
            disabled={selectedIds.length !== 4 || isSubmitting}
            className="px-5 py-2 rounded-full bg-nfl-blue hover:bg-nfl-blue/90 border border-blue-400/30 text-xs font-bold text-white transition-all disabled:opacity-40 disabled:hover:bg-nfl-blue"
          >
            {isSubmitting ? "Checking..." : "Submit"}
          </button>

          {/* Resign button */}
          {confirmResign ? (
            <div className="flex items-center gap-1">
              <button
                onClick={handleResign}
                className="px-3 py-1.5 rounded-full border border-rose-600 bg-rose-950/40 text-rose-400 text-xs font-bold hover:bg-rose-900/50 transition-all"
              >
                Confirm Resign
              </button>
              <button
                onClick={() => setConfirmResign(false)}
                className="px-2.5 py-1.5 rounded-full border border-border bg-surface text-gray-400 text-xs hover:bg-surface-raised transition-all"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={handleResign}
              title="Give up and reveal solutions"
              className="flex items-center space-x-1 px-3 py-2 rounded-full border border-border bg-surface hover:border-rose-600 hover:bg-rose-950/30 hover:text-rose-400 text-gray-500 text-xs transition-all"
            >
              <Flag className="h-3.5 w-3.5" />
              <span>Resign</span>
            </button>
          )}
        </div>
      )}

      {/* Completion / Game Over announcement */}
      {isGameOver && (
        <div className="w-full p-4 rounded-xl bg-surface border border-border text-center animate-in fade-in duration-300">
          <h3 className="text-lg font-bold text-white">
            {solvedGroups.length === 4 && strikesRemaining > 0 && !isResigned
              ? "🎉 All 4 Connections Found!"
              : isResigned
              ? "🏳️ Resigned — Solutions Revealed"
              : "💀 Game Over — 4 Mistakes (Solutions Revealed)"}
          </h3>
          <p className="text-xs text-gray-400 mt-1">
            {solvedGroups.length === 4 && strikesRemaining > 0 && !isResigned
              ? `Completed with ${strikesRemaining} mistake${strikesRemaining === 1 ? "" : "s"} remaining.`
              : "All 4 categories have been revealed above."}
          </p>
          <div className="mt-3 flex items-center justify-center gap-2">
            {confirmRestart ? (
              <>
                <button
                  onClick={handleRestart}
                  className="px-4 py-1.5 rounded-full bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-colors"
                >
                  Yes, restart
                </button>
                <button
                  onClick={() => setConfirmRestart(false)}
                  className="px-4 py-1.5 rounded-full border border-border bg-surface hover:bg-surface-raised text-gray-300 text-xs transition-colors"
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={handleRestart}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-full border border-border bg-surface hover:bg-surface-raised text-gray-300 text-xs font-medium transition-colors"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Restart
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
