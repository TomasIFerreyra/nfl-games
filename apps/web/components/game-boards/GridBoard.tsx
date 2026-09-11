"use client";

import React, { useState, useEffect, useCallback } from "react";
import { GridCriterion, GridPuzzleSummaryResponse, GridValidateResponse } from "@nfl-games/contracts";
import { PlayerSearchModal } from "@/components/PlayerSearchModal";
import { SearchPlayerItem } from "@/lib/search/playerSearch";
import { GameStateManager } from "@/lib/storage/gameState";
import { CheckCircle2, AlertCircle, RotateCcw, Flag, Eye, Loader2 } from "lucide-react";
import { getTeamLogoUrl } from "@/lib/teamLogos";
import { PlayerTile } from "@/components/PlayerTile";

export interface GridCellItem {
  player_id: string;
  player_name: string;
  position?: string | null;
  headshot_url?: string | null;
  is_correct: boolean;
  rarity_score?: number | null;
  is_revealed_missed?: boolean;
  pick_percentage?: number | null;
}

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

// Comprehensive set of 1st-Round Draft Picks across history + 2024, 2025, and 2026 draft classes
const ROUND_1_DRAFT_PICKS = new Set([
  // 2026 Draft Class top & projected 1st rounders
  "arch manning", "nico iamaleava", "jeremiah smith", "ryan williams", "dylan stewart",
  "jordan seaton", "colin simmons", "ellis robinson iv", "ellis robinson", "garrett nussmeier",
  "conner weigman", "zachariah branch", "caleb downs", "eugene wilson iii", "eugene wilson",
  "peter woods", "francis mauigoa", "kadyn proctor", "rueben owens", "justice haynes",
  "nyck harbor", "dj lagway", "anthony hill jr", "carnell tate", "tj shanahan",
  "samson okunlola", "suntarine perkins", "peyton bowen", "adepoju adebawore", "damon wilson jr",
  "jordan hall", "daevin hobbs", "taurean york", "tony mitchell", "malik muhammad",
  "cormani mcclain", "jaylen mbakwe", "kj bolden", "sammy brown", "terry bussey",

  // 2025 Draft Class 1st rounders & top prospects
  "cam ward", "travis hunter", "shedeur sanders", "abdul carter", "ashton jeanty",
  "tetairoa mcmillan", "mason graham", "will campbell", "malaki starks", "kelvin banks jr",
  "kelvin banks", "james pearce jr", "james pearce", "tyler booker", "luther burden iii",
  "luther burden", "colston loveland", "mykel williams", "shavon revel jr", "shavon revel",
  "jalon walker", "kenneth grant", "nic scourton", "jalen milroe", "quinn ewers",
  "jaxson dart", "emeka egbuka", "isaiah bond", "treveyon henderson", "quinshon judkins",
  "jonah savaiinaea", "josh simmons", "benjamin morrison", "will johnson", "jack sawyer",
  "derrick harmon", "walter nolen", "jihaad campbell", "carson beck", "tyler warren",
  "aireontae ersery", "wyatt milum", "josh conerly jr", "josh conerly", "grey zabel",
  "matthew golden", "tre harris", "xavier restrepo", "jayden higgins", "omarion hampton",
  "kaleb johnson", "nicholas singleton", "princely umanmielen", "landon jackson", "mike green",
  "donovan ezeiruaku", "tj sanders", "t.j. sanders", "deone walker", "jahdae barron",
  "maxwell hairston", "tacario davis", "trey amos", "xavier watts", "andrew mukuba",
  "nick emmanwori", "kevin winston jr", "kevin winston", "lathan ransom", "cam skattebo",
  "harold fannin jr", "kyle monangai", "armand membou",

  // 2024 Draft Class 1st rounders
  "caleb williams", "jayden daniels", "drake maye", "marvin harrison jr", "marvin harrison",
  "joe alt", "malik nabers", "jc latham", "michael penix jr", "michael penix",
  "rome odunze", "jj mccarthy", "j.j. mccarthy", "olu fashanu", "olumuyiwa fashanu",
  "bo nix", "brock bowers", "taliese fuaga", "laiatu latu", "byron murphy ii",
  "dallas turner", "amarius mims", "jared verse", "troy fautanu", "chop robinson",
  "quinyon mitchell", "brian thomas jr", "terrion arnold", "jordan morgan", "graham barton",
  "darius robinson", "xavier worthy", "tyler guyton", "nate wiggins", "ricky pearsall",
  "xavier legette",

  // Active & Historical 1st round picks
  "patrick mahomes", "aaron rodgers", "peyton manning", "eli manning", "dan marino",
  "john elway", "jim kelly", "terry bradshaw", "troy aikman", "cam newton",
  "matthew stafford", "joe burrow", "josh allen", "lamar jackson", "justin herbert",
  "trevor lawrence", "jordan love", "baker mayfield", "kyler murray", "tua tagovailoa",
  "jared goff", "cj stroud", "c.j. stroud", "carson palmer", "donovan mcnabb",
  "drew bledsoe", "joe flacco", "jay cutler", "sam darnold", "mark sanchez",
  "zach wilson", "michael vick", "daunte culpepper", "alex smith", "matt ryan",
  "philip rivers", "ben roethlisberger", "emmitt smith", "barry sanders", "walter payton",
  "adrian peterson", "christian mccaffrey", "ladainian tomlinson", "eric dickerson",
  "oj simpson", "o.j. simpson", "earl campbell", "marshall faulk", "jerome bettis",
  "tony dorsett", "marcus allen", "john riggins", "franco harris", "gale sayers",
  "marshawn lynch", "saquon barkley", "bijan robinson", "jahmyr gibbs", "shaun alexander",
  "edgerrin james", "jerry rice", "randy moss", "larry fitzgerald", "calvin johnson",
  "tim brown", "reggie wayne", "torry holt", "michael irvin", "james lofton",
  "julio jones", "deandre hopkins", "justin jefferson", "jamarr chase", "ja'marr chase",
  "ceedee lamb", "mike evans", "dj moore", "d.j. moore", "garrett wilson", "chris olave",
  "tony gonzalez", "greg olsen", "tj hockenson", "t.j. hockenson", "kyle pitts",
  "reggie white", "bruce smith", "lawrence taylor", "jj watt", "j.j. watt",
  "tj watt", "t.j. watt", "aaron donald", "von miller", "myles garrett",
  "nick bosa", "joey bosa", "micah parsons", "derrick thomas", "dwight freeney",
  "clay matthews", "julius peppers", "demarcus ware", "ndamukong suh", "quinnen williams",
  "ray lewis", "brian urlacher", "dick butkus", "junior seau", "luke kuechly",
  "patrick willis", "derrick brooks", "roquan smith", "deion sanders", "charles woodson",
  "rod woodson", "ed reed", "troy polamalu", "ronnie lott", "darrelle revis",
  "champ bailey", "steve atwater", "earl thomas", "patrick peterson", "jalen ramsey",
  "patrick surtain ii", "sauce gardner", "minkah fitzpatrick", "derwin james", "kyle hamilton",
  "kenny clark", "jaire alexander", "quay walker", "devonte wyatt", "rashan gary",
  "eric stokes", "darnell savage", "ha ha clinton-dix", "nick perry", "justin harrell",
  "aj hawk", "a.j. hawk", "jamal reynolds", "bubba franks", "antuan edwards",
  "vonnie holliday", "ross verba", "john michels", "craig newsome", "aaron taylor",
  "wayne simmons", "terrell buckley", "tony mandarich", "sterling sharpe",
  "will mcdonald iv", "jermaine johnson", "alijah vera-tucker", "mekhi becton",
  "jamal adams", "darron lee", "leonard williams", "calvin pryor", "dee milliner",
  "sheldon richardson", "quinton coples", "muhammad wilkerson", "kyle wilson",
  "dustin keller", "d'brickashaw ferguson", "nick mangold", "jonathan vilma",
  "bryan thomas", "santana moss", "chad pennington", "john abraham", "shaun ellis",
  "keyshawn johnson", "joe namath", "anthony richardson", "will levis", "mac jones",
  "justin fields", "trey lance", "dwayne haskins", "daniel jones", "josh rosen",
  "mitchell trubisky", "deshaun watson", "paxton lynch", "jameis winston", "marcus mariota",
  "blake bortles", "johnny manziel", "teddy bridgewater", "ej manuel", "andrew luck",
  "robert griffin iii", "ryan tannehill", "brandon weeden", "jake locker", "blaine gabbert",
  "christian ponder", "sam bradford", "tim tebow", "josh freeman", "jamarcus russell",
  "brady quinn", "vince young", "matt leinart", "jason campbell", "jp losman",
  "byron leftwich", "kyle boller", "rex grossman", "david carr", "joey harrington",
  "patrick ramsey", "tim couch", "akili smith", "cade mcnown", "ryan leaf",
  "jim druckenmiller", "kerry collins", "steve mcnair", "heath shuler", "trent dilfer",
  "rick mirer", "david klingler", "tommy maddox", "dan mcguire", "todd marinovich",
  "jeff george", "andre ware", "vinny testaverde", "kelly stouffer", "chris miller",
  "jim everett", "chuck long", "bernie kosar", "todd blackledge", "tony eason",
  "ken obrien", "art schlichter", "jim mcmahon", "rich campbell",
]);

