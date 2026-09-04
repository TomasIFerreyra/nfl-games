"use client";

import React, { useEffect, useState } from "react";
import { X, Flame, Trophy, Award, Calendar } from "lucide-react";
import { GameStateManager } from "@/lib/storage/gameState";
import { ClientLocalStorageState } from "@nfl-games/contracts";

interface StreakModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const StreakModal: React.FC<StreakModalProps> = ({ isOpen, onClose }) => {
  const [state, setState] = useState<ClientLocalStorageState | null>(null);

  useEffect(() => {
    if (isOpen) {
      setState(GameStateManager.loadState());
    }
  }, [isOpen]);

  if (!isOpen || !state) return null;

  const games = [
    { key: "grid" as const, title: "3x3 Grid", icon: Trophy, color: "text-blue-400" },
    { key: "connections" as const, title: "Connections 4x4", icon: Award, color: "text-emerald-400" },
    { key: "top10" as const, title: "Top 10 Leaderboard", icon: Flame, color: "text-amber-400" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-md overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4 bg-surface-raised/40">
          <div className="flex items-center space-x-2">
            <Flame className="h-5 w-5 text-amber-400 fill-amber-400" />
            <h3 className="font-bold text-white">Daily Streaks & Records</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:text-white hover:bg-surface-raised transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {games.map((g) => {
            const streak = state.streaks[g.key];
            const Icon = g.icon;
            return (
              <div
                key={g.key}
                className="flex items-center justify-between p-4 rounded-lg bg-surface-raised/60 border border-border"
              >
                <div className="flex items-center space-x-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface border border-border">
                    <Icon className={`h-5 w-5 ${g.color}`} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">{g.title}</h4>
                    <div className="text-xs text-gray-400 flex items-center space-x-1 mt-0.5">
                      <Calendar className="h-3 w-3" />
                      <span>Last played: {streak.last_played || "Never"}</span>
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-xl font-black text-amber-400 flex items-center justify-end space-x-1">
                    <span>{streak.current}</span>
                    <Flame className="h-4 w-4 fill-amber-400 inline" />
                  </div>
                  <div className="text-[11px] text-gray-400">Max: {streak.max}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
