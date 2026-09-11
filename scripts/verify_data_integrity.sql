-- ============================================================================
-- VERIFICATION & DIAGNOSTIC INTEGRITY TEST SUITE
-- Database: nfl_games_db
-- Target: Validate fix of all reported data issues:
--   1. Jalen Ramsey multi-franchise stints (JAX, LAR, MIA, etc.)
--   2. Recent draft picks metadata (2024-2025) and regular season stints
--   3. Recent accolades (MVP, OROY, DROY, WPMOTY, All-Pro, Pro Bowl)
--   4. Absence of unverified future mock records (> 2025)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- TEST 1: Jalen Ramsey Franchise Stints Verification
-- Expectation: JAX (2016-2019), LAR (2019-2022), MIA (2023-2024), PIT (2025)
-- ----------------------------------------------------------------------------
SELECT 
    'TEST 1: Jalen Ramsey Stints' AS test_name,
    p.player_id,
    p.full_name,
    p.draft_year,
    p.draft_round,
    p.draft_overall,
    s.franchise_id,
    f.canonical_name,
    s.season_year,
    s.games_played
FROM players p
JOIN player_team_stints s ON p.player_id = s.player_id
JOIN franchises f ON s.franchise_id = f.franchise_id
WHERE p.full_name ILIKE '%Jalen Ramsey%'
ORDER BY s.season_year, s.franchise_id;

-- Assert Ramsey has at least JAX, LAR, and MIA
SELECT 
    'TEST 1 ASSERTION: Ramsey Franchise Coverage' AS assertion_name,
    p.full_name,
    COUNT(DISTINCT s.franchise_id) AS distinct_franchises,
    ARRAY_AGG(DISTINCT s.franchise_id ORDER BY s.franchise_id) AS franchises_played,
    CASE 
        WHEN 'JAX' = ANY(ARRAY_AGG(s.franchise_id)) 
         AND 'LAR' = ANY(ARRAY_AGG(s.franchise_id)) 
         AND 'MIA' = ANY(ARRAY_AGG(s.franchise_id))
        THEN 'PASS' 
        ELSE 'FAIL' 
    END AS test_result
FROM players p
JOIN player_team_stints s ON p.player_id = s.player_id
WHERE p.full_name ILIKE '%Jalen Ramsey%'
GROUP BY p.player_id, p.full_name;

-- ----------------------------------------------------------------------------
-- TEST 2: Recent Draft Picks (2023-2025) Metadata & Stint Coverage
-- Expectation: High completeness (>95%) for draft_round/overall and valid stints
-- ----------------------------------------------------------------------------
SELECT 
    'TEST 2: Draft Metadata Completeness' AS test_name,
    draft_year,
    COUNT(*) AS total_drafted,
    COUNT(draft_round) AS has_round,
    COUNT(draft_overall) AS has_overall,
    COUNT(college) AS has_college,
    ROUND(100.0 * COUNT(draft_round) / NULLIF(COUNT(*), 0), 2) AS round_coverage_pct
FROM players
WHERE draft_year BETWEEN 2020 AND 2025
GROUP BY draft_year
ORDER BY draft_year;

SELECT 
    'TEST 2: Recent Drafted Players with Recorded Stints' AS test_name,
    p.draft_year,
    COUNT(DISTINCT p.player_id) AS total_drafted_players,
    COUNT(DISTINCT s.player_id) AS players_with_stints,
    ROUND(100.0 * COUNT(DISTINCT s.player_id) / NULLIF(COUNT(DISTINCT p.player_id), 0), 2) AS stint_coverage_pct
FROM players p
LEFT JOIN player_team_stints s ON p.player_id = s.player_id AND s.games_played >= 1
WHERE p.draft_year IN (2023, 2024, 2025)
GROUP BY p.draft_year
ORDER BY p.draft_year;

-- ----------------------------------------------------------------------------
-- TEST 3: Recent Accolades Ingestion Check (2020-2024)
-- Expectation: Accolades table contains MVP, OROY, DROY, WPMOTY, All-Pro, Pro Bowl
-- ----------------------------------------------------------------------------
SELECT 
    'TEST 3: Accolades by Type & Recent Year Range' AS test_name,
    accolade_type,
    MIN(season_year) AS earliest_season,
    MAX(season_year) AS latest_season,
    COUNT(*) AS total_accolades
FROM accolades
GROUP BY accolade_type
ORDER BY total_accolades DESC;

SELECT 
    'TEST 3: Recent Major Award Winners Verification' AS test_name,
    a.season_year,
    a.accolade_type,
    p.full_name,
    a.franchise_id,
    a.category
FROM accolades a
JOIN players p ON a.player_id = p.player_id
WHERE a.accolade_type IN ('MVP', 'OROY', 'DROY', 'WPMOTY', 'FIRST_TEAM_ALL_PRO')
  AND a.season_year >= 2023
ORDER BY a.season_year DESC, a.accolade_type, p.full_name;

-- ----------------------------------------------------------------------------
-- TEST 4: Zero Future Mock / Placeholder Records Verification
-- Expectation: 0 rows returned for draft_year > 2025 or rookie_year > 2025
-- ----------------------------------------------------------------------------
SELECT 
    'TEST 4: Mock & Future Player Scan' AS test_name,
    COUNT(*) AS mock_player_count,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS test_result
FROM players
WHERE draft_year > 2025 OR rookie_year > 2025;

SELECT 
    'TEST 4: Future Stints Scan' AS test_name,
    COUNT(*) AS future_stints_count,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS test_result
FROM player_team_stints
WHERE season_year > 2025;
