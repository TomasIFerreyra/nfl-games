"use client";

import React, { useEffect } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log unhandled error to console or error tracking service
    console.error("Unhandled client error in mini-game platform:", error);
  }, [error]);

  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center text-center px-4 py-12">
      <div className="w-16 h-16 bg-red-950/40 border border-red-800 rounded-full flex items-center justify-center mb-4 text-red-400 shadow-lg">
        <AlertTriangle size={32} />
      </div>
      <h2 className="text-2xl font-black tracking-tight text-white mb-2">
        Something went wrong!
      </h2>
      <p className="text-gray-400 text-sm max-w-md mb-6 leading-relaxed">
        An unexpected error occurred while loading this game view. Your progress and local streaks are preserved.
      </p>
      <button
        onClick={() => reset()}
        className="flex items-center gap-2 bg-nfl-blue hover:bg-nfl-blue/90 text-white font-bold py-2.5 px-6 rounded-lg transition-colors shadow-lg active:scale-95"
      >
        <RefreshCw size={16} /> Try Again
      </button>
    </div>
  );
}
