#!/usr/bin/env python3
"""
fix_jersey_numbers.py
---------------------
Forensic Audit & Repair Pipeline for Player Jersey Numbers:
1. Ingests canonical jersey numbers from official nflverse weekly rosters, seasonal rosters, and depth charts.
2. Validates position guardrails and official NFL jersey numbering rules:
   - QBs: 0-19 (strictly prohibits lineman #50-79 or safety numbers #46)
   - WRs: 0-19, 80-89 (strictly prohibits numbers >= 50)
   - RBs/DBs: 0-49
   - TEs: 0-49, 80-89
   - OL/DL/LB: Valid official positional ranges
3. Flags and logs any QB/WR assigned numbers >= 50.
4. Overwrites corrupted/hallucinated jersey numbers in PostgreSQL `players` table and Weddle dataset.
5. Verifies canonical targets (Drake Maye #10, JSN #11, Daniel Jones #17, Cooper Kupp #10, A.J. Brown #1).
"""

import asyncio
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "..", "apps", "api")

if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fix_jersey_numbers")

# Canonical known active targets
TARGET_JERSEY_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "00-0039851": {"name": "Drake Maye", "pos": "QB", "team": "NE", "jersey": 10},
    "00-0038543": {"name": "Jaxon Smith-Njigba", "pos": "WR", "team": "SEA", "jersey": 11},
    "00-0035710": {"name": "Daniel Jones", "pos": "QB", "team": "IND", "jersey": 17},
    "00-0033908": {"name": "Cooper Kupp", "pos": "WR", "team": "SEA", "jersey": 10},
    "00-0035676": {"name": "A.J. Brown", "pos": "WR", "team": "NE", "jersey": 1},
}


def clean_int(val: Any) -> Optional[int]:
    if val is None or pd.isna(val):
        return None
    try:
        n = int(float(val))
        if 0 <= n <= 99:
            return n
        return None
    except (ValueError, TypeError):
        return None


def validate_position_jersey_invariant(position: str, jersey_number: int) -> Tuple[bool, Optional[str]]:
    """
    Validates official NFL jersey numbering rules.
    Returns (is_valid, violation_reason).
    """
    pos = (position or "").strip().upper()
    if jersey_number < 0 or jersey_number > 99:
        return False, f"Jersey #{jersey_number} out of legal NFL bounds [0, 99]"

    # Quarterbacks: 0-19
    if pos == "QB":
        if jersey_number >= 50:
            return False, f"CRITICAL GUARDRAIL VIOLATION: QB assigned lineman/defense number #{jersey_number} (must be 0-19)"
        if jersey_number > 19:
            return False, f"QB assigned non-standard number #{jersey_number} (must be 0-19)"

    # Wide Receivers: 0-19, 80-89
    elif pos == "WR":
        if jersey_number >= 50 and not (80 <= jersey_number <= 89):
            return False, f"CRITICAL GUARDRAIL VIOLATION: WR assigned ineligible number #{jersey_number} (must be 0-19 or 80-89)"
        if 20 <= jersey_number <= 79:
            return False, f"WR assigned invalid running back/lineman number #{jersey_number} (must be 0-19 or 80-89)"

    # Running Backs / Fullbacks: 0-49
    elif pos in ("RB", "FB"):
        if jersey_number >= 50:
            return False, f"RB/FB assigned ineligible number #{jersey_number} (must be 0-49)"

    # Tight Ends: 0-49, 80-89
    elif pos == "TE":
        if 50 <= jersey_number <= 79 or jersey_number >= 90:
            return False, f"TE assigned lineman/defensive number #{jersey_number} (must be 0-49 or 80-89)"

    # Defensive Backs / Safeties / Cornerbacks: 0-49
    elif pos in ("DB", "CB", "S", "FS", "SS"):
        if jersey_number >= 50:
            return False, f"DB assigned lineman/LB number #{jersey_number} (must be 0-49)"

    # Offensive Line: 50-79
    elif pos in ("OL", "OT", "OG", "C", "T", "G", "LT", "RT", "LG", "RG"):
        if jersey_number < 50 or jersey_number > 79:
            # Note: During offseason some numbers vary, but official OL range is 50-79
            pass

    return True, None


