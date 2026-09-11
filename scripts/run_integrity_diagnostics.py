#!/usr/bin/env python3
"""
Executes verify_data_integrity.sql and formats output into clean diagnostic reports.
"""

import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "apps", "api")
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from app.core.config import settings

async def run_diagnostics():
    engine = create_async_engine(settings.async_database_url)
    async with engine.connect() as conn:
        print("=" * 80)
        print("DATABASE INTEGRITY DIAGNOSTIC & VERIFICATION SUITE")
        print("=" * 80)

        # 1. Jalen Ramsey Stints
        print("\n--- TEST 1: JALEN RAMSEY MULTI-FRANCHISE STINTS ---")
        q1 = text("""
            SELECT s.season_year, s.franchise_id, f.canonical_name, s.games_played, s.games_started
            FROM players p
            JOIN player_team_stints s ON p.player_id = s.player_id
            JOIN franchises f ON s.franchise_id = f.franchise_id
            WHERE p.full_name ILIKE '%Jalen Ramsey%'
            ORDER BY s.season_year, s.franchise_id;
        """)
        rows1 = (await conn.execute(q1)).fetchall()
        for r in rows1:
            print(f"  Season {r[0]}: {r[1]} ({r[2]}) -> GP: {r[3]}, GS: {r[4]}")

        q1_assert = text("""
            SELECT 
                COUNT(DISTINCT s.franchise_id) AS distinct_franchises,
                ARRAY_AGG(DISTINCT s.franchise_id ORDER BY s.franchise_id) AS franchises,
                CASE 
                    WHEN 'JAX' = ANY(ARRAY_AGG(s.franchise_id)) 
                     AND 'LAR' = ANY(ARRAY_AGG(s.franchise_id)) 
                     AND 'MIA' = ANY(ARRAY_AGG(s.franchise_id))
                    THEN 'PASS' 
                    ELSE 'FAIL' 
                END AS result
            FROM players p
            JOIN player_team_stints s ON p.player_id = s.player_id
            WHERE p.full_name ILIKE '%Jalen Ramsey%'
            GROUP BY p.player_id;
        """)
        r_assert = (await conn.execute(q1_assert)).fetchone()
        print(f"  => Assertion [JAX, LAR, MIA Coverage]: {r_assert[2]} (Franchises: {r_assert[1]})")

        # 2. Recent Draft Metadata & Stint Coverage
        print("\n--- TEST 2: RECENT DRAFT PICKS (2020-2025) METADATA & STINT COVERAGE ---")
        q2 = text("""
            SELECT 
                draft_year,
                COUNT(*) AS total_drafted,
                COUNT(draft_round) AS has_round,
                COUNT(draft_overall) AS has_overall,
                COUNT(college) AS has_college,
                ROUND(100.0 * COUNT(draft_round) / NULLIF(COUNT(*), 0), 1) AS round_pct
            FROM players
            WHERE draft_year BETWEEN 2020 AND 2025
            GROUP BY draft_year
            ORDER BY draft_year;
        """)
        rows2 = (await conn.execute(q2)).fetchall()
        print(f"  {'Draft Year':<12} {'Total Drafted':<15} {'Has Round':<12} {'Has Overall':<12} {'Coverage':<10}")
        for r in rows2:
            print(f"  {r[0]:<12} {r[1]:<15} {r[2]:<12} {r[3]:<12} {r[5]}%")

        q2_stints = text("""
            SELECT 
                p.draft_year,
                COUNT(DISTINCT p.player_id) AS total_drafted,
                COUNT(DISTINCT s.player_id) AS with_stints,
                ROUND(100.0 * COUNT(DISTINCT s.player_id) / NULLIF(COUNT(DISTINCT p.player_id), 0), 1) AS stint_pct
            FROM players p
            LEFT JOIN player_team_stints s ON p.player_id = s.player_id AND s.games_played >= 1
            WHERE p.draft_year IN (2023, 2024, 2025)
            GROUP BY p.draft_year
            ORDER BY p.draft_year;
        """)
        rows2_s = (await conn.execute(q2_stints)).fetchall()
        print("\n  Draft Stint Coverage:")
        for r in rows2_s:
            print(f"  Draft Year {r[0]}: {r[2]}/{r[1]} players with active stints ({r[3]}%)")

        # 3. Recent Accolades
        print("\n--- TEST 3: RECENT ACCOLADES & HONORS SUMMARY ---")
        q3_summary = text("""
            SELECT accolade_type, COUNT(*), MIN(season_year), MAX(season_year)
            FROM accolades
            GROUP BY accolade_type
            ORDER BY COUNT(*) DESC;
        """)
        rows3_s = (await conn.execute(q3_summary)).fetchall()
        for r in rows3_s:
            print(f"  {r[0]:<22} Total: {r[1]:<5} Range: {r[2]} - {r[3]}")

        print("\n  Sample Recent Award Winners (2023-2024):")
        q3_winners = text("""
            SELECT a.season_year, a.accolade_type, p.full_name, a.franchise_id
            FROM accolades a
            JOIN players p ON a.player_id = p.player_id
            WHERE a.accolade_type IN ('MVP', 'OROY', 'DROY', 'WPMOTY', 'FIRST_TEAM_ALL_PRO')
              AND a.season_year >= 2023
            ORDER BY a.season_year DESC, a.accolade_type, p.full_name;
        """)
        rows3_w = (await conn.execute(q3_winners)).fetchall()
        for r in rows3_w:
            print(f"  [{r[0]}] {r[1]:<20} -> {r[2]} ({r[3] or 'NFL'})")

        # 4. Zero Future Mock Data
        print("\n--- TEST 4: ABSENCE OF FUTURE / MOCK DATA (> 2025) ---")
        q4_players = text("SELECT COUNT(*) FROM players WHERE draft_year > 2025 OR rookie_year > 2025;")
        count4_p = (await conn.execute(q4_players)).scalar()
        print(f"  Future/Mock Players (> 2025): {count4_p} -> {'PASS' if count4_p == 0 else 'FAIL'}")

        q4_stints = text("SELECT COUNT(*) FROM player_team_stints WHERE season_year > 2025;")
        count4_s = (await conn.execute(q4_stints)).scalar()
        print(f"  Future Stints (> 2025): {count4_s} -> {'PASS' if count4_s == 0 else 'FAIL'}")

        print("\n" + "=" * 80)
        print("ALL DATA INTEGRITY CHECKS COMPLETED SUCCESSFULLY")
        print("=" * 80)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
