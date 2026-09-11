"use client";

import React, { useState } from "react";
import Image from "next/image";
import { CheckCircle2, Check, XCircle } from "lucide-react";
import { getPlayerHeadshotUrl } from "@/lib/playerHeadshots";

export interface PlayerTileProps {
  /** Full name of the player */
  name: string;
  /** Player ID (GSIS, PFR, UUID, or item_id) for headshot matching */
  playerId?: string | null;
  /** Optional explicit headshot image URL */
  headshotUrl?: string | null;
  /** Primary position (e.g. QB, WR, DE) */
  position?: string | null;
  /** Team abbreviation (e.g. KC, GB, MIN) */
  team?: string | null;
  /** Rarity percentage score for Grid mode (e.g. 14.5) */
  rarityScore?: number | null;
  /** Pick percentage for missed/revealed cell (e.g. 68.4) */
  pickPercentage?: number | null;
  /** Missed/unrevealed end of game state */
  isMissed?: boolean;
  /** Optional custom badge or subtext element */
  badge?: React.ReactNode;
  /** Optional secondary line of text */
  subtext?: string | null;
  /** Visual variant: 'grid' for 3x3 solved cells, 'grid-missed' for end-of-game revealed answers, 'connections' for 4x4 selectable items, 'default' */
  variant?: "grid" | "grid-missed" | "connections" | "default";
  /** Selection state for Connections board */
  isSelected?: boolean;
  /** Disabled interaction state */
  disabled?: boolean;
  /** Click / selection handler */
  onClick?: () => void;
  /** Additional custom class names */
  className?: string;
  /** High priority image loading for above-the-fold tiles */
  priority?: boolean;
}