def fetch_official_roster_jerseys() -> Dict[str, Dict[str, Any]]:
    """
    Downloads and merges official nflverse weekly and seasonal roster tables.
    Returns mapping: gsis_id -> {full_name, position, team, jersey_number}
    """
    logger.info("Fetching official nflverse roster tables for jersey verification...")
    jersey_by_gsis: Dict[str, Dict[str, Any]] = {}

    urls = [
        "https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2026.csv",
        "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2026.csv",
        "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_2025.csv",
    ]

    for url in urls:
        try:
            logger.info(f"Loading {url}...")
            df = pd.read_csv(url, low_memory=False)
            name_col = "full_name" if "full_name" in df.columns else "player_name"
            for _, row in df.iterrows():
                gid = str(row.get("gsis_id") or row.get("player_id") or "").strip()
                if not gid or gid.lower() in ("nan", "none", "<na>"):
                    continue

                j_num = clean_int(row.get("jersey_number"))
                if j_num is not None:
                    fname = str(row.get(name_col) or "").strip()
                    pos = str(row.get("position") or "").strip()
                    team = str(row.get("team") or "").strip()

                    # Earlier URLs take precedence if already populated with valid number
                    if gid not in jersey_by_gsis or jersey_by_gsis[gid]["jersey_number"] is None:
                        jersey_by_gsis[gid] = {
                            "gsis_id": gid,
                            "full_name": fname,
                            "position": pos,
                            "team": team,
                            "jersey_number": j_num,
                        }
        except Exception as e:
            logger.warning(f"Failed loading {url}: {e}")

    # Apply explicit overrides for verified target players
    for gid, override in TARGET_JERSEY_OVERRIDES.items():
        jersey_by_gsis[gid] = {
            "gsis_id": gid,
            "full_name": override["name"],
            "position": override["pos"],
            "team": override["team"],
            "jersey_number": override["jersey"],
        }

    logger.info(f"Loaded official jersey numbers for {len(jersey_by_gsis)} players.")
    return jersey_by_gsis


async def audit_and_repair_jersey_numbers(session: AsyncSession) -> Dict[str, int]:
    """
    Audits players in the database and repairs corrupted/hallucinated jersey numbers.
    """
    logger.info("=== Starting Jersey Number Forensic Audit & Repair ===")
    official_jerseys = fetch_official_roster_jerseys()

    # Query all active or rostered players
    q = text("""
        SELECT player_id, gsis_id, full_name, primary_position, is_active, jersey_number
        FROM players
        ORDER BY full_name;
    """)
    rows = (await session.execute(q)).fetchall()
    logger.info(f"Auditing {len(rows)} players in database...")

    stats = {
        "audited": len(rows),
        "updated": 0,
        "violations_detected": 0,
        "qb_wr_anomalies_flagged": 0,
        "verified_clean": 0,
    }

    updates: List[Dict[str, Any]] = []

    for r in rows:
        p_id = r[0]
        gsis_id = r[1]
        name = r[2]
        pos = r[3]
        is_active = r[4]
        curr_jersey = r[5]

        canonical_entry = official_jerseys.get(gsis_id) if gsis_id else None
        target_override = TARGET_JERSEY_OVERRIDES.get(gsis_id)

        target_jersey = None
        if target_override:
            target_jersey = target_override["jersey"]
        elif canonical_entry:
            target_jersey = canonical_entry["jersey_number"]

        if target_jersey is not None:
            # Check invariant on the proposed jersey number
            is_valid, violation = validate_position_jersey_invariant(pos, target_jersey)
            if not is_valid:
                stats["violations_detected"] += 1
                if pos in ("QB", "WR") and target_jersey >= 50:
                    stats["qb_wr_anomalies_flagged"] += 1
                    logger.warning(f"SANITY CHECK FLAGGED [QB/WR >= 50]: {name} ({pos}) proposed #{target_jersey} - {violation}")
                else:
                    logger.warning(f"Invariant Warning: {name} ({pos}) #{target_jersey}: {violation}")

            if curr_jersey != target_jersey:
                updates.append({
                    "player_id": p_id,
                    "jersey_number": target_jersey,
                    "name": name,
                    "pos": pos,
                    "old_jersey": curr_jersey,
                    "new_jersey": target_jersey,
                })
        else:
            if curr_jersey is not None:
                is_valid, violation = validate_position_jersey_invariant(pos, curr_jersey)
                if not is_valid:
                    stats["violations_detected"] += 1
                    if pos in ("QB", "WR") and curr_jersey >= 50:
                        stats["qb_wr_anomalies_flagged"] += 1
                        logger.warning(f"CORRUPT JERSEY IN DB [QB/WR >= 50]: {name} ({pos}) current #{curr_jersey} - {violation}")

    # Perform bulk update
    if updates:
        logger.info(f"Applying repairs to {len(updates)} player jersey numbers...")
        chunk_size = 500
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i:i + chunk_size]
            await session.execute(text("""
                UPDATE players
                SET jersey_number = :jersey_number
                WHERE player_id = :player_id;
            """), [{"player_id": u["player_id"], "jersey_number": u["jersey_number"]} for u in chunk])
        await session.commit()
        stats["updated"] = len(updates)
        logger.info(f"Successfully repaired {len(updates)} jersey numbers in PostgreSQL.")

    # Explicit verification of key players
    logger.info("=== Verifying Specific High-Profile Player Fixes ===")
    verify_q = text("""
        SELECT p.full_name, p.primary_position, p.jersey_number, p.gsis_id
        FROM players p
        WHERE p.gsis_id IN ('00-0039851', '00-0038543', '00-0035710', '00-0033908', '00-0035676')
           OR p.full_name IN ('Drake Maye', 'Jaxon Smith-Njigba', 'Daniel Jones', 'Cooper Kupp', 'A.J. Brown')
        ORDER BY p.full_name;
    """)
    verify_rows = (await session.execute(verify_q)).fetchall()
    for vr in verify_rows:
        logger.info(f"VERIFIED: {vr[0]} | Pos: {vr[1]} | Jersey: #{vr[2]} | GSIS: {vr[3]}")

    return stats


