"use client";

import React from "react";
import { Sparkles, Construction } from "lucide-react";
import Link from "next/link";

export default function ReverseGridPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[450px] text-center max-w-md mx-auto space-y-4">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-purple-600/20 text-purple-400 border border-purple-500/30">
        <Sparkles className="h-7 w-7" />
      </div>

      <h1 className="text-2xl font-black text-white">Reverse Grid Mode</h1>

      <p className="text-sm text-gray-400 leading-relaxed">
        The inverse puzzle mode where all 9 players are revealed upfront, and you must deduce the underlying historical criteria that connects them!
      </p>

      <div className="inline-flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-surface border border-border text-xs text-amber-400">
        <Construction className="h-4 w-4" />
        <span>Weekly featured mode — launches with Week 1 schedule</span>
      </div>

      <div className="pt-2">
        <Link
          href="/grid"
          className="inline-flex items-center px-4 py-2 rounded-lg bg-nfl-blue hover:bg-nfl-blue/90 text-white text-xs font-bold transition-all shadow-md"
        >
          Play Classic 3x3 Grid →
        </Link>
      </div>
    </div>
  );
}
