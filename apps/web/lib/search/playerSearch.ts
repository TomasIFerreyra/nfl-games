import { FALLBACK_PLAYERS } from "./fallbackPlayers";

export interface SearchIndexResponse {
  version: string;
  fields: string[];
  players: (string | number | boolean | null)[][];
}

export interface SearchPlayerItem {
  id: string;
  name: string;
  position: string;
  startYear: number;
  endYear: number | null;
  isActive: boolean;
}

class PlayerSearchEngine {
  // Initialize immediately with the rich embedded player dataset (never empty!)
  private players: SearchPlayerItem[] = [...FALLBACK_PLAYERS];
  private isLoaded: boolean = false;
  private loadPromise: Promise<void> | null = null;

  public async init(apiUrl: string = "/api/v1/players/search-index"): Promise<void> {
    if (this.isLoaded) return;
    if (this.loadPromise) return this.loadPromise;

    this.loadPromise = (async () => {
      // 1. Try to fetch from FastAPI endpoint with a 3000ms timeout
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);

        const res = await fetch(apiUrl, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (res.ok) {
          const rawData = await res.json();
          const playersList = Array.isArray(rawData) ? rawData : rawData?.players;
          if (Array.isArray(playersList) && playersList.length > 0) {
            this.indexCatalog({ version: "1.0", fields: [], players: playersList });
            this.isLoaded = true;
            return;
          }
        }
      } catch (err) {
        // Backend offline or timed out; try static fallback file next
      }

      // 2. Try to fetch from static public directory /player_search_index.json
      try {
        const staticRes = await fetch("/player_search_index.json");
        if (staticRes.ok) {
          const staticData = await staticRes.json();
          const playersList = Array.isArray(staticData) ? staticData : staticData?.players;
          if (Array.isArray(playersList) && playersList.length > 0) {
            this.indexCatalog({ version: "1.0", fields: [], players: playersList });
            this.isLoaded = true;
            return;
          }
        }
      } catch (err) {
        // Fallback to embedded players already initialized
      }

      this.isLoaded = true;
    })();


    return this.loadPromise;
  }

  public indexCatalog(data: SearchIndexResponse): void {
    const remotePlayers: SearchPlayerItem[] = data.players.map((p) => ({
      id: p[0] as string,
      name: p[1] as string,
      position: p[2] as string,
      startYear: p[3] as number,
      endYear: p[4] as number | null,
      isActive: Boolean(p[5]),
    }));

    if (remotePlayers.length > 0) {
      // Build lookup sets for both ID and normalized name from the remote/DB data.
      // Fallback players that share a name with a DB record (even if the ID differs)
      // must be excluded — the DB version is always canonical.
      const existingIds = new Set(remotePlayers.map((p) => p.id));
      const existingNames = new Set(remotePlayers.map((p) => p.name.toLowerCase().trim()));

      const merged = [...remotePlayers];
      for (const fb of FALLBACK_PLAYERS) {
        if (!existingIds.has(fb.id) && !existingNames.has(fb.name.toLowerCase().trim())) {
          merged.push(fb);
        }
      }
      this.players = merged;
    }
  }



  public search(query: string, limit: number = 10): SearchPlayerItem[] {
    if (!this.players || this.players.length === 0) {
      this.players = [...FALLBACK_PLAYERS];
    }

    const cleanQuery = query.trim().toLowerCase();
    if (!cleanQuery) return [];

    const tokens = cleanQuery.split(/\s+/).filter(Boolean);
    const results: Array<{ item: SearchPlayerItem; score: number }> = [];

    for (let i = 0; i < this.players.length; i++) {
      const p = this.players[i];
      const lowerName = p.name.toLowerCase();
      const nameParts = lowerName.split(" ");
      const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";

      let score = -1;

      // 1. Exact full name match
      if (lowerName === cleanQuery) {
        score = 150;
      }
      // 2. Exact last name match (e.g. user types "Mahomes")
      else if (lastName === cleanQuery) {
        score = 120;
      }
      // 3. Last name starts with query
      else if (lastName.startsWith(cleanQuery)) {
        score = 100;
      }
      // 4. Full name starts with query (e.g. "Patrick M...")
      else if (lowerName.startsWith(cleanQuery)) {
        score = 90;
      }
      // 5. Multi-token match (e.g. "Tom B" matches "Tom Brady")
      else if (tokens.length > 1 && tokens.every((t) => lowerName.includes(t))) {
        score = 80;
      }
      // 6. Any substring match
      else if (lowerName.includes(cleanQuery)) {
        score = 50;
      }

      if (score > 0) {
        // Boost active players
        if (p.isActive) score += 15;
        // Minor boost for Hall of Fame / modern legends
        if (!p.endYear || p.endYear >= 2010) score += 5;
        results.push({ item: p, score });
      }
    }

    results.sort((a, b) => b.score - a.score);
    return results.slice(0, limit).map((r) => r.item);
  }

  public getPlayerCount(): number {
    return this.players.length;
  }
}

export const playerSearchEngine = new PlayerSearchEngine();
