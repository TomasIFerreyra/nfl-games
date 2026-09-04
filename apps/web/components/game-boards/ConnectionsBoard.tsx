"use client";

import React, { useState, useEffect } from "react";
import { ConnectionsItem, ConnectionsGroup, ConnectionsValidateResponse } from "@nfl-games/contracts";
import { GameStateManager } from "@/lib/storage/gameState";
import { Shuffle, AlertTriangle, CheckCircle2 } from "lucide-react";

interface ConnectionsBoardProps {
  puzzleId: string;
  items: ConnectionsItem[];
}

export const ConnectionsBoard: React.FC<ConnectionsBoardProps> = ({ puzzleId, items }) => {
  const [boardItems, setBoardItems] = useState<ConnectionsItem[]>(items);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [strikesRemaining, setStrikesRemaining] = useState(4);
  const [solvedGroups, setSolvedGroups] = useState<ConnectionsGroup[]>([]);
  const [isOneAway, setIsOneAway] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const state = GameStateManager.loadState();
    if (state.games.connections.puzzle_id === puzzleId) {
      setStrikesRemaining(state.games.connections.strikes_remaining);
      setSolvedGroups(state.games.connections.solved_groups);
    } else {
      state.games.connections.puzzle_id = puzzleId;
      state.games.connections.strikes_remaining = 4;
      state.games.connections.solved_groups = [];
      state.games.connections.guess_history = [];
      state.games.connections.is_completed = false;
      GameStateManager.saveState(state);
      setStrikesRemaining(4);
      setSolvedGroups([]);
    }
  }, [puzzleId]);

  // Exclude solved items from remaining board
  const solvedItemIds = new Set(solvedGroups.flatMap((g) => g.item_ids));
  const activeItems = boardItems.filter((i) => !solvedItemIds.has(i.item_id));

  const handleToggleSelect = (id: string) => {
    setErrorMessage(null);
    setIsOneAway(false);
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter((item) => item !== id));
    } else {
      if (selectedIds.length < 4) {
        setSelectedIds([...selectedIds, id]);
      }
    }
  };

  const handleShuffle = () => {
    const shuffled = [...activeItems].sort(() => Math.random() - 0.5);
    setBoardItems([...solvedGroups.flatMap((g) => g.item_ids.map((id) => items.find((i) => i.item_id === id)!)), ...shuffled]);
  };

  const handleSubmit = async () => {
    if (selectedIds.length !== 4 || strikesRemaining <= 0 || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setIsOneAway(false);

    try {
      const res = await fetch("/api/v1/connections/validate-group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          puzzle_id: puzzleId,
          selected_item_ids: selectedIds,
        }),
      });

      const data: ConnectionsValidateResponse = await res.json();

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
        setStrikesRemaining(nextStrikes);
        setIsOneAway(data.is_one_away);

        if (!data.is_one_away) {
          setErrorMessage("Incorrect group.");
        }

        if (nextStrikes <= 0) {
          GameStateManager.updateStreak("connections", false);
        }

        const state = GameStateManager.loadState();
        state.games.connections.strikes_remaining = nextStrikes;
        state.games.connections.is_completed = nextStrikes <= 0;
        GameStateManager.saveState(state);
      }
    } catch (err) {
      console.error("Connections validation error:", err);
      setErrorMessage("Network error validating guess.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const getTierBadgeStyle = (tier: number) => {
    switch (tier) {
      case 1:
        return "bg-amber-400 text-black";
      case 2:
        return "bg-emerald-400 text-black";
      case 3:
        return "bg-blue-400 text-white";
      case 4:
        return "bg-purple-400 text-white";
      default:
        return "bg-gray-400 text-black";
    }
  };

  const isGameOver = strikesRemaining <= 0 || solvedGroups.length === 4;

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
            className={`w-full p-3.5 rounded-lg text-center font-semibold animate-in zoom-in-95 duration-200 ${getTierBadgeStyle(
              g.tier
            )}`}
          >
            <div className="text-xs uppercase font-extrabold tracking-wider">{g.title}</div>
            <div className="text-[11px] font-medium opacity-90 mt-0.5">
              {g.item_ids.map((id) => items.find((i) => i.item_id === id)?.display_text).join(", ")}
            </div>
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
      <div className="flex items-center space-x-2 mb-5">
        <span className="text-xs text-gray-400 font-medium">Mistakes remaining:</span>
        <div className="flex space-x-1.5">
          {[1, 2, 3, 4].map((dot) => (
            <div
              key={dot}
              className={`h-2.5 w-2.5 rounded-full transition-colors ${
                dot <= strikesRemaining ? "bg-gray-400" : "bg-border/60"
              }`}
            />
          ))}
        </div>
      </div>

      {/* Action Controls */}
      {!isGameOver && (
        <div className="flex items-center space-x-3">
          <button
            onClick={handleShuffle}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-full border border-border bg-surface hover:bg-surface-raised text-xs font-semibold text-gray-300 transition-colors"
          >
            <Shuffle className="h-3.5 w-3.5" />
            <span>Shuffle</span>
          </button>

          <button
            onClick={() => setSelectedIds([])}
            disabled={selectedIds.length === 0}
            className="px-4 py-2 rounded-full border border-border bg-surface hover:bg-surface-raised text-xs font-semibold text-gray-300 transition-colors disabled:opacity-40"
          >
            Deselect All
          </button>

          <button
            onClick={handleSubmit}
            disabled={selectedIds.length !== 4 || isSubmitting}
            className="px-5 py-2 rounded-full bg-nfl-blue hover:bg-nfl-blue/90 border border-blue-400/30 text-xs font-bold text-white transition-all disabled:opacity-40 disabled:hover:bg-nfl-blue"
          >
            Submit
          </button>
        </div>
      )}

      {/* Completion announcement */}
      {isGameOver && (
        <div className="w-full p-4 rounded-xl bg-surface border border-border text-center animate-in fade-in duration-300">
          <h3 className="text-lg font-bold text-white">
            {solvedGroups.length === 4 ? "🎉 All 4 Connections Found!" : "Game Over"}
          </h3>
          <p className="text-xs text-gray-400 mt-1">
            {solvedGroups.length === 4
              ? `Completed with ${strikesRemaining} mistakes remaining.`
              : "Better luck tomorrow!"}
          </p>
        </div>
      )}
    </div>
  );
};
