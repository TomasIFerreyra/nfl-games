"use client";

import React, { useEffect, useState } from "react";
import { DailyPuzzleResponse, ConnectionsItem } from "@nfl-games/contracts";
import { ConnectionsBoard } from "@/components/game-boards/ConnectionsBoard";
import { Loader2 } from "lucide-react";

export default function ConnectionsPage() {
  const [puzzle, setPuzzle] = useState<DailyPuzzleResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchPuzzle() {
      try {
        const res = await fetch("/api/v1/puzzles/connections/daily");
        if (!res.ok) throw new Error("Puzzle fetch failed");
        const data: DailyPuzzleResponse = await res.json();
        setPuzzle(data);
      } catch (err) {
        console.warn("Using offline fallback Connections puzzle:", err);
        setPuzzle({
          puzzle_id: "demo-connections-001",
          puzzle_number: 1,
          target_date: new Date().toISOString().split("T")[0],
          game_type: "connections",
          puzzle_data: {
            items: [
              { item_id: "i1", display_text: "Cam Newton" },
              { item_id: "i2", display_text: "Lamar Jackson" },
              { item_id: "i3", display_text: "Kyler Murray" },
              { item_id: "i4", display_text: "Baker Mayfield" },
              { item_id: "i5", display_text: "Patrick Mahomes" },
              { item_id: "i6", display_text: "Peyton Manning" },
              { item_id: "i7", display_text: "Drew Brees" },
              { item_id: "i8", display_text: "Tom Brady" },
              { item_id: "i9", display_text: "Randy Moss" },
              { item_id: "i10", display_text: "Jerry Rice" },
              { item_id: "i11", display_text: "Terrell Owens" },
              { item_id: "i12", display_text: "Cris Carter" },
              { item_id: "i13", display_text: "Michael Strahan" },
              { item_id: "i14", display_text: "T.J. Watt" },
              { item_id: "i15", display_text: "J.J. Watt" },
              { item_id: "i16", display_text: "Aaron Donald" },
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
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        <p className="text-xs text-gray-400">Loading today&apos;s Connections...</p>
      </div>
    );
  }

  if (!puzzle) return null;

  const items = (puzzle.puzzle_data.items || []) as ConnectionsItem[];

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-black tracking-tight text-white">NFL Connections 4x4</h1>
        <p className="text-xs text-gray-400 mt-1">
          Puzzle #{puzzle.puzzle_number} • {puzzle.target_date}
        </p>
      </div>

      <ConnectionsBoard puzzleId={puzzle.puzzle_id} items={items} />
    </div>
  );
}