const PASSING_4000_YARD_PLAYERS = new Set([
  "patrick mahomes", "peyton manning", "eli manning", "aaron rodgers", "matthew stafford",
  "josh allen", "philip rivers", "carson palmer", "jared goff", "baker mayfield",
  "joe burrow", "trevor lawrence", "cj stroud", "c.j. stroud", "jordan love",
  "cam newton", "daunte culpepper", "carson wentz", "alex smith", "vinny testaverde",
  "drew bledsoe", "michael vick", "jay cutler", "sam darnold", "kirk cousins",
  "tom brady", "drew brees", "dan marino", "kurt warner", "warren moon",
  "dan fouts", "matt ryan", "ben roethlisberger", "justin herbert", "dak prescott",
  "brock purdy", "caleb williams", "jayden daniels", "drake maye", "cam ward",
  "shedeur sanders", "arch manning", "tua tagovailoa", "deshaun watson", "ryan tannehill",
  "jameis winston", "andrew luck", "tony romo", "matt schaub", "marc bulger",
  "trent green", "jeff garcia", "rich gannon", "steve beuerlein", "brad johnson",
  "neil lomax", "bill kenney", "lynn dickey", "brian sipe", "joe namath",
]);

const HALL_OF_FAME_PLAYERS = new Set([
  "brett favre", "bart starr", "reggie white", "james lofton", "charles woodson",
  "leroy butler", "joe namath", "curtis martin", "darrelle revis", "ronnie lott",
  "ed reed", "peyton manning", "tom brady", "drew brees", "dan marino",
  "kurt warner", "warren moon", "dan fouts", "steve young", "joe montana",
  "john elway", "troy aikman", "roger staubach", "terry bradshaw", "fran tarkenton",
  "emmitt smith", "barry sanders", "walter payton", "eric dickerson", "jim brown",
  "oj simpson", "o.j. simpson", "earl campbell", "marshall faulk", "jerome bettis",
  "tony dorsett", "marcus allen", "john riggins", "franco harris", "gale sayers",
  "jerry rice", "randy moss", "terrell owens", "cris carter", "calvin johnson",
  "tim brown", "michael irvin", "steve largent", "andre reed", "tony gonzalez",
  "shannon sharpe", "ozzie newsome", "mike ditka", "bruce smith", "michael strahan",
  "lawrence taylor", "derrick thomas", "dwight freeney", "julius peppers", "demarcus ware",
  "ray lewis", "brian urlacher", "mike singletary", "dick butkus", "jack lambert",
  "junior seau", "derrick brooks", "patrick willis", "deion sanders", "rod woodson",
  "troy polamalu", "champ bailey", "brian dawkins", "steve atwater", "john lynch",
]);

