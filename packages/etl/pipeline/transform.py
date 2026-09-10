import datetime
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
        id_info_map = {}
        pfr_map = {}
        if not id_map_df.empty:
            for _, id_row in id_map_df.iterrows():
                gid = id_row.get("gsis_id")
                if pd.notna(gid) and str(gid).strip():
                    gid_str = str(gid).strip()
                    id_info_map[gid_str] = id_row
                    raw_pfr = id_row.get("pfr_id")
                    if pd.notna(raw_pfr):
                        pfr_map[gid_str] = str(raw_pfr).strip()

        seen_pfr_ids = set()
        grouped = rosters.groupby("gsis_id")
        current_year = datetime.datetime.now().year

        for gsis_id, group in grouped:
            first_row = group.iloc[0]
            full_name = str(first_row[name_col]).strip()
            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            id_info = id_info_map.get(str(gsis_id))
            stint_min_year = int(group[season_col].min())
            stint_max_year = int(group[season_col].max())

            # Canonical rookie year resolution
            canonical_rookie = None
            if id_info is not None:
                raw_rs = id_info.get("rookie_season")
                if pd.notna(raw_rs):
                    try:
                        canonical_rookie = int(raw_rs)
                    except (ValueError, TypeError):
                        pass
                if canonical_rookie is None or canonical_rookie < 1920:
                    raw_dy = id_info.get("draft_year")
                    if pd.notna(raw_dy):
                        try:
                            canonical_rookie = int(raw_dy)
                        except (ValueError, TypeError):
                            pass

            if canonical_rookie is None or canonical_rookie < 1920:
                raw_dy = first_row.get("draft_year")
                if pd.notna(raw_dy):
                    try:
                        canonical_rookie = int(raw_dy)
                    except (ValueError, TypeError):
                        pass

            if canonical_rookie is not None and 1920 <= canonical_rookie <= current_year + 1:
                rookie_year = min(canonical_rookie, stint_min_year)
            else:
                rookie_year = stint_min_year

            # Canonical retirement and active status resolution
            canonical_last = None
            player_status = ""
            if id_info is not None:
                raw_ls = id_info.get("last_season")
                if pd.notna(raw_ls):
                    try:
                        canonical_last = int(raw_ls)
                    except (ValueError, TypeError):
                        pass
                raw_status = id_info.get("status")
                if pd.notna(raw_status):
                    player_status = str(raw_status).strip().upper()

            # Player is active if playing in current season, unless explicitly retired/exempt
            if player_status in ("RET", "EXE", "HON"):
                is_active = False
            elif stint_max_year >= current_year or (player_status == "ACT" and stint_max_year >= current_year - 1):
                is_active = True
            elif canonical_last and canonical_last >= current_year and player_status == "ACT":
                is_active = True
            else:
                is_active = False

            if is_active:
                final_year = None
            else:
                final_year = max(stint_max_year, canonical_last) if canonical_last else stint_max_year

            # Safely resolve pfr_id without NaN string leaks
            raw_pfr = pfr_map.get(str(gsis_id))
            if pd.isna(raw_pfr) or not raw_pfr:
                raw_pfr = first_row.get("pfr_id")
            
            pfr_id = None
            if pd.notna(raw_pfr):
                clean_pfr = str(raw_pfr).strip()
                if clean_pfr and clean_pfr.lower() not in ("nan", "none") and clean_pfr not in seen_pfr_ids:
                    pfr_id = clean_pfr[:40]
                    seen_pfr_ids.add(pfr_id)

            raw_college = first_row.get("college")
            if (pd.isna(raw_college) or not raw_college) and id_info is not None:
                raw_college = id_info.get("college_name")
            college = None
            if pd.notna(raw_college):
                clean_col = str(raw_college).strip()
                if clean_col and clean_col.lower() not in ("nan", "none"):
                    college = clean_col[:100]

            raw_headshot = first_row.get("headshot_url")
            if (pd.isna(raw_headshot) or not raw_headshot) and id_info is not None:
                raw_headshot = id_info.get("headshot")
            headshot_url = None
            if pd.notna(raw_headshot):
                clean_hs = str(raw_headshot).strip()
                if clean_hs and clean_hs.lower() not in ("nan", "none"):
                    headshot_url = clean_hs[:255]

            draft_year_val = None
            raw_dy = first_row.get("draft_year")
            if (pd.isna(raw_dy) or not raw_dy) and id_info is not None:
                raw_dy = id_info.get("draft_year")
            if pd.notna(raw_dy):
                try:
                    draft_year_val = int(raw_dy)
                except (ValueError, TypeError):
                    pass

            draft_round_val = None
            raw_dr = first_row.get("draft_round")
            if (pd.isna(raw_dr) or not raw_dr) and id_info is not None:
                raw_dr = id_info.get("draft_round")
            if pd.notna(raw_dr):
                try:
                    draft_round_val = int(raw_dr)
                except (ValueError, TypeError):
                    pass

            draft_pick_val = None
            raw_dp = first_row.get("draft_number")
            if (pd.isna(raw_dp) or not raw_dp) and id_info is not None:
                raw_dp = id_info.get("draft_pick")
            if pd.notna(raw_dp):
                try:
                    draft_pick_val = int(raw_dp)
                except (ValueError, TypeError):
                    pass

            players_records.append({
                "player_id": str(uuid.uuid4()),
                "gsis_id": str(gsis_id),
                "pfr_id": pfr_id,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "primary_position": str(first_row.get(pos_col, "ATH"))[:10],
                "draft_year": draft_year_val,
                "draft_round": draft_round_val,
                "draft_overall": draft_pick_val,
                "college": college,
                "rookie_year": rookie_year,
                "final_year": final_year,
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
