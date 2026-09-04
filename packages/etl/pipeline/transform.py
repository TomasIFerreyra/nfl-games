import uuid
from typing import Any, Dict, List, Optional
import pandas as pd

# Canonical franchise continuum mapping dictionary
FRANCHISE_MAP: Dict[str, str] = {
    # Oilers / Titans
    "HOU": "TEN",  # Historically Oilers before 1997; modern Texans handled by season context
    "OIL": "TEN",
    "TEN": "TEN",
    # Rams Lineage
    "RAM": "LAR",
    "STL": "LAR",
    "LA": "LAR",
    "LAR": "LAR",
    # Raiders Lineage
    "OAK": "LVR",
    "RAI": "LVR",
    "LV": "LVR",
    "LVR": "LVR",
    # Chargers Lineage
    "SD": "LAC",
    "SDG": "LAC",
    "LAC": "LAC",
    # Cardinals Lineage
    "PHO": "ARI",
    "CRD": "ARI",
    "ARI": "ARI",
    # Washington Lineage
    "BOS": "WAS",
    "WAS": "WAS",
    "WFT": "WAS",
    # Browns / Ravens Rule: strictly separated
    "BAL": "BAL",
    "CLE": "CLE",
    # Standard franchise acronyms
    "KC": "KC",
    "KAN": "KC",
    "GB": "GNB",
    "GNB": "GNB",
    "SF": "SFO",
    "SFO": "SFO",
    "NE": "NWE",
    "NWE": "NWE",
    "NO": "NOR",
    "NOR": "NOR",
    "TB": "TAM",
    "TAM": "TAM",
}


class NFLDataTransformer:
    """
    Transforms raw nflverse data frames into normalized relational records matching DB schemas.
    """

    @classmethod
    def resolve_franchise_id(cls, team_abbr: str, season_year: int) -> str:
        """
        Disambiguates shared city abbreviations (e.g., Houston Oilers vs Houston Texans).
        """
        clean_abbr = team_abbr.strip().upper() if team_abbr else ""
        if clean_abbr == "HOU":
            # Houston Oilers (<= 1996) vs Houston Texans (>= 2002)
            return "TEN" if season_year <= 1996 else "HOU"
        if clean_abbr == "BAL":
            # Baltimore Colts (<= 1983) vs Baltimore Ravens (>= 1996)
            return "IND" if season_year <= 1983 else "BAL"
        return FRANCHISE_MAP.get(clean_abbr, clean_abbr)

    @classmethod
    def transform_players(
        cls,
        rosters_df: pd.DataFrame,
        id_map_df: pd.DataFrame,
    ) -> List[Dict[str, Any]]:
        """
        Deduplicates players by GSIS ID and attaches PFR/Draft metadata.
        """
        if rosters_df.empty:
            return []

        # Ensure string IDs
        rosters = rosters_df.copy()
        if "gsis_id" not in rosters.columns and "player_id" in rosters.columns:
            rosters["gsis_id"] = rosters["player_id"]

        # Drop records without player identity
        rosters = rosters.dropna(subset=["gsis_id", "player_name" if "player_name" in rosters.columns else "full_name"])

        # Aggregate min/max season per player
        season_col = "season" if "season" in rosters.columns else "year"
        name_col = "player_name" if "player_name" in rosters.columns else "full_name"
        pos_col = "position" if "position" in rosters.columns else "primary_position"

        players_records: List[Dict[str, Any]] = []

        # Merge with ID map if present
        pfr_map = {}
        if not id_map_df.empty and "gsis_id" in id_map_df.columns and "pfr_id" in id_map_df.columns:
            valid_ids = id_map_df.dropna(subset=["gsis_id", "pfr_id"])
            pfr_map = dict(zip(valid_ids["gsis_id"], valid_ids["pfr_id"]))

        seen_pfr_ids = set()
        grouped = rosters.groupby("gsis_id")
        for gsis_id, group in grouped:
            first_row = group.iloc[0]
            full_name = str(first_row[name_col]).strip()
            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            rookie_year = int(group[season_col].min())
            max_year = int(group[season_col].max())
            is_active = bool(max_year >= 2024)

            # Safely resolve pfr_id without NaN string leaks
            raw_pfr = pfr_map.get(gsis_id)
            if pd.isna(raw_pfr) or not raw_pfr:
                raw_pfr = first_row.get("pfr_id")
            
            pfr_id = None
            if pd.notna(raw_pfr):
                clean_pfr = str(raw_pfr).strip()
                if clean_pfr and clean_pfr.lower() not in ("nan", "none") and clean_pfr not in seen_pfr_ids:
                    pfr_id = clean_pfr[:40]
                    seen_pfr_ids.add(pfr_id)

            raw_college = first_row.get("college")
            college = None
            if pd.notna(raw_college):
                clean_col = str(raw_college).strip()
                if clean_col and clean_col.lower() not in ("nan", "none"):
                    college = clean_col[:100]

            raw_headshot = first_row.get("headshot_url")
            headshot_url = None
            if pd.notna(raw_headshot):
                clean_hs = str(raw_headshot).strip()
                if clean_hs and clean_hs.lower() not in ("nan", "none"):
                    headshot_url = clean_hs[:255]

            players_records.append({
                "player_id": str(uuid.uuid4()),
                "gsis_id": str(gsis_id),
                "pfr_id": pfr_id,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "primary_position": str(first_row.get(pos_col, "ATH"))[:10],
                "draft_year": int(first_row.get("draft_year")) if pd.notna(first_row.get("draft_year")) else None,
                "draft_round": int(first_row.get("draft_round")) if pd.notna(first_row.get("draft_round")) else None,
                "draft_overall": int(first_row.get("draft_number")) if pd.notna(first_row.get("draft_number")) else None,
                "college": college,
                "rookie_year": rookie_year,
                "final_year": None if is_active else max_year,
                "is_active": is_active,
                "headshot_url": headshot_url,
            })

        return players_records

    @classmethod
    def transform_stints(cls, rosters_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Constructs regular season stint records enforcing games_played >= 1.
        """
        stints = []
        season_col = "season" if "season" in rosters_df.columns else "year"
        team_col = "team" if "team" in rosters_df.columns else "recent_team"
        gp_col = "games" if "games" in rosters_df.columns else "games_played"

        for _, row in rosters_df.iterrows():
            gsis_id = row.get("gsis_id") or row.get("player_id")
            if not gsis_id or pd.isna(gsis_id):
                continue

            season = int(row.get(season_col, 2020))
            raw_team = str(row.get(team_col, ""))
            franchise_id = cls.resolve_franchise_id(raw_team, season)
            games_played = int(row.get(gp_col, 1)) if pd.notna(row.get(gp_col)) else 1

            if games_played >= 1:
                stints.append({
                    "gsis_id": str(gsis_id),
                    "franchise_id": franchise_id,
                    "season_year": season,
                    "games_played": games_played,
                    "games_started": int(row.get("games_started", 0)) if pd.notna(row.get("games_started")) else 0,
                })

        return stints
