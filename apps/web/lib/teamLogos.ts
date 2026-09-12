/**
 * NFL Team Logo utility
 * Maps NFL franchises, team abbreviations, and canonical names to ESPN CDN logo URLs.
 */

const ESPN_LOGO_BASE = "https://a.espncdn.com/i/teamlogos/nfl/500";

// Normalized franchise / abbreviation / name to ESPN logo code
const TEAM_CODE_MAP: Record<string, string> = {
  // Canonical franchise IDs
  ARI: "ari",
  ATL: "atl",
  BAL: "bal",
  BUF: "buf",
  CAR: "car",
  CHI: "chi",
  CIN: "cin",
  CLE: "cle",
  DAL: "dal",
  DEN: "den",
  DET: "det",
  GNB: "gb",
  GB: "gb",
  HOU: "hou",
  IND: "ind",
  JAX: "jax",
  JAC: "jax",
  KC: "kc",
  KAN: "kc",
  LAC: "lac",
  SDG: "lac",
  SD: "lac",
  LAR: "lar",
  LA: "lar",
  RAM: "lar",
  STL: "lar",
  LVR: "lv",
  LV: "lv",
  OAK: "lv",
  RAI: "lv",
  MIA: "mia",
  MIN: "min",
  NWE: "ne",
  NE: "ne",
  NOR: "no",
  NO: "no",
  NYG: "nyg",
  NYJ: "nyj",
  PHI: "phi",
  PIT: "pit",
  SEA: "sea",
  SFO: "sf",
  SF: "sf",
  TAM: "tb",
  TB: "tb",
  TEN: "ten",
  OTI: "ten",
  WAS: "wsh",
  WSH: "wsh",

  // Full and partial names (lowercase)
  "arizona cardinals": "ari",
  cardinals: "ari",
  "atlanta falcons": "atl",
  falcons: "atl",
  "baltimore ravens": "bal",
  ravens: "bal",
  "buffalo bills": "buf",
  bills: "buf",
  "carolina panthers": "car",
  panthers: "car",
  "chicago bears": "chi",
  bears: "chi",
  "cincinnati bengals": "cin",
  bengals: "cin",
  "cleveland browns": "cle",
  browns: "cle",
  "dallas cowboys": "dal",
  cowboys: "dal",
  "denver broncos": "den",
  broncos: "den",
  "detroit lions": "det",
  lions: "det",
  "green bay packers": "gb",
  packers: "gb",
  "houston texans": "hou",
  texans: "hou",
  "indianapolis colts": "ind",
  "baltimore colts": "ind",
  colts: "ind",
  "jacksonville jaguars": "jax",
  jaguars: "jax",
  "kansas city chiefs": "kc",
  chiefs: "kc",
  "los angeles chargers": "lac",
  "san diego chargers": "lac",
  chargers: "lac",
  "los angeles rams": "lar",
  "st. louis rams": "lar",
  rams: "lar",
  "las vegas raiders": "lv",
  "oakland raiders": "lv",
  raiders: "lv",
  "miami dolphins": "mia",
  dolphins: "mia",
  "minnesota vikings": "min",
  vikings: "min",
  "new england patriots": "ne",
  "boston patriots": "ne",
  patriots: "ne",
  "new orleans saints": "no",
  saints: "no",
  "new york giants": "nyg",
  giants: "nyg",
  "new york jets": "nyj",
  jets: "nyj",
  "philadelphia eagles": "phi",
  eagles: "phi",
  "pittsburgh steelers": "pit",
  steelers: "pit",
  "san francisco 49ers": "sf",
  "49ers": "sf",
  niners: "sf",
  "seattle seahawks": "sea",
  seahawks: "sea",
  "tampa bay buccaneers": "tb",
  buccaneers: "tb",
  bucs: "tb",
  "tennessee titans": "ten",
  "houston oilers": "ten",
  "tennessee oilers": "ten",
  titans: "ten",
  oilers: "ten",
  "washington commanders": "wsh",
  "washington football team": "wsh",
  "washington redskins": "wsh",
  commanders: "wsh",
  redskins: "wsh",
};

export interface TeamLogoCriterion {
  type?: string;
  criterion_id?: string;
  display_title?: string;
  icon_url?: string | null;
  parameters?: Record<string, unknown> | null;
}

/**
 * Returns the team logo image URL if the criterion corresponds to an NFL franchise/team,
 * or null if it's a non-franchise criterion (stat, accolade, draft pick, etc.).
 */
export function getTeamLogoUrl(criterion: TeamLogoCriterion): string | null {
  // If icon_url is explicitly provided on the criterion, use it
  if (criterion.icon_url) {
    return criterion.icon_url;
  }

  // 1. Check parameters.franchise_id or parameters.team_abbr
  const paramFranchise =
    (criterion.parameters?.franchise_id as string) ||
    (criterion.parameters?.team_abbr as string) ||
    (criterion.parameters?.team_id as string);
  if (paramFranchise) {
    const code = TEAM_CODE_MAP[paramFranchise.toUpperCase()];
    if (code) return `${ESPN_LOGO_BASE}/${code}.png`;
  }

  // 2. Check criterion_id (e.g. FRAN_GNB, FRAN_NYJ, GNB, etc.)
  if (criterion.criterion_id) {
    const rawId = criterion.criterion_id.toUpperCase();
    if (rawId.startsWith("FRAN_")) {
      const stripped = rawId.replace("FRAN_", "");
      const code = TEAM_CODE_MAP[stripped];
      if (code) return `${ESPN_LOGO_BASE}/${code}.png`;
    }
    if (TEAM_CODE_MAP[rawId]) {
      return `${ESPN_LOGO_BASE}/${TEAM_CODE_MAP[rawId]}.png`;
    }
  }

  // 3. If type is FRANCHISE or if display_title matches a known team
  if (criterion.type === "FRANCHISE" || criterion.display_title) {
    const titleKey = (criterion.display_title || "").toLowerCase().trim();
    if (TEAM_CODE_MAP[titleKey]) {
      return `${ESPN_LOGO_BASE}/${TEAM_CODE_MAP[titleKey]}.png`;
    }

    // Check if title ends with any known team mascot name (e.g. "Packers", "Jets")
    for (const [key, code] of Object.entries(TEAM_CODE_MAP)) {
      if (titleKey.includes(key) && key.length > 3) {
        return `${ESPN_LOGO_BASE}/${code}.png`;
      }
    }
  }

  return null;
}
