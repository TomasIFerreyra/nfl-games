"use client";

import React, { useState, useEffect } from "react";
import { Top10Entry, Top10GuessResponse } from "@nfl-games/contracts";
import { PlayerSearchModal } from "@/components/PlayerSearchModal";
import { SearchPlayerItem } from "@/lib/search/playerSearch";
import { GameStateManager } from "@/lib/storage/gameState";
import { Search, AlertCircle, CheckCircle2, XCircle } from "lucide-react";

interface Top10BoardProps {
  puzzleId: string;
  title: string;
  metricLabel: string;
  description?: string | null;
}

// Fallback leaderboard for offline resilience
const DEMO_TOP10_LEADERBOARD: Record<string, Top10Entry> = {
  "p-brady-tom01": { rank: 1, player_id: "p-brady-tom01", player_name: "Tom Brady", metric_value: 649, formatted_value: "649 TDs", active_years: "2000-2022", primary_franchise: "NWE" },
  "p-brees-dre01": { rank: 2, player_id: "p-brees-dre01", player_name: "Drew Brees", metric_value: 571, formatted_value: "571 TDs", active_years: "2001-2020", primary_franchise: "NOR" },
  "p-manning-pey01": { rank: 3, player_id: "p-manning-pey01", player_name: "Peyton Manning", metric_value: 539, formatted_value: "539 TDs", active_years: "1998-2015", primary_franchise: "IND" },
  "p-favre-bre01": { rank: 4, player_id: "p-favre-bre01", player_name: "Brett Favre", metric_value: 508, formatted_value: "508 TDs", active_years: "1991-2010", primary_franchise: "GNB" },
  "00-0023459": { rank: 5, player_id: "00-0023459", player_name: "Aaron Rodgers", metric_value: 475, formatted_value: "475 TDs", active_years: "2005-Present", primary_franchise: "GNB" },
  "p-rivers-phi01": { rank: 6, player_id: "p-rivers-phi01", player_name: "Philip Rivers", metric_value: 421, formatted_value: "421 TDs", active_years: "2004-2020", primary_franchise: "LAC" },
  "p-marino-dan01": { rank: 7, player_id: "p-marino-dan01", player_name: "Dan Marino", metric_value: 420, formatted_value: "420 TDs", active_years: "1983-1999", primary_franchise: "MIA" },
  "p-roethlisberger-ben01": { rank: 8, player_id: "p-roethlisberger-ben01", player_name: "Ben Roethlisberger", metric_value: 418, formatted_value: "418 TDs", active_years: "2004-2021", primary_franchise: "PIT" },
  "p-ryan-mat01": { rank: 9, player_id: "p-ryan-mat01", player_name: "Matt Ryan", metric_value: 381, formatted_value: "381 TDs", active_years: "2008-2022", primary_franchise: "ATL" },
  "p-manning-eli01": { rank: 10, player_id: "p-manning-eli01", player_name: "Eli Manning", metric_value: 366, formatted_value: "366 TDs", active_years: "2004-2019", primary_franchise: "NYG" },
};