const PLAYER_FRANCHISE_MAP: Record<string, string[]> = {
  "aaron rodgers": ["GNB", "NYJ"],
  "brett favre": ["ATL", "GNB", "NYJ", "MIN"],
  "jordan love": ["GNB"],
  "clay matthews": ["GNB", "LAR"],
  "kenny clark": ["GNB"],
  "jaire alexander": ["GNB"],
  "quay walker": ["GNB"],
  "jordan morgan": ["GNB"],
  "devonte wyatt": ["GNB"],
  "rashan gary": ["GNB"],
  "bart starr": ["GNB"],
  "reggie white": ["PHI", "GNB", "CAR"],
  "james lofton": ["GNB", "LVR", "BUF", "LAR", "PHI"],
  "charles woodson": ["LVR", "GNB"],
  "leroy butler": ["GNB"],
  "greg jennings": ["GNB", "MIN", "MIA"],
  "ryan longwell": ["GNB", "MIN"],
  "zarius smith": ["BAL", "GNB", "MIN", "CLE", "DET"],
  "zadarius smith": ["BAL", "GNB", "MIN", "CLE", "DET"],
  "darren sharper": ["GNB", "MIN", "NOR"],
  "davante adams": ["GNB", "LVR", "NYJ"],
  "aaron jones": ["GNB", "MIN"],
  "sam darnold": ["NYJ", "CAR", "SFO", "MIN"],
  "joe namath": ["NYJ", "LAR"],
  "curtis martin": ["NE", "NYJ"],
  "darrelle revis": ["NYJ", "TAM", "NE", "KC"],
  "ronnie lott": ["SFO", "LVR", "NYJ"],
  "ed reed": ["BAL", "HOU", "NYJ"],
  "mark sanchez": ["NYJ", "PHI", "DAL", "WAS"],
  "zach wilson": ["NYJ", "DEN"],
  "quinnen williams": ["NYJ"],
  "sauce gardner": ["NYJ"],
  "garrett wilson": ["NYJ"],
  "breece hall": ["NYJ"],
  "olu fashanu": ["NYJ"],
  "alijah vera tucker": ["NYJ"],
  "ryan fitzpatrick": ["LAR", "CIN", "BUF", "TEN", "HOU", "NYJ", "TAM", "MIA", "WAS"],
  "dalvin cook": ["MIN", "NYJ", "BAL", "DAL"],
  "kirk cousins": ["WAS", "MIN", "ATL"],
  "daunte culpepper": ["MIN", "MIA", "LVR", "DET"],
  "warren moon": ["TEN", "MIN", "SEA", "KC"],
  "randy moss": ["MIN", "LVR", "NE", "TEN", "SFO"],
  "cris carter": ["PHI", "MIN", "MIA"],
  "adrian peterson": ["MIN", "ARI", "NOR", "WAS", "DET", "TEN", "SEA"],
  "justin jefferson": ["MIN"],
  "jj mccarthy": ["MIN"],
  "j.j. mccarthy": ["MIN"],
  "dallas turner": ["MIN"],
  "caleb williams": ["CHI"],
  "jayden daniels": ["WAS"],
  "drake maye": ["NE"],
  "marvin harrison jr": ["ARI"],
  "joe alt": ["LAC"],
  "malik nabers": ["NYG"],
  "jc latham": ["TEN"],
  "michael penix jr": ["ATL"],
  "rome odunze": ["CHI"],
  "bo nix": ["DEN"],
  "brock bowers": ["LVR"],
  "taliese fuaga": ["NOR"],
  "laiatu latu": ["IND"],
  "byron murphy ii": ["SEA"],
  "amarius mims": ["CIN"],
  "jared verse": ["LAR"],
  "troy fautanu": ["PIT"],
  "chop robinson": ["MIA"],
  "quinyon mitchell": ["PHI"],
  "brian thomas jr": ["JAX"],
  "terrion arnold": ["DET"],
  "graham barton": ["TAM"],
  "darius robinson": ["ARI"],
  "xavier worthy": ["KC"],
  "tyler guyton": ["DAL"],
  "nate wiggins": ["BAL"],
  "ricky pearsall": ["SFO"],
  "xavier legette": ["CAR"],
  "terrell owens": ["SFO", "PHI", "DAL", "BUF", "CIN"],
  "jerry rice": ["SFO", "LVR", "SEA"],
  "patrick mahomes": ["KC"],
  "tom brady": ["NE", "TAM"],
  "drew brees": ["LAC", "NOR"],
  "peyton manning": ["IND", "DEN"],
  "eli manning": ["NYG"],
  "matthew stafford": ["DET", "LAR"],
  "josh allen": ["BUF"],
  "lamar jackson": ["BAL"],
  "joe burrow": ["CIN"],
  "cj stroud": ["HOU"],
  "c.j. stroud": ["HOU"],
  "trevor lawrence": ["JAX"],
  "justin herbert": ["LAC"],
  "jalen hurts": ["PHI"],
  "baker mayfield": ["CLE", "CAR", "LAR", "TAM"],
  "kyler murray": ["ARI"],
  "tua tagovailoa": ["MIA"],
  "jared goff": ["LAR", "DET"],
  "brock purdy": ["SFO"],
  "dak prescott": ["DAL"],
  "travis hunter": ["COL"],
  "cam ward": ["MIA"],
  "shedeur sanders": ["COL"],
  "abdul carter": ["PSU"],
  "ashton jeanty": ["BSU"],
  "arch manning": ["TEX"],
  "nico iamaleava": ["TEN"],
  "jeremiah smith": ["OSU"],
  "ryan williams": ["ALA"],
};

