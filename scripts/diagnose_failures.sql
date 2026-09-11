-- ============================================================================
-- FORENSIC DIAGNOSTIC SQL SCRIPT
-- Target: Investigate exact root cause for validation failures of:
--         Brett Favre, Jordan Love, Garrett Wilson
-- ============================================================================

-- 1. Check duplicate entities in players table
SELECT player_id, gsis_id, pfr_id, full_name, primary_position, draft_year, draft_round, draft_overall, rookie_year, final_year, is_active
FROM players 
WHERE full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson', 'Ahmad Gardner', 'Sauce Gardner')
ORDER BY full_name, player_id;

-- 2. Check stints registered for these players (showing player_id to detect split entity stints)
SELECT p.player_id, p.full_name, pts.franchise_id, pts.season_year, pts.games_played, pts.games_started
FROM player_team_stints pts
JOIN players p ON p.player_id = pts.player_id
WHERE p.full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson')
ORDER BY p.full_name, pts.season_year, pts.franchise_id;

-- 3. Check accolades for Brett Favre (and other key players)
SELECT p.player_id, p.full_name, a.accolade_id, a.accolade_type, a.category, a.season_year, a.franchise_id
FROM accolades a
JOIN players p ON p.player_id = a.player_id
WHERE p.full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson')
ORDER BY p.full_name, a.season_year, a.accolade_type;

-- 4. Check all distinct duplicate full_names across the entire database
SELECT full_name, COUNT(*) AS count_duplicates, ARRAY_AGG(player_id) AS player_ids, ARRAY_AGG(gsis_id) AS gsis_ids
FROM players
GROUP BY full_name
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 50;

-- 5. Check Grid validation criteria mapping for HOF, 1st Round pick, Franchise
SELECT DISTINCT accolade_type FROM accolades;
