"use client";

import React, { useEffect, useState } from "react";
import { DailyPuzzleResponse } from "@nfl-games/contracts";
import { Top10Board } from "@/components/game-boards/Top10Board";
import { Loader2 } from "lucide-react";

export default function Top10Page() {
  const [puzzle, setPuzzle] = useState<DailyPuzzleResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchPuzzle() {
      try {
        const res = await fetch("/api/v1/puzzles/top10/daily");
        if (!res.ok) throw new Error("Puzzle fetch failed");
        const data: DailyPuzzleResponse = await res.json();
        setPuzzle(data);
      } catch (err) {
        console.warn("Using offline fallback Top 10 puzzle:", err);
        setPuzzle({
          puzzle_id: "demo-top10-001",
          puzzle_number: 1,
          target_date: new Date().toISOString().split("T")[0],
          game_type: "top10",
          puzzle_data: {
            category_id: "all_time_pass_td",
            title: "NFL All-Time Career Passing Touchdowns",
            description: "Regular season career passing touchdowns leaders.",
            metric_label: "Passing Touchdowns",
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
        <Loader2 className="h-8 w-8 animate-spin text-amber-500" />
        <p className="text-xs text-gray-400">Loading today&apos;s Top 10 Leaderboard...</p>
      </div>
    );
  }

  if (!puzzle) return null;

  const data = puzzle.puzzle_data;

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-black tracking-tight text-white">Top 10 Leaderboard</h1>
        <p className="text-xs text-gray-400 mt-1">
          Puzzle #{puzzle.puzzle_number} • {puzzle.target_date}
        </p>
      </div>

      <Top10Board
        puzzleId={puzzle.puzzle_id}
        title={data.title as string}
        metricLabel={data.metric_label as string}
        description={data.description as string}
      />
    </div>
  );
}