function isPlayerValidForCriterion(player: SearchPlayerItem, criterion: GridCriterion): boolean {
  const cType = criterion.type;
  const cId = criterion.criterion_id || "";
  const params = (criterion.parameters || {}) as Record<string, unknown>;
  const cleanName = player.name.toLowerCase().trim();
  const normalizedName = cleanName.replace(/[\.\-]/g, " ").replace(/\s+/g, " ");
  const cleanId = player.id.toLowerCase().trim();

  // 1. DRAFT ROUND (e.g. 1st Round Pick)
  if (cType === "DRAFT_ROUND" || cId.includes("DRAFT_RD1") || cId.includes("DRAFT")) {
    const round = (params.round as number) || 1;
    if (round === 1) {
      return (
        ROUND_1_DRAFT_PICKS.has(cleanName) ||
        ROUND_1_DRAFT_PICKS.has(normalizedName) ||
        ROUND_1_DRAFT_PICKS.has(cleanId) ||
        cleanId.startsWith("draft2024-") ||
        cleanId.startsWith("draft2025-") ||
        cleanId.startsWith("draft2026-")
      );
    }
  }

  // 2. FRANCHISE
  if (cType === "FRANCHISE" || cId.startsWith("FRAN_")) {
    const franId = ((params.franchise_id as string) || cId.replace("FRAN_", "")).toUpperCase();
    const franchises =
      PLAYER_FRANCHISE_MAP[cleanName] ||
      PLAYER_FRANCHISE_MAP[normalizedName] ||
      PLAYER_FRANCHISE_MAP[cleanId] ||
      [];
    return franchises.includes(franId);
  }

  // 3. STAT SEASON (e.g. 4,000+ pass yds)
  if (cType === "STAT_SEASON" || cId.includes("STAT_PASS_4000") || cId.includes("PASS_4000")) {
    return (
      PASSING_4000_YARD_PLAYERS.has(cleanName) ||
      PASSING_4000_YARD_PLAYERS.has(normalizedName) ||
      PASSING_4000_YARD_PLAYERS.has(cleanId)
    );
  }

  // 4. ACCOLADE (e.g. Hall of Fame)
  if (cType === "ACCOLADE" || cId.includes("ACCOLADE_HOF") || cId.includes("HOF")) {
    return (
      HALL_OF_FAME_PLAYERS.has(cleanName) ||
      HALL_OF_FAME_PLAYERS.has(normalizedName) ||
      HALL_OF_FAME_PLAYERS.has(cleanId)
    );
  }

  return false;
}