export const PlayerTile: React.FC<PlayerTileProps> = ({
  name,
  playerId,
  headshotUrl: explicitHeadshotUrl,
  position,
  team,
  rarityScore,
  pickPercentage,
  isMissed = false,
  badge,
  subtext,
  variant = "default",
  isSelected = false,
  disabled = false,
  onClick,
  className = "",
  priority = false,
}) => {
  const [imgError, setImgError] = useState(false);

  // Check both name and playerId to resolve headshots reliably across all game modes
  const headshotSrc = getPlayerHeadshotUrl(name, playerId, explicitHeadshotUrl);
  const showImage = Boolean(headshotSrc) && !imgError;

  // Split name for compact mobile / hover display
  const nameParts = (name || "").trim().split(/\s+/);
  const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : name;
  const firstName = nameParts.length > 1 ? nameParts.slice(0, -1).join(" ") : "";

  // Base card variant styles
  const isGridMissed = variant === "grid-missed" || (variant === "grid" && isMissed) || isMissed;
  const isGrid = variant === "grid" && !isMissed;
  const isConnections = variant === "connections";

  const getContainerStyle = () => {
    if (isGridMissed) {
      return "bg-gradient-to-b from-rose-950/60 to-surface border-2 border-red-500/80 ring-1 ring-red-500/40 shadow-inner text-white";
    }
    if (isGrid) {
      return "bg-gradient-to-b from-emerald-950/50 to-surface border-emerald-500/60 shadow-inner text-white";
    }
    if (isConnections) {
      if (isSelected) {
        return "bg-gradient-to-b from-blue-900/60 to-surface-raised border-blue-400 ring-2 ring-blue-500/60 shadow-lg shadow-blue-950/40 text-white scale-[0.98]";
      }
      return "bg-surface border-border text-white hover:border-gray-500 hover:bg-surface-raised hover:shadow-md";
    }
    return "bg-surface border-border text-white hover:border-border/80";
  };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`group relative aspect-square w-full rounded-xl border p-0 select-none overflow-hidden text-center transition-all duration-300 ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-nfl-blue ${getContainerStyle()} ${disabled ? "cursor-default" : "cursor-pointer"
        } ${className}`}
      title={name}
    >
      {/* Subtle Stadium Radial Glow */}
      <div className="absolute inset-0 bg-gradient-to-b from-white/[0.04] to-transparent pointer-events-none" />

      {/* Selected Indicator for Connections */}
      {isConnections && isSelected && (
        <div className="absolute top-1.5 right-1.5 z-20 flex h-4 w-4 sm:h-5 sm:w-5 items-center justify-center rounded-full bg-blue-500 text-white shadow-sm ring-1 ring-white/40 animate-in zoom-in-75 duration-150">
          <Check className="h-2.5 w-2.5 sm:h-3 sm:w-3 stroke-[3]" />
        </div>
      )}

      {/* Grid Success Rarity Top-Right Pill Badge */}
      {isGrid && rarityScore !== null && rarityScore !== undefined && (
        <div className="absolute top-1 sm:top-1.5 right-1 sm:right-1.5 z-20 flex items-center space-x-0.5 sm:space-x-1 rounded-full bg-emerald-900/80 border border-emerald-400/40 px-1 sm:px-1.5 py-0.5 text-[8px] sm:text-[10px] font-bold text-emerald-300 backdrop-blur-xs shadow-sm">
          <CheckCircle2 className="h-2 w-2 sm:h-2.5 sm:w-2.5 shrink-0 text-emerald-400" />
          <span>{rarityScore.toFixed(1)}%</span>
        </div>
      )}

      {/* Grid Missed / Unrevealed Top Pick Pill Badge */}
      {isGridMissed && (
        <div className="absolute top-1 sm:top-1.5 right-1 sm:right-1.5 z-20 flex items-center space-x-0.5 sm:space-x-1 rounded-full bg-rose-950/90 border border-rose-500/60 px-1 sm:px-1.5 py-0.5 text-[8px] sm:text-[10px] font-bold text-rose-300 backdrop-blur-xs shadow-sm">
          <XCircle className="h-2 w-2 sm:h-2.5 sm:w-2.5 shrink-0 text-rose-400" />
          <span>
            {pickPercentage !== null && pickPercentage !== undefined
              ? `${pickPercentage.toFixed(1)}%`
              : "Top Pick"}
          </span>
        </div>
      )}

      {/* Primary Visual Presentation */}
      {showImage ? (
        <>
          {/* Official Headshot with smooth scale down on hover */}
          <div className="absolute inset-0 flex items-center justify-center p-2 sm:p-2.5 transition-transform duration-300 ease-in-out sm:group-hover:scale-75 sm:group-hover:-translate-y-3.5">
            <div className="relative w-full h-full filter drop-shadow-[0_4px_8px_rgba(0,0,0,0.6)]">
              <Image
                src={headshotSrc!}
                alt={name}
                fill
                sizes="(max-width: 640px) 25vw, (max-width: 1024px) 20vw, 160px"
                priority={priority}
                onError={() => setImgError(true)}
                className={`object-contain object-bottom pointer-events-none transition-all duration-300 ${isGridMissed ? "grayscale-[35%] opacity-85" : ""
                  }`}
              />
            </div>
          </div>

          {/* Mobile Compact Bottom Gradient Overlay */}
          <div className="sm:hidden absolute bottom-0 inset-x-0 z-10 bg-gradient-to-t from-black/95 via-black/75 to-transparent pt-3 pb-1 px-1 flex flex-col items-center justify-end">
            <span className="text-[10px] font-bold text-white tracking-tight truncate w-full leading-tight">
              {lastName}
            </span>
            {position && (
              <span className="text-[8px] font-medium text-gray-300 leading-none mt-0.5">
                {position} {team ? `• ${team}` : ""}
              </span>
            )}
          </div>

          {/* Desktop Smooth Hover Reveal Backdrop & Information */}
          <div className="hidden sm:flex absolute inset-x-0 bottom-0 z-10 flex-col items-center justify-end bg-gradient-to-t from-black/95 via-black/85 to-transparent pt-6 pb-2 px-1.5 opacity-0 translate-y-3 sm:group-hover:opacity-100 sm:group-hover:translate-y-0 transition-all duration-300 ease-out pointer-events-none">
            {firstName && (
              <span className="text-[9px] font-medium text-gray-400 uppercase tracking-wider leading-none truncate max-w-full">
                {firstName}
              </span>
            )}
            <div className="text-xs font-black text-white tracking-tight leading-tight truncate max-w-full">
              {lastName}
            </div>

            {(position || team || subtext || badge) && (
              <div className="flex items-center justify-center space-x-1 mt-0.5 max-w-full">
                {position && (
                  <span className="text-[10px] font-semibold text-blue-400 bg-blue-950/60 px-1 rounded border border-blue-500/30">
                    {position}
                  </span>
                )}
                {team && (
                  <span className="text-[10px] font-semibold text-gray-300">
                    {team}
                  </span>
                )}
                {subtext && (
                  <span className="text-[9px] text-gray-400 truncate">
                    {subtext}
                  </span>
                )}
                {badge}
              </div>
            )}
          </div>
        </>
      ) : (
        /* Fallback: Directly show the player's full name centered with optional position/badge */
        <div className="absolute inset-0 flex flex-col items-center justify-center p-2 text-center select-none">
          <div className="text-xs sm:text-sm font-extrabold text-white line-clamp-2 leading-tight px-1">
            {name}
          </div>
          {(position || team || subtext || badge) && (
            <div className="flex items-center justify-center space-x-1 mt-1.5 max-w-full">
              {position && (
                <span className="text-[9px] sm:text-[10px] font-semibold text-blue-400 bg-blue-950/60 px-1.5 py-0.5 rounded border border-blue-500/30">
                  {position}
                </span>
              )}
              {team && (
                <span className="text-[9px] sm:text-[10px] font-medium text-gray-400">
                  {team}
                </span>
              )}
              {subtext && (
                <span className="text-[9px] text-gray-400 truncate">
                  {subtext}
                </span>
              )}
              {badge}
            </div>
          )}
        </div>
      )}
    </button>
  );
};
