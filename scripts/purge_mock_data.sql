-- ============================================================================
-- PURGE MOCK DATA & SPECULATIVE PLACEHOLDERS
-- Database: nfl_games_db
-- Target: Remove unverified future draft picks (2026+), placeholder players,
--         and phantom records with no official NFL regular season participation.
-- ============================================================================

BEGIN;

-- 1. Identify and log count of mock/speculative future players
DO $$
DECLARE
    mock_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO mock_count
    FROM players
    WHERE (draft_year > 2025 OR rookie_year > 2025)
      AND player_id NOT IN (
          SELECT DISTINCT player_id 
          FROM player_team_stints 
          WHERE season_year <= 2025 AND games_played >= 1
      );
    RAISE NOTICE 'Found % mock/future player records eligible for purging.', mock_count;
END $$;

-- 2. Remove future/invalid season stints if any exist (> 2025)
DELETE FROM player_team_stints
WHERE season_year > 2025;

-- 3. Delete phantom / future players with no official regular season game appearances
DELETE FROM players
WHERE (draft_year > 2025 OR rookie_year > 2025)
  AND player_id NOT IN (
      SELECT DISTINCT player_id 
      FROM player_team_stints 
      WHERE season_year <= 2025 AND games_played >= 1
  );

-- 4. Purge placeholder name patterns if any exist
DELETE FROM players
WHERE (
    full_name ILIKE '%Mock Pick%'
    OR full_name ILIKE '%Placeholder%'
    OR full_name ILIKE '%Draft Prospect%'
    OR full_name ILIKE '%TBD%'
)
AND player_id NOT IN (
    SELECT DISTINCT player_id 
    FROM player_team_stints 
    WHERE games_played >= 1
);

-- 5. Reset any erroneous future draft metadata on legitimate existing players
UPDATE players
SET draft_year = NULL,
    draft_round = NULL,
    draft_overall = NULL
WHERE draft_year > 2025;

-- 6. Clean up any orphaned stats or career precomputed records
DELETE FROM player_career_stats
WHERE player_id NOT IN (SELECT player_id FROM players);

DELETE FROM player_season_stats
WHERE season_year > 2025;

COMMIT;