export const Top10Board: React.FC<Top10BoardProps> = ({
  puzzleId,
  title,
  metricLabel,
  description,
}) => {
  const [revealedEntries, setRevealedEntries] = useState<Record<number, Top10Entry>>({});
  const [strikesRemaining, setStrikesRemaining] = useState(3);
  const [missedGuesses, setMissedGuesses] = useState<string[]>([]);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [lastFeedback, setLastFeedback] = useState<{ message: string; isError: boolean } | null>(null);

  useEffect(() => {
    const state = GameStateManager.loadState();
    if (state.games.top10.puzzle_id === puzzleId) {
      setStrikesRemaining(state.games.top10.strikes_remaining);
      setMissedGuesses(state.games.top10.missed_guesses);
      // Restore revealed entries if any
      const restored: Record<number, Top10Entry> = {};
      for (const r of state.games.top10.revealed_ranks) {
        const found = Object.values(DEMO_TOP10_LEADERBOARD).find((e) => e.rank === r);
        if (found) restored[r] = found;
      }
      setRevealedEntries(restored);
    } else {
      state.games.top10.puzzle_id = puzzleId;
      state.games.top10.strikes_remaining = 3;
      state.games.top10.revealed_ranks = [];
      state.games.top10.missed_guesses = [];
      state.games.top10.is_completed = false;
      GameStateManager.saveState(state);
      setStrikesRemaining(3);
      setRevealedEntries({});
      setMissedGuesses([]);
    }
  }, [puzzleId]);

  const handleSelectPlayer = async (player: SearchPlayerItem) => {
    if (strikesRemaining <= 0 || Object.keys(revealedEntries).length === 10) return;

    // Check if already guessed
    if (
      Object.values(revealedEntries).some((e) => e.player_id === player.id) ||
      missedGuesses.includes(player.name)
    ) {
      setLastFeedback({ message: `${player.name} has already been guessed!`, isError: true });
      return;
    }

    let data: Top10GuessResponse | null = null;

    try {
      const res = await fetch("/api/v1/top10/guess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          puzzle_id: puzzleId,
          player_id: player.id,
        }),
      });

      if (res.ok) {
        data = await res.json();
      }
    } catch (err) {
      // Backend offline: fallback
    }

    // Fallback evaluation
    if (!data) {
      const entry = DEMO_TOP10_LEADERBOARD[player.id];
      if (entry) {
        data = {
          is_hit: true,
          entry,
          player_name: player.name,
          strikes_added: 0,
        };
      } else {
        data = {
          is_hit: false,
          entry: null,
          player_name: player.name,
          strikes_added: 1,
        };
      }
    }

    if (data.is_hit && data.entry) {
      const nextRevealed = { ...revealedEntries, [data.entry.rank]: data.entry };
      setRevealedEntries(nextRevealed);
      setLastFeedback({
        message: `Hit! #${data.entry.rank} - ${data.entry.player_name} (${data.entry.formatted_value})`,
        isError: false,
      });

      const isWin = Object.keys(nextRevealed).length === 10;
      if (isWin) {
        GameStateManager.updateStreak("top10", true);
      }

      const state = GameStateManager.loadState();
      state.games.top10.revealed_ranks = Object.keys(nextRevealed).map(Number);
      state.games.top10.is_completed = isWin;
      GameStateManager.saveState(state);
    } else {
      const nextStrikes = strikesRemaining - 1;
      const nextMisses = [...missedGuesses, player.name];
      setStrikesRemaining(nextStrikes);
      setMissedGuesses(nextMisses);
      setLastFeedback({
        message: `Miss! ${player.name} is not in the Top 10.`,
        isError: true,
      });

      if (nextStrikes <= 0) {
        GameStateManager.updateStreak("top10", false);
      }

      const state = GameStateManager.loadState();
      state.games.top10.strikes_remaining = nextStrikes;
      state.games.top10.missed_guesses = nextMisses;
      state.games.top10.is_completed = nextStrikes <= 0;
      GameStateManager.saveState(state);
    }
  };

  const solvedCount = Object.keys(revealedEntries).length;
  const isGameOver = strikesRemaining <= 0 || solvedCount === 10;

  return (
    <div className="w-full max-w-xl mx-auto flex flex-col items-center">
      {/* Category header */}
      <div className="w-full text-center mb-5">
        <h2 className="text-xl font-black text-white tracking-tight">{title}</h2>
        {description && <p className="text-xs text-gray-400 mt-1">{description}</p>}
        <div className="text-xs font-semibold text-amber-400 mt-1 uppercase tracking-wider">
          Metric: {metricLabel}
        </div>
      </div>

      {/* Status Bar */}
      <div className="w-full flex items-center justify-between mb-4 px-2">
        <div className="flex items-center space-x-2">
          <span className="text-xs uppercase tracking-wider text-gray-400">Strikes Remaining:</span>
          <div className="flex space-x-1.5">
            {[1, 2, 3].map((dot) => (
              <div
                key={dot}
                className={`h-3 w-3 rounded-full transition-colors ${
                  dot <= strikesRemaining ? "bg-rose-500" : "bg-border/60"
                }`}
              />
            ))}
          </div>
        </div>

        <div className="text-xs text-gray-400">
          Revealed: <span className="font-bold text-white">{solvedCount}/10</span>
        </div>
      </div>

      {/* Feedback banner */}
      {lastFeedback && (
        <div
          className={`w-full mb-4 p-2.5 rounded-lg text-xs flex items-center space-x-2 animate-in fade-in duration-150 ${
            lastFeedback.isError
              ? "bg-rose-950/40 border border-rose-800 text-rose-300"
              : "bg-emerald-950/40 border border-emerald-800 text-emerald-300"
          }`}
        >
          {lastFeedback.isError ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
          <span>{lastFeedback.message}</span>
        </div>
      )}

      {/* Guess Input Trigger Button */}
      {!isGameOver && (
        <button
          onClick={() => setIsSearchOpen(true)}
          className="w-full mb-6 p-3 rounded-xl border border-border bg-surface hover:border-nfl-blue hover:bg-surface-raised transition-all flex items-center justify-between text-gray-400 text-sm shadow-md group"
        >
          <div className="flex items-center space-x-2.5">
            <Search className="h-4 w-4 text-gray-400 group-hover:text-white" />
            <span className="group-hover:text-gray-200">Guess a player in the Top 10...</span>
          </div>
          <span className="text-xs px-2 py-0.5 rounded bg-surface-raised border border-border text-gray-400">
            Search
          </span>
        </button>
      )}

      {/* 10 Ranked Slots */}
      <div className="w-full space-y-2 mb-6">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((rank) => {
          const entry = revealedEntries[rank];
          const isRevealed = Boolean(entry);

          return (
            <div
              key={rank}
              className={`w-full p-3 rounded-lg border flex items-center justify-between transition-all ${
                isRevealed
                  ? "bg-surface-raised border-emerald-500/30 text-white"
                  : "bg-surface/50 border-border/70 text-gray-500"
              }`}
            >
              <div className="flex items-center space-x-3">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded text-xs font-black ${
                    isRevealed ? "bg-nfl-blue text-white" : "bg-surface-raised text-gray-500"
                  }`}
                >
                  {rank}
                </span>

                {isRevealed ? (
                  <div>
                    <span className="text-sm font-bold text-white">{entry.player_name}</span>
                    {entry.primary_franchise && (
                      <span className="text-[10px] uppercase ml-2 px-1.5 py-0.5 rounded bg-surface text-gray-400 border border-border">
                        {entry.primary_franchise}
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-sm tracking-widest font-mono text-gray-600">••••••••••••••••</span>
                )}
              </div>

              <div>
                {isRevealed ? (
                  <span className="text-sm font-black text-amber-400">{entry.formatted_value}</span>
                ) : (
                  <span className="text-xs text-gray-600">Hidden</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Missed guesses tags */}
      {missedGuesses.length > 0 && (
        <div className="w-full mb-6">
          <div className="text-xs text-gray-400 mb-2">Incorrect Guesses:</div>
          <div className="flex flex-wrap gap-1.5">
            {missedGuesses.map((name) => (
              <span
                key={name}
                className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full bg-rose-950/30 border border-rose-900/50 text-rose-300 text-xs"
              >
                <XCircle className="h-3 w-3 text-rose-400" />
                <span>{name}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Game Over Announcement */}
      {isGameOver && (
        <div className="w-full p-4 rounded-xl bg-surface border border-border text-center animate-in fade-in duration-300">
          <h3 className="text-lg font-bold text-white">
            {solvedCount === 10 ? "🏆 Flawless! Complete Top 10 Found!" : "Game Over"}
          </h3>
          <p className="text-xs text-gray-400 mt-1">
            You found {solvedCount} of 10 leaders.
          </p>
        </div>
      )}

      <PlayerSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelectPlayer={handleSelectPlayer}
        title={`Guess for ${title}`}
      />
    </div>
  );
};
