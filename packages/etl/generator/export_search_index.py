from datetime import datetime, timezone
import gzip
import json
import logging
import os
import pathlib
from typing import List, Union
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def export_player_search_index(
    session: AsyncSession,
    output_dir: str = "dist",
) -> str:
    """
    Exports the complete player catalog to a compact gzipped JSON file for edge CDN delivery.
    """
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_path = os.path.join(output_dir, "player_search_index.json.gz")

    query = text("""
        SELECT 
            p.player_id, 
            p.full_name, 
            p.primary_position, 
            p.rookie_year, 
            CASE 
                WHEN p.is_active = FALSE AND p.final_year IS NULL THEN (
                    SELECT MAX(s.season_year) 
                    FROM player_team_stints s 
                    WHERE s.player_id = p.player_id
                )
                ELSE p.final_year 
            END AS final_year, 
            p.is_active
        FROM players p
        ORDER BY p.is_active DESC, final_year DESC NULLS FIRST, p.full_name ASC;
    """)

    result = await session.execute(query)
    rows = result.fetchall()

    player_records: List[List[Union[str, int, None]]] = [
        [
            r[0],  # player_id
            r[1],  # full_name
            r[2],  # primary_position
            r[3],  # rookie_year
            r[4],  # final_year
            1 if r[5] else 0,  # is_active
        ]
        for r in rows
    ]

    payload = {
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d.1"),
        "fields": ["id", "name", "pos", "start", "end", "active"],
        "players": player_records,
    }

    raw_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    with gzip.open(out_path, "wb", compresslevel=9) as f:
        f.write(raw_json)

    size_kb = os.path.getsize(out_path) / 1024.0
    logger.info(f"Exported player search index to {out_path} ({size_kb:.1f} KB gzipped).")
    return out_path
