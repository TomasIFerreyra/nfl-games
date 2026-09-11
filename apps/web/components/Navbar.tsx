"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Flame, Grid3X3, Layers, Trophy, RotateCcw, UserSearch } from "lucide-react";

interface NavbarProps {
  onOpenStreaks?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenStreaks }) => {
  const pathname = usePathname();

  const navItems = [
    { label: "3x3 Grid", href: "/grid", icon: Grid3X3, comingSoon: false },
    { label: "Connections", href: "/connections", icon: Layers, comingSoon: false },
    { label: "Top 10", href: "/top10", icon: Trophy, comingSoon: false },
    { label: "Guess Player", href: "/weddle", icon: UserSearch, comingSoon: false },
    { label: "Reverse Grid", href: "/reverse-grid", icon: RotateCcw, comingSoon: true },
  ];


  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-surface/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
        {/* Brand */}
        <Link href="/" className="flex items-center space-x-3 group">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-nfl-blue text-white font-black text-lg shadow-md group-hover:bg-nfl-red transition-colors">
            NFL
          </div>
          <div>
            <span className="font-extrabold tracking-tight text-white text-lg">DAILY</span>
            <span className="text-xs uppercase ml-1.5 px-1.5 py-0.5 rounded bg-surface-raised text-gray-300 font-mono">
              GAMES
            </span>
          </div>
        </Link>

        {/* Navigation links */}
        <nav className="hidden md:flex items-center space-x-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;

            if (item.comingSoon) {
              return (
                <div
                  key={item.label}
                  className="flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-sm font-medium text-gray-500 cursor-not-allowed opacity-60 select-none"
                  title="Coming Soon"
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                  <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-surface-raised border border-border text-gray-400 font-semibold">
                    Soon
                  </span>
                </div>
              );
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-surface-raised text-white border border-border"
                    : "text-gray-400 hover:text-white hover:bg-surface-raised/50"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Actions */}
        <div className="flex items-center space-x-3">
          <button
            onClick={onOpenStreaks}
            className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg bg-surface-raised hover:bg-surface-raised/80 text-amber-400 border border-amber-500/20 text-xs font-semibold transition-all hover:scale-105"
            title="View Daily Streaks"
          >
            <Flame className="h-4 w-4 fill-amber-400" />
            <span className="hidden sm:inline">Streaks</span>
          </button>
        </div>
      </div>
    </header>
  );
};