// Fallback seed dictionary for historical matrix combinations
const DEMO_CELL_ANSWERS: Record<string, string[]> = {
  // Row 0: Packers
  "r0_c0": ["p-favre-bre01", "p-jennings-gre01", "p-longwell-rya01", "p-smith-zad01", "p-sharper-dar01", "00-0033293"],
  "r0_c1": ["p-favre-bre01", "p-starr-bar01", "p-white-reg01", "p-lofton-jam01", "p-woodson-cha01", "p-butler-ler01"],
  "r0_c2": [
    "00-0023459", "00-0036264", "p-matthews-cla01", "p-clark-ken01", "p-alexander-jai01", "p-walker-qua01",
    "draft2024-morgan-jor01", "p-favre-bre01", "p-starr-bar01", "p-lofton-jam01", "p-woodson-cha01"
  ],
  // Row 1: Jets
  "r1_c0": ["p-favre-bre01", "p-darnold-sam01", "p-fitzpatrick-rya01", "00-0033897"],
  "r1_c1": ["p-namath-joe01", "p-martin-cur01", "p-revis-dar01", "p-favre-bre01", "p-lott-ron01", "p-reed-ed01"],
  "r1_c2": [
    "p-namath-joe01", "p-revis-dar01", "p-sanchez-mar01", "p-darnold-sam01", "p-wilson-zac01",
    "00-0035235", "00-0037838", "00-0037836", "draft2024-fashanu-olu01", "00-0023459"
  ],
  // Row 2: 4,000+ Pass Yds
  "r2_c0": ["00-0029604", "p-culpepper-dau01", "p-favre-bre01", "p-moon-war01", "p-darnold-sam01"],
  "r2_c1": [
    "p-manning-pey01", "p-brady-tom01", "p-favre-bre01", "p-brees-dre01", "p-marino-dan01",
    "p-warner-kur01", "p-moon-war01", "p-fouts-dan01", "p-namath-joe01"
  ],
  "r2_c2": [
    "00-0033873", "p-manning-pey01", "00-0023459", "p-stafford-mat01", "00-0034857",
    "p-manning-eli01", "p-rivers-phi01", "p-palmer-car01", "00-0033106", "00-0034844",
    "00-0036442", "00-0036971", "00-0039163", "00-0036264", "draft2024-williams-cal01",
    "draft2024-daniels-jay01", "draft2024-maye-dra01", "draft2024-nix-bo01",
    "draft2025-ward-cam01", "draft2025-sanders-she01", "draft2026-manning-arc01"
  ],
};

