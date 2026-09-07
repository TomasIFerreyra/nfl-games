"use client";

import React, { useState, useEffect } from "react";
import { GridCriterion, GridValidateResponse } from "@nfl-games/contracts";
import { PlayerSearchModal } from "@/components/PlayerSearchModal";
import { SearchPlayerItem } from "@/lib/search/playerSearch";
import { GameStateManager } from "@/lib/storage/gameState";
import { CheckCircle2, AlertCircle, RotateCcw } from "lucide-react";
import { getTeamLogoUrl } from "@/lib/teamLogos";

const CriterionHeaderCell: React.FC<{ criterion: GridCriterion }> = ({ criterion }) => {
  const [imgError, setImgError] = useState(false);
  const logoUrl = getTeamLogoUrl(criterion);

  if (logoUrl && !imgError) {
    return (
      <div
        className="w-full h-full flex items-center justify-center p-2 sm:p-3"
        title={criterion.display_title}
      >
        <img
          src={logoUrl}
          alt={criterion.display_title}
          onError={() => setImgError(true)}
          className="w-full h-full object-contain filter drop-shadow-md select-none transition-transform group-hover:scale-105"
          loading="lazy"
        />
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col items-center justify-center text-center p-1.5 sm:p-2 overflow-hidden">
      <div className="text-[11px] sm:text-xs md:text-sm font-bold text-white line-clamp-2 leading-tight">
        {criterion.display_title}
      </div>
      {criterion.subtitle && (
        <div className="text-[9px] sm:text-[10px] md:text-xs text-gray-400 mt-0.5 line-clamp-2 leading-tight">
          {criterion.subtitle}
        </div>
      )}
    </div>
  );
};

interface GridBoardProps {
  puzzleId: string;
  rows: GridCriterion[];
  columns: GridCriterion[];
}

// Client-side validation fallback dictionary for demo/offline play resilience
const DEMO_CELL_ANSWERS: Record<string, string[]> = {
  // Row 0: Packers
  "r0_c0": ["p-favre-bre01", "p-jennings-gre01", "p-longwell-rya01", "p-smith-zad01", "p-sharper-dar01"],
  "r0_c1": ["p-favre-bre01", "p-starr-bar01", "p-white-reg01", "p-lofton-jam01", "p-woodson-cha01", "p-butler-ler01"],
  "r0_c2": ["00-0023459", "00-0036264", "p-matthews-cla01", "p-clark-ken01", "p-alexander-jai01", "p-walker-qua01"],
  // Row 1: Jets
  "r1_c0": ["p-favre-bre01", "p-darnold-sam01", "p-fitzpatrick-rya01", "00-0033897"],
  "r1_c1": ["p-namath-joe01", "p-martin-cur01", "p-revis-dar01", "p-favre-bre01", "p-lott-ron01", "p-reed-ed01"],
  "r1_c2": ["p-namath-joe01", "p-revis-dar01", "p-sanchez-mar01", "p-darnold-sam01", "p-wilson-zac01", "00-0035235", "00-0037838", "00-0037836"],
  // Row 2: 4,000+ Pass Yds
  "r2_c0": ["00-0029604", "p-culpepper-dau01", "p-favre-bre01", "p-moon-war01"],
  "r2_c1": ["p-manning-pey01", "p-brady-tom01", "p-favre-bre01", "p-brees-dre01", "p-marino-dan01", "p-warner-kur01", "p-moon-war01", "p-fouts-dan01"],
  "r2_c2": [
    "00-0033873", "p-manning-pey01", "00-0023459", "p-stafford-mat01", "00-0034857",
    "p-manning-eli01", "p-rivers-phi01", "p-palmer-car01", "00-0033106", "00-0034844",
    "00-0036442", "00-0036971", "00-0039163", "00-0036264"
  ],
};

export const GridBoard: React.FC<GridBoardProps> = ({ puzzleId, rows, columns }) => {
  const [selectedCell, setSelectedCell] = useState<{ r: number; c: number } | null>(null);
  const [guessesRemaining, setGuessesRemaining] = useState(9);
  const [cells, setCells] = useState<Record<string, {
    player_id: string;
    player_name: string;
    is_correct: boolean;
    rarity_score: number;
  } | null>>({});
  const [usedPlayerIds, setUsedPlayerIds] = useState<string[]>([]);
  const [lastValidation, setLastValidation] = useState<GridValidateResponse | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);

  const handleRestart = () => {
    if (!confirmRestart) {
      setConfirmRestart(true);
      return;
    }
    // Reset in-memory state
    const emptyCells = {
      r0_c0: null, r0_c1: null, r0_c2: null,
      r1_c0: null, r1_c1: null, r1_c2: null,
      r2_c0: null, r2_c1: null, r2_c2: null,
    };
    setGuessesRemaining(9);
    setCells(emptyCells);
    setUsedPlayerIds([]);
    setLastValidation(null);
    setSelectedCell(null);
    setConfirmRestart(false);
    // Reset localStorage
    const state = GameStateManager.loadState();
    state.games.grid.guesses_remaining = 9;
    state.games.grid.cells = emptyCells;
    state.games.grid.used_player_ids = [];
    state.games.grid.is_completed = false;
    GameStateManager.saveState(state);
  };



  // Load from local storage
  useEffect(() => {
    const state = GameStateManager.loadState();
    if (state.games.grid.puzzle_id === puzzleId) {
      setGuessesRemaining(state.games.grid.guesses_remaining);
      setCells(state.games.grid.cells);
      setUsedPlayerIds(state.games.grid.used_player_ids);
    } else {
      // Initialize with new puzzle
      state.games.grid.puzzle_id = puzzleId;
      state.games.grid.guesses_remaining = 9;
      state.games.grid.cells = {
        r0_c0: null, r0_c1: null, r0_c2: null,
        r1_c0: null, r1_c1: null, r1_c2: null,
        r2_c0: null, r2_c1: null, r2_c2: null,
      };
      state.games.grid.used_player_ids = [];
      state.games.grid.is_completed = false;
      GameStateManager.saveState(state);
      setGuessesRemaining(9);
      setCells(state.games.grid.cells);
      setUsedPlayerIds([]);
    }
  }, [puzzleId]);

  const handleCellClick = (r: number, c: number) => {
    const cellKey = `r${r}_c${c}`;
    if (cells[cellKey] || guessesRemaining <= 0) return;
    setSelectedCell({ r, c });
    setLastValidation(null);
  };

  const handleSelectPlayer = async (player: SearchPlayerItem) => {
    if (!selectedCell || guessesRemaining <= 0) return;

    if (usedPlayerIds.includes(player.id)) {
      setLastValidation({
        is_valid: false,
        row_index: selectedCell.r,
        col_index: selectedCell.c,
        reason: `${player.name} has already been used in this grid!`,
      });
      return;
    }

    setIsValidating(true);
    let data: GridValidateResponse | null = null;
    const cellKey = `r${selectedCell.r}_c${selectedCell.c}`;

    try {
      const res = await fetch("/api/v1/grid/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          puzzle_id: puzzleId,
          row_index: selectedCell.r,
          col_index: selectedCell.c,
          player_id: player.id,
        }),
      });

      if (res.ok) {
        data = await res.json();
      }
    } catch (err) {
      // Backend offline: fallback to client validation
    }

    // Offline / Demo validation fallback
    if (!data) {
      const validAnswers = DEMO_CELL_ANSWERS[cellKey] || [];
      const isValid = validAnswers.includes(player.id);
      data = {
        is_valid: isValid,
        row_index: selectedCell.r,
        col_index: selectedCell.c,
        player: {
          player_id: player.id,
          full_name: player.name,
          position: player.position,
        },
        rarity_score: isValid ? Math.floor(Math.random() * 40) + 10 : null,
        reason: isValid ? null : `${player.name} does not satisfy both criteria for this cell.`,
      };
    }

    setLastValidation(data);

    const nextRemaining = guessesRemaining - 1;
    setGuessesRemaining(nextRemaining);

    const nextCells = { ...cells };
    const nextUsed = [...usedPlayerIds, player.id];

    if (data.is_valid) {
      nextCells[cellKey] = {
        player_id: player.id,
        player_name: player.name,
        is_correct: true,
        rarity_score: data.rarity_score || 35.0,
      };
      setCells(nextCells);
      setUsedPlayerIds(nextUsed);
    }

    // Check completion condition
    const solvedCount = Object.values(nextCells).filter((c) => c !== null).length;
    const isComplete = solvedCount === 9 || nextRemaining <= 0;

    if (isComplete && solvedCount === 9) {
      GameStateManager.updateStreak("grid", true);
    } else if (nextRemaining <= 0 && solvedCount < 9) {
      GameStateManager.updateStreak("grid", false);
    }

    // Update local storage
    const state = GameStateManager.loadState();
    state.games.grid.guesses_remaining = nextRemaining;
    state.games.grid.cells = nextCells;
    state.games.grid.used_player_ids = nextUsed;
    state.games.grid.is_completed = isComplete;
    GameStateManager.saveState(state);

    setIsValidating(false);
    setSelectedCell(null);
  };

  const solvedCount = Object.values(cells).filter((c) => c !== null).length;
  const totalRarity = Object.values(cells)
    .filter((c) => c !== null)
    .reduce((acc, curr) => acc + (curr?.rarity_score || 0), 0);

  return (
    <div className="w-full max-w-2xl mx-auto flex flex-col items-center">
      {/* Top status bar */}
      <div className="w-full flex items-center justify-between mb-4 px-2">
        <div className="flex items-center space-x-2">
          <span className="text-xs uppercase tracking-wider text-gray-400">Guesses Left:</span>
          <span className={`text-lg font-black ${guessesRemaining <= 2 ? "text-rose-500" : "text-white"}`}>
            {guessesRemaining} / 9
          </span>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-xs text-gray-400">
            Solved: <span className="font-bold text-white">{solvedCount}/9</span>
          </div>
          {solvedCount > 0 && (
            <div className="text-xs text-gray-400">
              Rarity: <span className="font-bold text-amber-400">{totalRarity.toFixed(1)}</span>
            </div>
          )}
        </div>
      </div>

      {/* Validation alert banner */}
      {lastValidation && !lastValidation.is_valid && (
        <div className="w-full mb-4 p-3 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center space-x-2 animate-in fade-in duration-200">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{lastValidation.reason || "Incorrect player for this intersection."}</span>
        </div>
      )}

      {/* 3x3 Matrix Grid Container */}
      <div className="grid grid-cols-4 gap-2 sm:gap-3 w-full select-none">
        {/* Top-Left Empty / Shield Corner */}
        <div className="aspect-square rounded-xl bg-surface/50 border border-border flex items-center justify-center p-2.5 sm:p-3">
          <img
            src="https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png"
            alt="NFL"
            className="w-full h-full object-contain opacity-70"
          />
        </div>

        {/* Column Headers (Top) */}
        {columns.map((col, cIdx) => (
          <div
            key={col.criterion_id || cIdx}
            className="aspect-square rounded-xl bg-surface border border-border flex items-center justify-center overflow-hidden group shadow-sm"
          >
            <CriterionHeaderCell criterion={col} />
          </div>
        ))}

        {/* Rows & Cells */}
        {rows.map((row, rIdx) => (
          <React.Fragment key={row.criterion_id || rIdx}>
            {/* Row Header (Left) */}
            <div className="aspect-square rounded-xl bg-surface border border-border flex items-center justify-center overflow-hidden group shadow-sm">
              <CriterionHeaderCell criterion={row} />
            </div>

            {/* 3 Cells in this row */}
            {[0, 1, 2].map((cIdx) => {
              const cellKey = `r${rIdx}_c${cIdx}`;
              const cellData = cells[cellKey];
              const isFilled = Boolean(cellData);

              return (
                <button
                  key={cellKey}
                  disabled={isFilled || guessesRemaining <= 0 || isValidating}
                  onClick={() => handleCellClick(rIdx, cIdx)}
                  className={`aspect-square rounded-xl border p-1.5 sm:p-2.5 flex flex-col items-center justify-center text-center transition-all duration-150 relative overflow-hidden group ${
                    isFilled
                      ? "bg-emerald-950/40 border-emerald-500/50 shadow-inner text-white"
                      : guessesRemaining <= 0
                      ? "bg-surface/20 border-border/40 text-gray-600 cursor-not-allowed"
                      : "bg-surface border-border hover:border-nfl-blue hover:bg-surface-raised cursor-pointer hover:shadow-md"
                  }`}
                >
                  {isFilled ? (
                    <>
                      <div className="text-[11px] sm:text-xs md:text-sm font-bold text-white line-clamp-2 leading-tight px-0.5">
                        {cellData?.player_name}
                      </div>
                      <div className="text-[9px] sm:text-[10px] md:text-xs font-semibold text-emerald-400 mt-1 flex items-center space-x-0.5 sm:space-x-1 bg-emerald-900/50 border border-emerald-500/30 px-1.5 py-0.5 rounded-full">
                        <CheckCircle2 className="h-2.5 w-2.5 sm:h-3 sm:w-3 shrink-0" />
                        <span>{cellData?.rarity_score}%</span>
                      </div>
                    </>
                  ) : (
                    <span className="text-xl sm:text-2xl text-gray-500 font-light group-hover:text-blue-400 transition-colors">
                      +
                    </span>
                  )}
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </div>

      {/* Game Over / Summary Card */}
      {(guessesRemaining <= 0 || solvedCount === 9) && (
        <div className="w-full mt-6 p-4 rounded-xl bg-surface border border-border text-center animate-in fade-in duration-300">
          <h3 className="text-lg font-bold text-white">
            {solvedCount === 9 ? "🏆 Immaculate! Grid Complete!" : "Game Over"}
          </h3>
          <p className="text-xs text-gray-400 mt-1">
            You solved {solvedCount} of 9 cells. Total Rarity Score:{" "}
            <span className="font-bold text-amber-400">{totalRarity.toFixed(1)}</span>
          </p>
          <div className="mt-3 flex items-center justify-center gap-2">
            {confirmRestart ? (
              <>
                <button
                  onClick={handleRestart}
                  className="px-4 py-1.5 rounded-full bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-colors"
                >
                  Yes, restart
                </button>
                <button
                  onClick={() => setConfirmRestart(false)}
                  className="px-4 py-1.5 rounded-full border border-border bg-surface hover:bg-surface-raised text-gray-300 text-xs transition-colors"
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={handleRestart}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-full border border-border bg-surface hover:bg-surface-raised text-gray-300 text-xs font-medium transition-colors"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Restart
              </button>
            )}
          </div>
        </div>
      )}


      {/* Search Modal */}
      <PlayerSearchModal
        isOpen={selectedCell !== null}
        onClose={() => setSelectedCell(null)}
        onSelectPlayer={handleSelectPlayer}
        title={
          selectedCell
            ? `Row: ${rows[selectedCell.r]?.display_title} ✕ Col: ${columns[selectedCell.c]?.display_title}`
            : "Select Player"
        }
      />
    </div>
  );
};
