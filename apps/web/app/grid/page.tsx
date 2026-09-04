"use client";

import React, { useEffect, useState } from "react";
import { DailyPuzzleResponse, GridCriterion } from "@nfl-games/contracts";
import { GridBoard } from "@/components/game-boards/GridBoard";
import { Loader2 } from "lucide-react";

export default function GridPage() {
  const [puzzle, setPuzzle] = useState<DailyPuzzleResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchPuzzle() {
      try {
        const res = await fetch("/api/v1/puzzles/grid/daily");
        if (!res.ok) throw new Error("Puzzle fetch failed");
        const data: DailyPuzzleResponse = await res.json();
        setPuzzle(data);
      } catch (err) {
        console.warn("Using offline fallback 3x3 Grid puzzle:", err);
        // Resilient fallback puzzle
        setPuzzle({
          puzzle_id: "demo-grid-001",
          puzzle_number: 1,
          target_date: new Date().toISOString().split("T")[0],
          game_type: "grid",
          puzzle_data: {
            rows: [
              { criterion_id: "FRAN_GNB", type: "FRANCHISE", display_title: "Green Bay Packers" },
              { criterion_id: "FRAN_NYJ", type: "FRANCHISE", display_title: "New York Jets" },
              { criterion_id: "STAT_PASS_4000", type: "STAT_SEASON", display_title: "4,000+ Pass Yds", subtitle: "Single Season" },
            ],
            columns: [
              { criterion_id: "FRAN_MIN", type: "FRANCHISE", display_title: "Minnesota Vikings" },
              { criterion_id: "ACCOLADE_HOF", type: "ACCOLADE", display_title: "Hall of Fame", subtitle: "Inducted" },
              { criterion_id: "DRAFT_RD1", type: "DRAFT_ROUND", display_title: "1st Round Pick", subtitle: "NFL Draft" },
            ],
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
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        <p className="text-xs text-gray-400">Loading today&apos;s 3x3 Grid...</p>
      </div>
    );
  }

  if (!puzzle) return null;

  const rows = (puzzle.puzzle_data.rows || []) as GridCriterion[];
  const columns = (puzzle.puzzle_data.columns || []) as GridCriterion[];

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-black tracking-tight text-white">3x3 Immaculate Grid</h1>
        <p className="text-xs text-gray-400 mt-1">
          Puzzle #{puzzle.puzzle_number} • {puzzle.target_date}
        </p>
      </div>

      <GridBoard puzzleId={puzzle.puzzle_id} rows={rows} columns={columns} />
    </div>
  );
}