export const GridBoard: React.FC<GridBoardProps> = ({ puzzleId, rows, columns }) => {
  const [selectedCell, setSelectedCell] = useState<{ r: number; c: number } | null>(null);
  const [guessesRemaining, setGuessesRemaining] = useState(9);
  const [cells, setCells] = useState<Record<string, GridCellItem | null>>({});
  const [usedPlayerIds, setUsedPlayerIds] = useState<string[]>([]);
  const [lastValidation, setLastValidation] = useState<GridValidateResponse | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isRevealing, setIsRevealing] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [confirmSurrender, setConfirmSurrender] = useState(false);

  const revealMissedAnswers = useCallback(
    async (
      currentCells: Record<string, GridCellItem | null>,
      remainingGuesses: number,
      currentUsed: string[]
    ) => {
      setIsRevealing(true);
      let summaryData: GridPuzzleSummaryResponse | null = null;

      try {
        const res = await fetch(`/api/v1/grid/puzzles/${puzzleId}/summary`);
        if (res.ok) {
          summaryData = await res.json();
        }
      } catch (err) {
        console.warn("Failed to fetch grid puzzle summary from backend:", err);
      }

      const updatedCells: Record<string, GridCellItem | null> = { ...currentCells };

      for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 3; c++) {
          const cellKey = `r${r}_c${c}`;
          const coordKey = `${r}_${c}`;

          // Only populate cells that are not correctly solved by the user
          if (!updatedCells[cellKey] || !updatedCells[cellKey]?.is_correct) {
            const sol =
              summaryData?.cell_solutions?.[coordKey] || summaryData?.cell_solutions?.[cellKey];

            if (sol) {
              updatedCells[cellKey] = {
                player_id: sol.player_id,
                player_name: sol.full_name,
                position: sol.position || null,
                headshot_url: sol.headshot_url || null,
                is_correct: false,
                is_revealed_missed: true,
                pick_percentage: sol.pick_percentage ?? null,
                rarity_score: null,
              };
            } else {
              // Resilient offline / demo fallback answer
              const fallbackPlayerId = DEMO_CELL_ANSWERS[cellKey]?.[0] || `demo-player-${r}-${c}`;
              const cleanFallbackName = fallbackPlayerId
                .replace("p-", "")
                .replace("-", " ")
                .replace(/\d+/g, "")
                .trim()
                .split(" ")
                .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                .join(" ");

              updatedCells[cellKey] = {
                player_id: fallbackPlayerId,
                player_name: cleanFallbackName || "Top Pick",
                position: null,
                headshot_url: null,
                is_correct: false,
                is_revealed_missed: true,
                pick_percentage: null,
                rarity_score: null,
              };
            }
          }
        }
      }

      setCells(updatedCells);
      setIsRevealing(false);

      // Persist revealed state to localStorage so page refresh retains solved grid view
      const state = GameStateManager.loadState();
      state.games.grid.guesses_remaining = remainingGuesses;
      state.games.grid.cells = updatedCells;
      state.games.grid.used_player_ids = currentUsed;
      state.games.grid.is_completed = true;
      GameStateManager.saveState(state);
    },
    [puzzleId]
  );

  const handleRestart = () => {
    if (!confirmRestart) {
      setConfirmRestart(true);
      return;
    }
    // Reset in-memory state
    const emptyCells: Record<string, GridCellItem | null> = {
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
    setConfirmSurrender(false);
    // Reset localStorage
    const state = GameStateManager.loadState();
    state.games.grid.guesses_remaining = 9;
    state.games.grid.cells = emptyCells;
    state.games.grid.used_player_ids = [];
    state.games.grid.is_completed = false;
    state.games.grid.is_surrendered = false;
    GameStateManager.saveState(state);
  };

  const handleSurrender = async () => {
    if (!confirmSurrender) {
      setConfirmSurrender(true);
      return;
    }
    setConfirmSurrender(false);
    setGuessesRemaining(0);
    GameStateManager.updateStreak("grid", false);
    await revealMissedAnswers(cells, 0, usedPlayerIds);
  };

  // Load from local storage
  useEffect(() => {
    const state = GameStateManager.loadState();
    if (state.games.grid.puzzle_id === puzzleId) {
      setGuessesRemaining(state.games.grid.guesses_remaining);
      setCells(state.games.grid.cells as Record<string, GridCellItem | null>);
      setUsedPlayerIds(state.games.grid.used_player_ids);

      // If already completed and has unfilled slots, ensure answers are revealed
      if (state.games.grid.is_completed && state.games.grid.guesses_remaining === 0) {
        const hasUnrevealed = Object.values(state.games.grid.cells).some((c) => c === null);
        if (hasUnrevealed) {
          revealMissedAnswers(
            state.games.grid.cells as Record<string, GridCellItem | null>,
            0,
            state.games.grid.used_player_ids
          );
        }
      }
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
      state.games.grid.is_surrendered = false;
      GameStateManager.saveState(state);
      setGuessesRemaining(9);
      setCells(state.games.grid.cells as Record<string, GridCellItem | null>);
      setUsedPlayerIds([]);
    }
  }, [puzzleId, revealMissedAnswers]);

  const handleCellClick = (r: number, c: number) => {
    const cellKey = `r${r}_c${c}`;
    if (cells[cellKey] || guessesRemaining <= 0) return;
    setSelectedCell({ r, c });
    setLastValidation(null);
  };

  const handleSelectPlayer = async (player: SearchPlayerItem) => {
    if (!selectedCell || guessesRemaining <= 0) return;

    const playerNameLower = player.name.toLowerCase().trim();

    // Check if already used — match by name too in case IDs differ between DB and demo data
    const alreadyUsedById = usedPlayerIds.includes(player.id);
    const alreadyUsedByName = Object.values(cells).some(
      (c) => c !== null && c.player_name.toLowerCase().trim() === playerNameLower
    );

    if (alreadyUsedById || alreadyUsedByName) {
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

    // Offline / Demo validation fallback — dynamic rule evaluation + matrix dictionary
    if (!data) {
      const validAnswers = DEMO_CELL_ANSWERS[cellKey] || [];
      const rowCriterion = rows[selectedCell.r];
      const colCriterion = columns[selectedCell.c];

      const rowValid = rowCriterion ? isPlayerValidForCriterion(player, rowCriterion) : false;
      const colValid = colCriterion ? isPlayerValidForCriterion(player, colCriterion) : false;

      const isValid = (rowValid && colValid) || validAnswers.includes(player.id);

      data = {
        is_valid: isValid,
        row_index: selectedCell.r,
        col_index: selectedCell.c,
        player: {
          player_id: player.id,
          full_name: player.name,
          position: player.position,
        },
        rarity_score: isValid ? Math.floor(Math.random() * 35) + 8 : null,
        reason: isValid ? null : `${player.name} does not satisfy both criteria for this cell.`,
      };
    }

    setLastValidation(data);

    const nextRemaining = guessesRemaining - 1;
    setGuessesRemaining(nextRemaining);

    const nextCells: Record<string, GridCellItem | null> = { ...cells };
    const nextUsed = [...usedPlayerIds, player.id];

    if (data.is_valid) {
      nextCells[cellKey] = {
        player_id: player.id,
        player_name: player.name,
        position: player.position || data.player?.position || null,
        headshot_url: data.player?.headshot_url || null,
        is_correct: true,
        rarity_score: data.rarity_score || 35.0,
      };
      setCells(nextCells);
      setUsedPlayerIds(nextUsed);
    }

    // Check completion condition
    const solvedCount = Object.values(nextCells).filter((c) => c !== null && c.is_correct).length;
    const isComplete = solvedCount === 9 || nextRemaining <= 0;

    if (isComplete && solvedCount === 9) {
      GameStateManager.updateStreak("grid", true);
    } else if (nextRemaining <= 0 && solvedCount < 9) {
      GameStateManager.updateStreak("grid", false);
      // Auto-reveal missed cells with easiest top picks
      await revealMissedAnswers(nextCells, nextRemaining, nextUsed);
      setIsValidating(false);
      setSelectedCell(null);
      return;
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

  const solvedCount = Object.values(cells).filter((c) => c !== null && c.is_correct).length;
  const totalRarity = Object.values(cells)
    .filter((c) => c !== null && c.is_correct)
    .reduce((acc, curr) => acc + (curr?.rarity_score || 0), 0);
  const isGameOver = guessesRemaining <= 0 || solvedCount === 9;

  return (
    <div className="w-full max-w-2xl mx-auto flex flex-col items-center">
      {/* Top status bar */}
      <div className="w-full flex items-center justify-between mb-4 px-2">
        <div className="flex items-center space-x-2">
          <span className="text-xs uppercase tracking-wider text-gray-400">Guesses Left:</span>
          <span
            className={`text-lg font-black ${
              guessesRemaining <= 2 ? "text-rose-500" : "text-white"
            }`}
          >
            {guessesRemaining} / 9
          </span>
        </div>

        <div className="flex items-center space-x-3 sm:space-x-4">
          <div className="text-xs text-gray-400">
            Solved: <span className="font-bold text-white">{solvedCount}/9</span>
          </div>
          {solvedCount > 0 && (
            <div className="text-xs text-gray-400">
              Rarity: <span className="font-bold text-amber-400">{totalRarity.toFixed(1)}</span>
            </div>
          )}

          {/* Give Up / Surrender Action */}
          {!isGameOver && (
            <div className="flex items-center">
              {confirmSurrender ? (
                <div className="flex items-center space-x-1 animate-in fade-in zoom-in-95 duration-150">
                  <button
                    onClick={handleSurrender}
                    className="px-2.5 py-1 rounded-full bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-bold shadow-xs transition-colors"
                  >
                    Reveal answers?
                  </button>
                  <button
                    onClick={() => setConfirmSurrender(false)}
                    className="px-2 py-1 rounded-full border border-border bg-surface hover:bg-surface-raised text-gray-300 text-[11px] transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmSurrender(true)}
                  className="flex items-center space-x-1 px-2.5 py-1 rounded-full border border-border bg-surface hover:bg-rose-950/40 hover:border-rose-800 text-gray-400 hover:text-rose-300 text-[11px] font-medium transition-colors"
                  title="Give up and view unrevealed easiest answers"
                >
                  <Flag className="h-3 w-3 shrink-0" />
                  <span>Give Up</span>
                </button>
              )}
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

              return isFilled && cellData ? (
                <div key={cellKey} className="aspect-square w-full">
                  <PlayerTile
                    name={cellData.player_name}
                    playerId={cellData.player_id}
                    position={cellData.position}
                    headshotUrl={cellData.headshot_url}
                    rarityScore={cellData.is_correct ? cellData.rarity_score : null}
                    pickPercentage={cellData.pick_percentage}
                    isMissed={Boolean(cellData.is_revealed_missed)}
                    variant={cellData.is_revealed_missed ? "grid-missed" : "grid"}
                    disabled
                  />
                </div>
              ) : (
                <button
                  key={cellKey}
                  type="button"
                  disabled={guessesRemaining <= 0 || isValidating || isRevealing}
                  onClick={() => handleCellClick(rIdx, cIdx)}
                  className={`aspect-square w-full rounded-xl border p-1.5 sm:p-2.5 flex flex-col items-center justify-center text-center transition-all duration-200 relative overflow-hidden group ${
                    guessesRemaining <= 0
                      ? "bg-surface/20 border-border/40 text-gray-600 cursor-not-allowed"
                      : "bg-surface border-border hover:border-nfl-blue hover:bg-surface-raised cursor-pointer hover:shadow-md"
                  }`}
                >
                  <span className="text-xl sm:text-2xl text-gray-500 font-light group-hover:text-blue-400 group-hover:scale-125 transition-transform duration-200">
                    +
                  </span>
                </button>
              );
            })}
          </React.Fragment>
        ))}
      </div>

      {/* Game Over / Summary Card */}
      {isGameOver && (
        <div className="w-full mt-6 p-4 rounded-xl bg-surface border border-border text-center animate-in fade-in duration-300">
          <h3 className="text-lg font-bold text-white">
            {solvedCount === 9 ? "🏆 Immaculate! Grid Complete!" : "Game Over"}
          </h3>
          <p className="text-xs text-gray-400 mt-1">
            You solved {solvedCount} of 9 cells. Total Rarity Score:{" "}
            <span className="font-bold text-amber-400">{totalRarity.toFixed(1)}</span>
          </p>
          {solvedCount < 9 && (
            <p className="text-[11px] text-gray-400 mt-1 flex items-center justify-center gap-1.5">
              <span className="inline-block w-2.5 h-2.5 rounded-xs bg-rose-950 border border-red-500" />
              Unrevealed cells are highlighted with the top / easiest picks.
            </p>
          )}
          <div className="mt-4 flex items-center justify-center gap-2">
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
                Play Again / Restart
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