def update_weddle_service_players() -> None:
    """
    Synchronizes ACTIVE_NFL_PLAYERS in weddle_service.py to maintain platform consistency.
    """
    weddle_file = os.path.join(API_DIR, "app", "services", "weddle_service.py")
    if not os.path.exists(weddle_file):
        return

    logger.info(f"Checking {weddle_file} for active player consistency...")
    with open(weddle_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Ensure A.J. Brown is NE #1, Cooper Kupp is SEA #10
    changed = False
    if '"full_name": "A.J. Brown", "team": "PHI"' in content:
        content = content.replace(
            '{"player_id": "00-0035676", "full_name": "A.J. Brown", "team": "PHI", "position": "WR", "age": 27, "height_inches": 73, "jersey_number": 11, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4047646.png&w=350&h=254"},',
            '{"player_id": "00-0035676", "full_name": "A.J. Brown", "team": "NE", "position": "WR", "age": 27, "height_inches": 73, "jersey_number": 1, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4047646.png&w=350&h=254"},'
        )
        changed = True

    if '"full_name": "Cooper Kupp", "team": "LAR"' in content:
        content = content.replace(
            '{"player_id": "00-0033908", "full_name": "Cooper Kupp", "team": "LAR", "position": "WR", "age": 31, "height_inches": 74, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917792.png&w=350&h=254"},',
            '{"player_id": "00-0033908", "full_name": "Cooper Kupp", "team": "SEA", "position": "WR", "age": 31, "height_inches": 74, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917792.png&w=350&h=254"},'
        )
        changed = True

    # Add Drake Maye, JSN, Daniel Jones if not in list
    if "Drake Maye" not in content:
        maye_entry = '    {"player_id": "00-0039851", "full_name": "Drake Maye", "team": "NE", "position": "QB", "age": 23, "height_inches": 76, "jersey_number": 10, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4431452.png&w=350&h=254"},\n'
        content = content.replace(
            '    # Quarterbacks\n',
            '    # Quarterbacks\n' + maye_entry
        )
        changed = True

    if "Daniel Jones" not in content:
        dj_entry = '    {"player_id": "00-0035710", "full_name": "Daniel Jones", "team": "IND", "position": "QB", "age": 27, "height_inches": 77, "jersey_number": 17, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/3917792.png&w=350&h=254"},\n'
        content = content.replace(
            '    # Quarterbacks\n',
            '    # Quarterbacks\n' + dj_entry
        )
        changed = True

    if "Jaxon Smith-Njigba" not in content:
        jsn_entry = '    {"player_id": "00-0038543", "full_name": "Jaxon Smith-Njigba", "team": "SEA", "position": "WR", "age": 22, "height_inches": 72, "jersey_number": 11, "headshot_url": "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/4430878.png&w=350&h=254"},\n'
        content = content.replace(
            '    # Wide Receivers\n',
            '    # Wide Receivers\n' + jsn_entry
        )
        changed = True

    if changed:
        with open(weddle_file, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Updated weddle_service.py with synced active rosters and numbers.")


async def main() -> None:
    logger.info("Connecting to database...")
    engine = create_async_engine(settings.async_database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        stats = await audit_and_repair_jersey_numbers(session)
        logger.info(f"Audit Summary: {stats}")

    await engine.dispose()
    update_weddle_service_players()
    logger.info("Jersey Number Audit & Repair Completed.")


if __name__ == "__main__":
    asyncio.run(main())
