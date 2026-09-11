"use client";

import React, { useState, useCallback, useMemo } from "react";
import Image from "next/image";
import {
  WeddleGuessComparison,
  WeddleGuessResponse,
  WeddlePlayer,
  WeddleComparisonAttributes,
} from "@nfl-games/contracts";
import { PlayerSearchModal } from "@/components/PlayerSearchModal";
import { SearchPlayerItem } from "@/lib/search/playerSearch";
import { useWeddleGameState } from "@/hooks/useWeddleGameState";
import { getPlayerHeadshotUrl } from "@/lib/playerHeadshots";
import { getTeamLogoUrl } from "@/lib/teamLogos";
import {
  Search,
  AlertCircle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  RotateCcw,
  Share2,
  Sparkles,
  ArrowUp,
  ArrowDown,
  Flag,
} from "lucide-react";

interface WeddleBoardProps {
  puzzleId: string;
  puzzleNumber?: number;
  targetDate?: string;
}

const MAX_GUESSES = 6;

// Local fallback target for offline / disconnected situations
const DEMO_TARGET: WeddlePlayer = {
  player_id: "00-0033873",
  full_name: "Patrick Mahomes",
  headshot_url: "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3139477.png&w=350&h=254",
  team: "KC",
  side_of_ball: "Offense",
  position: "QB",
  conference: "AFC",
  division: "West",
  age: 28,
  height_inches: 74,
  height_formatted: "6'2\"",
  jersey_number: 15,
};

const COLOR_CLASSES = {
  green: "bg-emerald-600 text-white border-emerald-500 shadow-sm shadow-emerald-950/40",
  yellow: "bg-amber-500 text-white border-amber-400 shadow-sm shadow-amber-950/40",
  gray: "bg-zinc-700 text-gray-200 border-zinc-600 shadow-sm",
};

