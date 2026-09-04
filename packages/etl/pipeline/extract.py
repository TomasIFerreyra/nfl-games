import logging
from typing import Any, Dict, List
import pandas as pd

logger = logging.getLogger(__name__)


class NFLDataExtractor:
    """
    Extracts raw NFL roster, season statistics, and player ID cross-references from nflverse datasets.
    """

    @classmethod
    def extract_rosters(cls, years: List[int]) -> pd.DataFrame:
        """
        Extracts seasonal rosters containing biographical, college, draft, and GSIS IDs.
        """
        try:
            import nflreadpy as nfl
            logger.info(f"Loading seasonal rosters with nflreadpy for years: {years}")
            df = nfl.load_rosters(years)
            return df.to_pandas() if hasattr(df, "to_pandas") else df
        except Exception as e:
            logger.warning(f"nflreadpy load_rosters failed ({e}); attempting direct nflverse github release download.")
            frames = []
            for y in years:
                url = f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{y}.csv"
                try:
                    df_year = pd.read_csv(url, low_memory=False)
                    frames.append(df_year)
                except Exception as err:
                    logger.error(f"Failed to fetch roster for {y}: {err}")
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    @classmethod
    def extract_seasonal_stats(cls, years: List[int]) -> pd.DataFrame:
        """
        Extracts regular season individual player statistics.
        """
        try:
            import nflreadpy as nfl
            logger.info(f"Loading player stats with nflreadpy for years: {years}")
            df = nfl.load_player_stats(years)
            return df.to_pandas() if hasattr(df, "to_pandas") else df
        except Exception as e:
            logger.warning(f"nflreadpy load_player_stats failed ({e}); downloading from nflverse player_stats.")
            url = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv"
            df = pd.read_csv(url, low_memory=False)
            return df[df["season"].isin(years)] if "season" in df.columns else df

    @classmethod
    def extract_id_mappings(cls) -> pd.DataFrame:
        """
        Extracts the universal player ID mapping table cross-referencing GSIS, PFR, and ESPN.
        """
        try:
            import nflreadpy as nfl
            logger.info("Loading player catalog and ID mapping with nflreadpy...")
            df = nfl.load_players()
            return df.to_pandas() if hasattr(df, "to_pandas") else df
        except Exception as e:
            logger.warning(f"nflreadpy load_players failed ({e}); downloading fallback ids.")
            url = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
            return pd.read_csv(url, low_memory=False)
