"use client";

import React, { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import { Top10Entry, Top10GuessResponse } from "@nfl-games/contracts";
import { PlayerSearchModal } from "@/components/PlayerSearchModal";
import { SearchPlayerItem } from "@/lib/search/playerSearch";
import { useTop10GameState } from "@/hooks/useTop10GameState";
import { getPlayerHeadshotUrl } from "@/lib/playerHeadshots";
import { Search, AlertCircle, CheckCircle2, XCircle, Flag, RotateCcw } from "lucide-react";

interface Top10BoardProps {
  puzzleId: string;
  title: string;
  metricLabel: string;
  description?: string | null;
}

// Fallback leaderboard for offline resilience (ONLY for demo-top10-001)
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

/** Row thumbnail with Next Image headshot support */
const Top10PlayerAvatar: React.FC<{ name: string; playerId?: string | null; headshotUrl?: string | null }> = ({
  name,
  playerId,
  headshotUrl,
}) => {
  const [imgError, setImgError] = useState(false);
  const src = getPlayerHeadshotUrl(name, playerId, headshotUrl);

  if (!src || imgError) {
    return null;
  }

  return (
    <div className="relative h-8 w-8 sm:h-9 sm:w-9 rounded-full overflow-hidden bg-surface-raised border border-white/10 shrink-0">
      <Image
        src={src}
        alt={name}
        fill
        sizes="36px"
        className="object-cover object-top"
        onError={() => setImgError(true)}
      />
    </div>
  );
};

export const Top10Board: React.FC<Top10BoardProps> = ({
  puzzleId,
  title,
  metricLabel,
  description,
}) => {
  const {
    state,
    isHydrated,
    recordHit,
    recordMiss,
    recordResign,
    restart,
  } = useTop10GameState(puzzleId);

  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [lastFeedback, setLastFeedback] = useState<{ message: string; isError: boolean } | null>(null);
  // `fullLeaderboard` contains all 10 entries revealed at the end of the game
  const [fullLeaderboard, setFullLeaderboard] = useState<Record<number, Top10Entry>>({});
  const [confirmResign, setConfirmResign] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);

  const solvedCount = Object.keys(state.revealed_slots).length;
  const isWin = solvedCount === 10 && state.strikes_remaining > 0 && !state.is_resigned;
  const isLoss = state.strikes_remaining <= 0 || Boolean(state.is_resigned);
  const isGameOver = state.is_completed || isWin || isLoss;

  /** Fetches the full leaderboard from API (or demo fallback) without mutating user-guessed entries */
  const fetchAndRevealAll = useCallback(async () => {
    let allEntries: Record<number, Top10Entry> = {};

    try {
      const res = await fetch(`/api/v1/top10/leaderboard/${puzzleId}`);
      if (res.ok) {
        const data: Top10Entry[] = await res.json();
        for (const entry of data) {
          allEntries[entry.rank] = entry;
        }
      }
    } catch {
      // Fallback
    }

    // If API had no data and it's the demo puzzle, use demo fallback
    if (Object.keys(allEntries).length === 0 && puzzleId === "demo-top10-001") {
      for (const entry of Object.values(DEMO_TOP10_LEADERBOARD)) {
        allEntries[entry.rank] = entry;
      }
    }

    setFullLeaderboard(allEntries);
  }, [puzzleId]);

  // If game is completed on load/hydration, reveal full answers
  useEffect(() => {
    if (isHydrated && isGameOver && Object.keys(fullLeaderboard).length === 0) {
      fetchAndRevealAll();
    }
  }, [isHydrated, isGameOver, fullLeaderboard, fetchAndRevealAll]);

  // Reset fullLeaderboard when puzzleId changes
  useEffect(() => {
    setFullLeaderboard({});
    setLastFeedback(null);
    setConfirmResign(false);
    setConfirmRestart(false);
  }, [puzzleId]);

  const handleRestart = () => {
    if (!confirmRestart) {
      setConfirmRestart(true);
      return;
    }
    restart();
    setLastFeedback(null);
    setFullLeaderboard({});
    setConfirmResign(false);
    setConfirmRestart(false);
  };

  const handleResign = async () => {
    if (!confirmResign) {
      setConfirmResign(true);
      return;
    }
    setConfirmResign(false);
    recordResign();
    await fetchAndRevealAll();
  };

  const handleSelectPlayer = async (player: SearchPlayerItem) => {
    if (state.strikes_remaining <= 0 || solvedCount === 10 || isGameOver) return;

    const playerNameLower = player.name.toLowerCase().trim();

    // Check if already guessed — match by ID or by name (case-insensitive)
    if (
      state.submitted_player_ids.includes(player.id) ||
      Object.values(state.revealed_slots).some(
        (e) => e.player_id === player.id || e.player_name.toLowerCase().trim() === playerNameLower
      ) ||
      state.missed_guesses.some((n) => n.toLowerCase().trim() === playerNameLower)
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
    } catch {
      // Backend offline: fallback
    }

    // Fallback evaluation — only for demo mock puzzle when backend is offline
    if (!data && puzzleId === "demo-top10-001") {
      const entry =
        DEMO_TOP10_LEADERBOARD[player.id] ??
        Object.values(DEMO_TOP10_LEADERBOARD).find(
          (e) => e.player_name.toLowerCase().trim() === playerNameLower
        );
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

    if (!data) {
      setLastFeedback({
        message: "Unable to reach validation server. Please try again.",
        isError: true,
      });
      return;
    }

    if (data.is_hit && data.entry) {
      recordHit(data.entry, player.id);
      setLastFeedback({
        message: `Hit! #${data.entry.rank} - ${data.entry.player_name} (${data.entry.formatted_value})`,
        isError: false,
      });

      const nextSolvedCount = solvedCount + 1;
      if (nextSolvedCount === 10) {
        await fetchAndRevealAll();
      }
    } else {
      recordMiss(player.name, player.id);
      setLastFeedback({
        message: `Miss! ${player.name} is not in the Top 10.`,
        isError: true,
      });

      if (state.strikes_remaining - 1 <= 0) {
        await fetchAndRevealAll();
      }
    }
  };

  // Decide which entries to display in the slots:
  // If game over, fullLeaderboard is merged with user-guessed revealed_slots
  const displayEntries = isGameOver ? { ...fullLeaderboard, ...state.revealed_slots } : state.revealed_slots;

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
                  dot <= state.strikes_remaining ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]" : "bg-border/60"
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

      {/* Guess Input + Resign Row */}
      {!isGameOver && (
        <div className="w-full mb-6 flex items-stretch gap-2">
          {/* Search button */}
          <button
            onClick={() => {
              setConfirmResign(false);
              setIsSearchOpen(true);
            }}
            className="flex-1 p-3 rounded-xl border border-border bg-surface hover:border-nfl-blue hover:bg-surface-raised transition-all flex items-center justify-between text-gray-400 text-sm shadow-md group"
          >
            <div className="flex items-center space-x-2.5">
              <Search className="h-4 w-4 text-gray-400 group-hover:text-white" />
              <span className="group-hover:text-gray-200">Guess a player in the Top 10...</span>
            </div>
            <span className="text-xs px-2 py-0.5 rounded bg-surface-raised border border-border text-gray-400">
              Search
            </span>
          </button>

          {/* Resign button */}
          {confirmResign ? (
            <div className="flex items-stretch gap-1">
              <button
                onClick={handleResign}
                className="px-3 rounded-xl border border-rose-600 bg-rose-950/40 text-rose-400 text-xs font-bold hover:bg-rose-900/50 transition-all"
              >
                Confirm
              </button>
              <button
                onClick={() => setConfirmResign(false)}
                className="px-3 rounded-xl border border-border bg-surface text-gray-400 text-xs hover:bg-surface-raised transition-all"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={handleResign}
              title="Resign and reveal answers"
              className="px-3 rounded-xl border border-border bg-surface hover:border-rose-600 hover:bg-rose-950/30 hover:text-rose-400 text-gray-500 transition-all flex items-center gap-1.5 text-xs"
            >
              <Flag className="h-3.5 w-3.5" />
              <span>Resign</span>
            </button>
          )}
        </div>
      )}

      {/* 10 Ranked Slots */}
      <div className="w-full space-y-2 mb-6">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((rank) => {
          const entry = displayEntries[rank];
          const isRevealed = Boolean(entry);
          // wasGuessed is true ONLY if the player actively guessed this rank correctly
          const wasGuessed = Boolean(state.revealed_slots[rank]);
          // isAutoRevealed is true when game is over and this entry was missed by the player
          const isAutoRevealed = isGameOver && isRevealed && !wasGuessed;

          return (
            <div
              key={rank}
              className={`w-full p-3 rounded-xl border flex items-center justify-between transition-all duration-300 ${
                isRevealed
                  ? wasGuessed
                    ? "bg-emerald-950/20 border-emerald-500/60 ring-1 ring-emerald-500/20 shadow-[0_0_12px_rgba(16,185,129,0.1)] text-white"
                    : "bg-rose-950/25 border-rose-500/70 ring-1 ring-rose-500/30 shadow-[0_0_12px_rgba(244,63,94,0.15)] text-white"
                  : "bg-surface/50 border-border/70 text-gray-500"
              }`}
            >
              <div className="flex items-center space-x-3 min-w-0">
                {/* Rank Badge */}
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-black shadow-sm transition-colors ${
                    isRevealed
                      ? wasGuessed
                        ? "bg-emerald-600 text-white shadow-emerald-900/40"
                        : "bg-rose-900/90 border border-rose-500/60 text-rose-200 shadow-rose-950/40"
                      : "bg-surface-raised text-gray-500"
                  }`}
                >
                  {rank}
                </span>

                {/* Headshot Avatar */}
                {isRevealed && (
                  <Top10PlayerAvatar
                    name={entry.player_name}
                    playerId={entry.player_id}
                    headshotUrl={entry.headshot_url}
                  />
                )}

                {/* Player Information */}
                {isRevealed ? (
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span
                        className={`text-sm font-bold truncate ${
                          isAutoRevealed ? "text-rose-100" : "text-white"
                        }`}
                      >
                        {entry.player_name}
                      </span>
                      {entry.primary_franchise && (
                        <span
                          className={`text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded border ${
                            isAutoRevealed
                              ? "bg-rose-950/60 border-rose-500/40 text-rose-300"
                              : "bg-emerald-950/60 border-emerald-500/40 text-emerald-300"
                          }`}
                        >
                          {entry.primary_franchise}
                        </span>
                      )}
                    </div>
                    {entry.active_years && (
                      <span className="text-[11px] text-gray-400 block leading-tight">
                        {entry.active_years}
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-sm tracking-widest font-mono text-gray-600 select-none">••••••••••••••••</span>
                )}
              </div>

              {/* Metric Value & Status Indicator */}
              <div className="flex items-center space-x-2 shrink-0 ml-2">
                {isRevealed ? (
                  <>
                    <span
                      className={`text-sm font-black ${
                        isAutoRevealed ? "text-rose-400" : "text-amber-400"
                      }`}
                    >
                      {entry.formatted_value}
                    </span>
                    {wasGuessed ? (
                      <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-500/50 text-emerald-300">
                        <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                        <span className="hidden sm:inline">Found</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-rose-950/80 border border-rose-500/50 text-rose-300">
                        <XCircle className="h-3 w-3 text-rose-400" />
                        <span className="hidden sm:inline">Missed</span>
                      </span>
                    )}
                  </>
                ) : (
                  <span className="text-xs text-gray-600 font-mono">Hidden</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Missed guesses tags */}
      {state.missed_guesses.length > 0 && (
        <div className="w-full mb-6">
          <div className="text-xs text-gray-400 mb-2">Incorrect Guesses:</div>
          <div className="flex flex-wrap gap-1.5">
            {state.missed_guesses.map((name) => (
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
        <div
          className={`w-full p-4 rounded-xl border text-center animate-in fade-in duration-300 ${
            isWin
              ? "bg-gradient-to-b from-emerald-950/40 to-surface border-emerald-500/50 ring-1 ring-emerald-500/20"
              : "bg-gradient-to-b from-rose-950/40 to-surface border-rose-500/50 ring-1 ring-rose-500/20"
          }`}
        >
          <h3 className="text-lg font-bold text-white">
            {isWin
              ? "🏆 Flawless! Complete Top 10 Found!"
              : state.is_resigned
              ? "🏳️ Resigned — Leaderboard Revealed"
              : "💀 Defeat — 3 Strikes Reached"}
          </h3>
          <p className="text-xs text-gray-300 mt-1">
            {isWin
              ? "You solved the entire Top 10 without striking out!"
              : `You found ${solvedCount} of 10 leaders. Missed players are highlighted in red above.`}
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

      <PlayerSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelectPlayer={handleSelectPlayer}
        title={`Guess for ${title}`}
      />
    </div>
  );
};