export const WeddleBoard: React.FC<WeddleBoardProps> = ({
  puzzleId,
  puzzleNumber = 1,
  targetDate = new Date().toISOString().split("T")[0],
}) => {
  const { state, isHydrated, recordGuess, recordResign, restart } = useWeddleGameState(puzzleId);

  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ message: string; isError: boolean } | null>(null);
  const [copiedShare, setCopiedShare] = useState(false);
  const [confirmResign, setConfirmResign] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);

  const attempts = state.attempts;
  const isWon = state.is_won;
  const isLoss = (state.guesses_remaining <= 0 || Boolean(state.is_resigned)) && !isWon;
  const isGameOver = state.is_completed || isWon || isLoss;
  const remainingSlots = Math.max(0, MAX_GUESSES - attempts.length);

  /**
   * Evaluates guess via FastAPI endpoint with offline fallback
   */
  const handleSelectPlayer = async (player: SearchPlayerItem) => {
    setIsSearchOpen(false);
    if (isGameOver || submitting) return;

    // Prevent duplicate guess in current session
    if (attempts.some((a) => a.player.player_id === player.id || a.player.full_name.toLowerCase() === player.name.toLowerCase())) {
      setFeedback({
        message: `${player.name} has already been guessed in this game.`,
        isError: true,
      });
      return;
    }

    setSubmitting(true);
    setFeedback(null);

    const previousGuesses = attempts.map((a) => a.player.player_id);

    try {
      const res = await fetch("/api/v1/weddle/guess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          puzzle_id: puzzleId,
          player_id: player.id,
          previous_guesses: previousGuesses,
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        const errMsg = errorData?.detail || `Error evaluating guess (${res.status})`;
        setFeedback({
          message: errMsg,
          isError: true,
        });
        return;
      }

      const data: WeddleGuessResponse = await res.json();
      recordGuess(data);

      if (data.is_correct) {
        setFeedback({
          message: `🎯 Spot on! You found ${data.comparison.player.full_name} in ${attempts.length + 1} guesses!`,
          isError: false,
        });
      }
    } catch (err) {
      console.error("Backend guess evaluation failed:", err);
      setFeedback({
        message: "Failed to connect to the game server. Please check your connection and try again.",
        isError: true,
      });
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * Resigns game and reveals target
   */
  const handleResign = async () => {
    setConfirmResign(false);
    try {
      const res = await fetch(`/api/v1/weddle/target/${puzzleId}`);
      if (res.ok) {
        const target: WeddlePlayer = await res.json();
        recordResign(target);
        return;
      }
    } catch {
      // Fallback
    }
    recordResign(DEMO_TARGET);
  };

  /**
   * Generates shareable emoji grid (Wordle/Weddle style)
   */
  const generateShareText = useCallback(() => {
    const score = isWon ? `${attempts.length}/${MAX_GUESSES}` : `X/${MAX_GUESSES}`;
    const header = `NFL Daily Weddle #${puzzleNumber} • ${score}\n`;

    const emojiGrid = attempts
      .map((att) => {
        const attrs = [
          att.attributes.team,
          att.attributes.side_of_ball,
          att.attributes.position,
          att.attributes.conference,
          att.attributes.division,
          att.attributes.age,
          att.attributes.height,
          att.attributes.jersey_number,
        ];
        return attrs
          .map((a) => (a.status === "green" ? "🟩" : a.status === "yellow" ? "🟨" : "⬛"))
          .join("");
      })
      .join("\n");

    return `${header}\n${emojiGrid}\n\nPlay at https://nfldaily.games/weddle`;
  }, [attempts, isWon, puzzleNumber]);

  const handleCopyShare = async () => {
    const text = generateShareText();
    try {
      await navigator.clipboard.writeText(text);
      setCopiedShare(true);
      setTimeout(() => setCopiedShare(false), 2500);
    } catch (err) {
      console.warn("Failed to copy share text:", err);
    }
  };

  if (!isHydrated) {
    return (
      <div className="flex items-center justify-center p-12 text-sm text-gray-400">
        Loading puzzle state...
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center w-full max-w-5xl mx-auto space-y-6">
      {/* Top Banner & Remaining Guess Indicators */}
      <div className="flex flex-col sm:flex-row items-center justify-between w-full bg-surface border border-border rounded-xl px-5 py-4 gap-4 shadow-md">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-600/20 border border-emerald-500/30 text-emerald-400 font-black">
            #{puzzleNumber}
          </div>
          <div>
            <h2 className="text-sm font-bold text-white uppercase tracking-wider">
              Guess the Active NFL Player
            </h2>
            <p className="text-xs text-gray-400">
              6 guesses max • Colors & arrows reveal how close you are
            </p>
          </div>
        </div>

        {/* Guesses indicator pills */}
        <div className="flex items-center gap-1.5">
          {Array.from({ length: MAX_GUESSES }).map((_, idx) => {
            const attempt = attempts[idx];
            const isCurrent = idx === attempts.length && !isGameOver;
            let pillClass = "bg-surface-raised border-border text-gray-500";

            if (attempt) {
              const allGreen = Object.values(attempt.attributes).every((a) => a.status === "green");
              pillClass = allGreen
                ? "bg-emerald-600 border-emerald-400 text-white font-bold"
                : "bg-zinc-700 border-zinc-500 text-gray-200 font-semibold";
            } else if (isCurrent) {
              pillClass = "bg-blue-600/30 border-blue-500 text-blue-300 animate-pulse";
            }

            return (
              <div
                key={idx}
                className={`flex h-8 w-8 items-center justify-center rounded-lg border text-xs font-mono transition-all ${pillClass}`}
                title={`Guess ${idx + 1}`}
              >
                {attempt ? (Object.values(attempt.attributes).every((a) => a.status === "green") ? "✓" : idx + 1) : idx + 1}
              </div>
            );
          })}
        </div>
      </div>

      {/* Primary Search Input Button */}
      {!isGameOver && (
        <div className="w-full flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => setIsSearchOpen(true)}
            disabled={submitting}
            className="flex-1 flex items-center justify-between px-5 py-3.5 rounded-xl bg-surface border-2 border-border hover:border-blue-500/80 hover:bg-surface-raised/80 text-left transition-all group shadow-lg"
          >
            <div className="flex items-center gap-3">
              <Search className="h-5 w-5 text-gray-400 group-hover:text-blue-400 transition-colors" />
              <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">
                Search active NFL player (e.g. Mahomes, Jefferson, Watt)...
              </span>
            </div>
            <kbd className="hidden sm:inline-block px-2.5 py-1 text-[11px] font-mono bg-surface-raised border border-border rounded text-gray-400 group-hover:text-gray-200">
              Guess {attempts.length + 1} of 6
            </kbd>
          </button>

          <button
            onClick={() => setConfirmResign(true)}
            className="px-4 py-3 rounded-xl bg-surface hover:bg-red-500/10 border border-border hover:border-red-500/40 text-gray-400 hover:text-red-400 text-xs font-semibold flex items-center justify-center gap-2 transition-colors shrink-0"
            title="Surrender and reveal mystery player"
          >
            <Flag className="h-4 w-4" />
            <span className="hidden sm:inline">Give Up</span>
          </button>
        </div>
      )}

      {/* Feedback Banner */}
      {feedback && (
        <div
          className={`flex items-center gap-2.5 px-4 py-2.5 rounded-lg text-xs font-medium w-full border animate-fade-in ${
            feedback.isError
              ? "bg-red-950/40 border-red-500/40 text-red-300"
              : "bg-emerald-950/40 border-emerald-500/40 text-emerald-300"
          }`}
        >
          {feedback.isError ? (
            <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Game Over Announcement Modal / Card */}
      {isGameOver && (
        <div
          className={`w-full p-6 rounded-2xl border flex flex-col md:flex-row items-center justify-between gap-6 shadow-2xl animate-fade-in ${
            isWon
              ? "bg-gradient-to-r from-emerald-950/60 via-surface to-surface border-emerald-500/40"
              : "bg-gradient-to-r from-red-950/60 via-surface to-surface border-red-500/40"
          }`}
        >
          <div className="flex items-center gap-5">
            {state.revealed_target && (
              <div className="relative h-16 w-16 sm:h-20 sm:w-20 rounded-full overflow-hidden bg-surface-raised border-2 border-white/20 shrink-0 shadow-lg">
                {state.revealed_target.headshot_url ? (
                  <Image
                    src={state.revealed_target.headshot_url}
                    alt={state.revealed_target.full_name}
                    fill
                    sizes="80px"
                    className="object-cover object-top"
                  />
                ) : (
                  <div className="h-full w-full flex items-center justify-center text-gray-500 font-bold">
                    {state.revealed_target.position}
                  </div>
                )}
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <span
                  className={`text-[11px] font-black uppercase tracking-wider px-2.5 py-0.5 rounded-full ${
                    isWon ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-red-500/20 text-red-400 border border-red-500/30"
                  }`}
                >
                  {isWon ? "Puzzle Solved! 🎉" : "Game Over"}
                </span>
                {isWon && (
                  <span className="text-xs text-amber-400 font-bold flex items-center gap-1">
                    <Sparkles className="h-3.5 w-3.5" /> {attempts.length} / 6 Guesses
                  </span>
                )}
              </div>
              <h3 className="text-xl sm:text-2xl font-black text-white mt-1">
                {state.revealed_target?.full_name ?? "Mystery Player"}
              </h3>
              <p className="text-xs text-gray-400 mt-0.5">
                {state.revealed_target
                  ? `${state.revealed_target.team} • ${state.revealed_target.position} • #${state.revealed_target.jersey_number} • ${state.revealed_target.conference} ${state.revealed_target.division} • ${state.revealed_target.age} yrs • ${state.revealed_target.height_formatted}`
                  : "Target revealed"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 w-full md:w-auto">
            <button
              onClick={handleCopyShare}
              className="flex-1 md:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all shadow-md active:scale-95"
            >
              <Share2 className="h-4 w-4" />
              <span>{copiedShare ? "Copied Grid!" : "Share Results"}</span>
            </button>
            <button
              onClick={() => setConfirmRestart(true)}
              className="px-3.5 py-2.5 rounded-xl bg-surface-raised hover:bg-surface-raised/80 border border-border text-gray-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition-colors"
              title="Play again or reset"
            >
              <RotateCcw className="h-4 w-4" />
              <span>Reset</span>
            </button>
          </div>
        </div>
      )}

      {/* 8-Attribute Guess Comparison Table */}
      <div className="w-full overflow-x-auto rounded-2xl border border-border bg-surface shadow-xl">
        <table className="w-full text-center border-collapse min-w-[760px]">
          <thead>
            <tr className="border-b border-border/80 bg-surface-raised/60 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
              <th className="py-3 px-3 text-left w-48 font-black">Player</th>
              <th className="py-3 px-2 w-20">Team</th>
              <th className="py-3 px-2 w-24">Side</th>
              <th className="py-3 px-2 w-20">Pos</th>
              <th className="py-3 px-2 w-20">Conf</th>
              <th className="py-3 px-2 w-20">Div</th>
              <th className="py-3 px-2 w-20">Age</th>
              <th className="py-3 px-2 w-20">Height</th>
              <th className="py-3 px-2 w-20">Number</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 text-xs">
            {/* Submitted Guess Rows */}
            {attempts.map((attempt, rowIdx) => {
              const p = attempt.player;
              const attrs = attempt.attributes;
              const teamLogo = getTeamLogoUrl({ criterion_id: p.team });

              return (
                <tr
                  key={`${p.player_id}-${rowIdx}`}
                  className="hover:bg-white/[0.02] transition-colors"
                >
                  {/* 0. Player Name & Headshot */}
                  <td className="py-3 px-3 text-left">
                    <div className="flex items-center gap-3">
                      <div className="relative h-9 w-9 rounded-full overflow-hidden bg-surface-raised border border-white/10 shrink-0">
                        {p.headshot_url ? (
                          <Image
                            src={p.headshot_url}
                            alt={p.full_name}
                            fill
                            sizes="36px"
                            className="object-cover object-top"
                          />
                        ) : (
                          <div className="h-full w-full flex items-center justify-center text-[10px] font-bold text-gray-400">
                            {p.position}
                          </div>
                        )}
                      </div>
                      <div className="truncate">
                        <div className="font-bold text-white text-xs truncate max-w-[140px]">
                          {p.full_name}
                        </div>
                        <div className="text-[10px] text-gray-400">
                          {p.team} • #{p.jersey_number}
                        </div>
                      </div>
                    </div>
                  </td>

                  {/* 1. Team */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center gap-1 font-bold ${
                        COLOR_CLASSES[attrs.team.status]
                      }`}
                      style={{ animationDelay: "100ms" }}
                    >
                      {teamLogo ? (
                        <div className="relative h-5 w-5 shrink-0">
                          <Image
                            src={teamLogo}
                            alt={p.team}
                            fill
                            sizes="20px"
                            className="object-contain"
                          />
                        </div>
                      ) : null}
                      <span>{p.team}</span>
                    </div>
                  </td>

                  {/* 2. Side of Ball */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center font-bold ${
                        COLOR_CLASSES[attrs.side_of_ball.status]
                      }`}
                      style={{ animationDelay: "200ms" }}
                    >
                      {p.side_of_ball}
                    </div>
                  </td>

                  {/* 3. Position */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center font-bold ${
                        COLOR_CLASSES[attrs.position.status]
                      }`}
                      style={{ animationDelay: "300ms" }}
                    >
                      {p.position}
                    </div>
                  </td>

                  {/* 4. Conference */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center font-bold ${
                        COLOR_CLASSES[attrs.conference.status]
                      }`}
                      style={{ animationDelay: "400ms" }}
                    >
                      {p.conference}
                    </div>
                  </td>

                  {/* 5. Division */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center font-bold ${
                        COLOR_CLASSES[attrs.division.status]
                      }`}
                      style={{ animationDelay: "500ms" }}
                    >
                      {p.division}
                    </div>
                  </td>

                  {/* 6. Age */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center gap-1 font-bold ${
                        COLOR_CLASSES[attrs.age.status]
                      }`}
                      style={{ animationDelay: "600ms" }}
                    >
                      <span>{p.age}</span>
                      {attrs.age.direction === "higher" && (
                        <ArrowUp className="h-4 w-4 stroke-[3] text-white shrink-0 animate-bounce" />
                      )}
                      {attrs.age.direction === "lower" && (
                        <ArrowDown className="h-4 w-4 stroke-[3] text-white shrink-0 animate-bounce" />
                      )}
                    </div>
                  </td>

                  {/* 7. Height */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center gap-1 font-bold ${
                        COLOR_CLASSES[attrs.height.status]
                      }`}
                      style={{ animationDelay: "700ms" }}
                    >
                      <span className="text-[11px]">{p.height_formatted}</span>
                      {attrs.height.direction === "higher" && (
                        <ArrowUp className="h-4 w-4 stroke-[3] text-white shrink-0 animate-bounce" />
                      )}
                      {attrs.height.direction === "lower" && (
                        <ArrowDown className="h-4 w-4 stroke-[3] text-white shrink-0 animate-bounce" />
                      )}
                    </div>
                  </td>

                  {/* 8. Jersey Number */}
                  <td className="p-2">
                    <div
                      className={`h-11 rounded-lg border flex items-center justify-center gap-1 font-bold ${
                        COLOR_CLASSES[attrs.jersey_number.status]
                      }`}
                      style={{ animationDelay: "800ms" }}
                    >
                      <span>#{p.jersey_number}</span>
                      {attrs.jersey_number.direction === "higher" && (
                        <ArrowUp className="h-4 w-4 stroke-[3] text-white shrink-0 animate-bounce" />
                      )}
                      {attrs.jersey_number.direction === "lower" && (
                        <ArrowDown className="h-4 w-4 stroke-[3] text-white shrink-0 animate-bounce" />
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}

            {/* Unfilled Empty Attempt Slots */}
            {Array.from({ length: remainingSlots }).map((_, emptyIdx) => {
              const slotNumber = attempts.length + emptyIdx + 1;
              return (
                <tr key={`empty-${slotNumber}`} className="opacity-40">
                  <td className="py-3 px-3 text-left">
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-full border border-dashed border-gray-600 flex items-center justify-center text-xs font-mono text-gray-500">
                        {slotNumber}
                      </div>
                      <span className="text-xs text-gray-500 font-mono">
                        Attempt {slotNumber}
                      </span>
                    </div>
                  </td>
                  {Array.from({ length: 8 }).map((_, cIdx) => (
                    <td key={cIdx} className="p-2">
                      <div className="h-11 rounded-lg border border-dashed border-zinc-800 bg-surface-raised/20" />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Color Grading Guide / Legend */}
      <div className="w-full flex flex-wrap items-center justify-center gap-6 p-4 rounded-xl bg-surface border border-border text-xs text-gray-300">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 rounded bg-emerald-600 border border-emerald-400" />
          <span className="font-semibold text-white">Exact Match</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 rounded bg-amber-500 border border-amber-400" />
          <span className="font-semibold text-white">Close / Partial</span>
          <span className="text-[11px] text-gray-400">(±2 years, ±2&quot;, ±2 #, or position group)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 rounded bg-zinc-700 border border-zinc-500" />
          <span className="font-semibold text-white">Incorrect</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center text-white font-bold gap-0.5">
            <ArrowUp className="h-3.5 w-3.5" /> <ArrowDown className="h-3.5 w-3.5" />
          </div>
          <span className="font-semibold text-white">Target Higher / Lower</span>
        </div>
      </div>

      {/* Modals */}
      <PlayerSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelectPlayer={handleSelectPlayer}
        title={`Guess ${attempts.length + 1} of ${MAX_GUESSES} - Select NFL Player`}
      />

      {/* Confirm Resign Modal */}
      {confirmResign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-fade-in">
          <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-red-400">
              <AlertCircle className="h-6 w-6" />
              <h3 className="text-lg font-bold text-white">Give Up?</h3>
            </div>
            <p className="text-xs text-gray-300 leading-relaxed">
              Are you sure you want to surrender? This will end the game and reveal today&apos;s mystery player.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setConfirmResign(false)}
                className="px-4 py-2 rounded-lg bg-surface-raised border border-border text-xs font-semibold text-gray-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleResign}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-xs font-bold text-white transition-colors shadow-md"
              >
                Reveal Player
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm Reset Modal */}
      {confirmRestart && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-fade-in">
          <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-amber-400">
              <RotateCcw className="h-6 w-6" />
              <h3 className="text-lg font-bold text-white">Reset Game?</h3>
            </div>
            <p className="text-xs text-gray-300 leading-relaxed">
              This will clear your current attempts and let you replay today&apos;s puzzle from scratch.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setConfirmRestart(false)}
                className="px-4 py-2 rounded-lg bg-surface-raised border border-border text-xs font-semibold text-gray-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setConfirmRestart(false);
                  restart();
                }}
                className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-xs font-bold text-white transition-colors shadow-md"
              >
                Reset Puzzle
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
