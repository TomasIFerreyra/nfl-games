"use client";

import React, { useEffect, useState } from "react";
import { DailyPuzzleResponse } from "@nfl-games/contracts";
import { WeddleBoard } from "@/components/game-boards/WeddleBoard";
import { Loader2 } from "lucide-react";

export default function WeddlePage() {
  const [puzzle, setPuzzle] = useState<DailyPuzzleResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchPuzzle() {
      try {
        const res = await fetch("/api/v1/puzzles/weddle/daily");
        if (!res.ok) throw new Error("Puzzle fetch failed");
        const data: DailyPuzzleResponse = await res.json();
        setPuzzle(data);
      } catch (err) {
        console.warn("Using offline fallback Weddle puzzle:", err);
        setPuzzle({
          puzzle_id: `weddle-${new Date().toISOString().split("T")[0]}`,
          puzzle_number: 1,
          target_date: new Date().toISOString().split("T")[0],
          game_type: "weddle",
          puzzle_data: {
            mode: "weddle",
            max_attempts: 6,
            attributes_count: 8,
          },
          created_at: new Date().toISOString(),
        });
      } finally {
        setLoading(false);
      }
    }
    fetchPuzzle();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-3">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        <p className="text-xs text-gray-400">Loading today&apos;s Guess the Player mystery...</p>
      </div>
    );
  }

  if (!puzzle) return null;

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-black tracking-tight text-white">Guess the Player</h1>
        <p className="text-xs text-gray-400 mt-1">
          Weddle Daily Challenge • Puzzle #{puzzle.puzzle_number} • {puzzle.target_date}
        </p>
      </div>

      <WeddleBoard
        puzzleId={puzzle.puzzle_id}
        puzzleNumber={puzzle.puzzle_number}
        targetDate={puzzle.target_date}
      />
    </div>
  );
}
