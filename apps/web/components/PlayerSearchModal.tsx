"use client";

import React, { useEffect, useState, useRef } from "react";
import { Search, X, User } from "lucide-react";
import { playerSearchEngine, SearchPlayerItem } from "@/lib/search/playerSearch";
import { FALLBACK_PLAYERS } from "@/lib/search/fallbackPlayers";

function fallbackSearch(query: string, limit: number = 10): SearchPlayerItem[] {
  const clean = query.trim().toLowerCase();
  if (!clean) return [];
  const tokens = clean.split(/\s+/).filter(Boolean);
  const scored: Array<{ item: SearchPlayerItem; score: number }> = [];

  for (const p of FALLBACK_PLAYERS) {
    const lowerName = p.name.toLowerCase();
    const parts = lowerName.split(" ");
    const lastName = parts.length > 1 ? parts[parts.length - 1] : "";
    let score = -1;

    if (lowerName === clean) score = 150;
    else if (lastName === clean) score = 120;
    else if (lastName.startsWith(clean)) score = 100;
    else if (lowerName.startsWith(clean)) score = 90;
    else if (tokens.length > 1 && tokens.every((t) => lowerName.includes(t))) score = 80;
    else if (lowerName.includes(clean)) score = 50;

    if (score > 0) {
      if (p.isActive) score += 15;
      if (!p.endYear || p.endYear >= 2010) score += 5;
      scored.push({ item: p, score });
    }
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((s) => s.item);
}

interface PlayerSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectPlayer: (player: SearchPlayerItem) => void;
  title?: string;
}

export const PlayerSearchModal: React.FC<PlayerSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectPlayer,
  title = "Select an NFL Player",
}) => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchPlayerItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setSelectedIndex(0);
      // Show top suggestions immediately
      let initialSuggestions = playerSearchEngine.search("a", 6);
      if (!initialSuggestions || initialSuggestions.length === 0) {
        initialSuggestions = fallbackSearch("a", 6);
      }
      setResults(initialSuggestions);

      // Async background catalog sync
      playerSearchEngine.init().then(() => {
        if (inputRef.current?.value) {
          handleQueryChange(inputRef.current.value);
        }
      });

      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const handleQueryChange = (val: string) => {
    setQuery(val);
    if (!val.trim()) {
      // Show default top suggestions when query is cleared
      let defaultSuggestions = playerSearchEngine.search("a", 6);
      if (!defaultSuggestions || defaultSuggestions.length === 0) {
        defaultSuggestions = fallbackSearch("a", 6);
      }
      setResults(defaultSuggestions);
      setSelectedIndex(0);
      return;
    }
    let matches = playerSearchEngine.search(val, 10);
    if (!matches || matches.length === 0) {
      matches = fallbackSearch(val, 10);
    }
    setResults(matches);
    setSelectedIndex(0);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < results.length - 1 ? prev + 1 : prev));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : 0));
    } else if (e.key === "Enter" && results[selectedIndex]) {
      e.preventDefault();
      onSelectPlayer(results[selectedIndex]);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3 bg-surface-raised/40">
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-400 hover:text-white hover:bg-surface-raised transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Search input */}
        <div className="relative border-b border-border p-3">
          <Search className="absolute left-6 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type player name (e.g. Mahomes, Brady, Favre, Lamar)..."
            className="w-full rounded-lg bg-surface-raised border border-border py-2.5 pl-11 pr-10 text-sm text-white placeholder-gray-500 focus:border-nfl-blue focus:outline-none focus:ring-1 focus:ring-nfl-blue"
          />
          {query && (
            <button
              onClick={() => handleQueryChange("")}
              className="absolute right-6 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Results list */}
        <div className="max-h-72 overflow-y-auto divide-y divide-border/40">
          {results.length > 0 ? (
            results.map((player, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <button
                  key={player.id}
                  onClick={() => {
                    onSelectPlayer(player);
                    onClose();
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`w-full flex items-center justify-between px-4 py-3 text-left transition-colors ${
                    isSelected ? "bg-nfl-blue/30 text-white" : "text-gray-300 hover:bg-surface-raised/60"
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-raised border border-border text-gray-400">
                      <User className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white flex items-center space-x-2">
                        <span>{player.name}</span>
                        {player.isActive && (
                          <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                            Active
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-400">
                        {player.position} • {player.startYear} - {player.endYear || "Present"}
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500">Select ↵</div>
                </button>
              );
            })
          ) : query.trim().length > 0 ? (
            <div className="py-8 text-center text-sm text-gray-500">
              No players found matching &ldquo;{query}&rdquo;
            </div>
          ) : (
            <div className="py-8 text-center text-sm text-gray-500">
              Type to search active and historical NFL players
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
