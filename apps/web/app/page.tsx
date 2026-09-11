"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Grid3X3, Layers, Trophy, RotateCcw, ArrowRight, Flame, Sparkles, UserSearch } from "lucide-react";
import { GameStateManager } from "@/lib/storage/gameState";
import { ClientLocalStorageState } from "@nfl-games/contracts";

export default function HomePage() {
  const [state, setState] = useState<ClientLocalStorageState | null>(null);

  useEffect(() => {
    setState(GameStateManager.loadState());
  }, []);

  const games = [
    {
      title: "3x3 Grid",
      description: "Test your football knowledge with the classic 9-cell intersection challenge.",
      href: "/grid",
      icon: Grid3X3,
      color: "from-blue-600 to-indigo-700",
      streakKey: "grid" as const,
      status: state?.games.grid.is_completed ? "Completed Today" : "Play Today's Grid",
      isDone: state?.games.grid.is_completed,
    },
    {
      title: "Guess the Player",
      description: "Weddle-style mystery: 6 attempts to deduce the active NFL player by attributes.",
      href: "/weddle",
      icon: UserSearch,
      color: "from-emerald-600 to-teal-800",
      streakKey: null,
      status: "Play Today's Mystery",
      isDone: false,
    },
    {
      title: "Connections 4x4",
      description: "Find four groups of four NFL players or milestones that share a secret link.",
      href: "/connections",
      icon: Layers,
      color: "from-violet-600 to-purple-800",
      streakKey: "connections" as const,
      status: state?.games.connections.is_completed ? "Completed Today" : "Play Today's Puzzle",
      isDone: state?.games.connections.is_completed,
    },
    {
      title: "Top 10 Leaderboard",
      description: "Guess the top 10 all-time leaders in iconic NFL historical stat categories.",
      href: "/top10",
      icon: Trophy,
      color: "from-amber-600 to-orange-700",
      streakKey: "top10" as const,
      status: state?.games.top10.is_completed ? "Completed Today" : "Guess the Leaders",
      isDone: state?.games.top10.is_completed,
    },
    {
      title: "Reverse Grid",
      description: "Players are revealed. Can you deduce the mystery criteria that unite them?",
      href: "/reverse-grid",
      icon: RotateCcw,
      color: "from-purple-900/40 to-violet-950/40",
      streakKey: null,
      status: "Mode in Development",
      isDone: false,
      comingSoon: true,
    },
  ];


  return (
    <div className="flex flex-col items-center justify-center space-y-10">
      {/* Hero section */}
      <div className="text-center max-w-2xl space-y-3">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-surface border border-border text-xs text-gray-300 mb-2">
          <Sparkles className="h-3.5 w-3.5 text-amber-400" />
          <span>New puzzles published daily at 00:00 UTC</span>
        </div>
        <h1 className="text-4xl md:text-5xl font-black tracking-tight text-white">
          NFL Daily Mini-Games
        </h1>
        <p className="text-sm md:text-base text-gray-400">
          Sharpen your football IQ with daily Immaculate Grid, Connections, and Top 10 trivia.
        </p>
      </div>

      {/* Game Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 w-full">
        {games.map((game) => {
          const Icon = game.icon;
          const streak = game.streakKey ? state?.streaks[game.streakKey] : null;

          if (game.comingSoon) {
            return (
              <div
                key={game.title}
                className="relative overflow-hidden rounded-2xl border border-border/60 bg-surface/30 p-6 select-none cursor-not-allowed opacity-60"
              >
                {/* Greyish layer overlay */}
                <div className="absolute inset-0 bg-neutral-950/50 backdrop-grayscale pointer-events-none z-10" />

                <div className="relative z-20">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center space-x-4">
                      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-surface-raised border border-border text-gray-500 shadow-inner">
                        <Icon className="h-6 w-6" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="text-lg font-bold text-gray-300">
                            {game.title}
                          </h2>
                        </div>
                      </div>
                    </div>

                    <span className="text-[11px] uppercase font-bold tracking-wider px-2.5 py-1 rounded-md bg-surface-raised/80 border border-border text-gray-400">
                      Coming Soon
                    </span>
                  </div>

                  <p className="text-xs text-gray-400 mt-4 leading-relaxed">
                    {game.description}
                  </p>

                  <div className="mt-5 flex items-center justify-between pt-3 border-t border-border/40 text-xs">
                    <span className="text-gray-400 font-medium">
                      {game.status}
                    </span>
                    <span className="inline-flex items-center px-3 py-1 rounded-lg bg-surface-raised border border-border text-gray-400 font-bold text-xs">
                      Coming Soon
                    </span>
                  </div>
                </div>
              </div>
            );
          }

          return (
            <Link
              key={game.href}
              href={game.href}
              className="group relative overflow-hidden rounded-2xl border border-border bg-surface p-6 transition-all hover:border-gray-500 hover:shadow-xl hover:scale-[1.01]"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center space-x-4">
                  <div className={`flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${game.color} text-white shadow-lg`}>
                    <Icon className="h-6 w-6" />
                  </div>
                  <div>
                    <h2 className="text-lg font-bold text-white group-hover:text-blue-400 transition-colors">
                      {game.title}
                    </h2>
                    {streak && streak.current > 0 && (
                      <div className="flex items-center space-x-1 text-xs text-amber-400 font-semibold mt-0.5">
                        <Flame className="h-3.5 w-3.5 fill-amber-400" />
                        <span>{streak.current} day streak</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="text-gray-500 group-hover:text-white transition-colors">
                  <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </div>
              </div>

              <p className="text-xs text-gray-400 mt-4 leading-relaxed">
                {game.description}
              </p>

              <div className="mt-5 flex items-center justify-between pt-3 border-t border-border/50 text-xs">
                <span className={game.isDone ? "text-emerald-400 font-semibold" : "text-gray-400 font-medium"}>
                  {game.status}
                </span>
                <span className="text-blue-400 font-semibold group-hover:underline">Play Now →</span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
