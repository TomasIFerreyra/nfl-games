-- ============================================================================
-- FORENSIC DIAGNOSTIC SQL SCRIPT: Milton Williams vs Creed Humphrey Collision
-- ============================================================================

-- 1. Database Check: Query entity records for Milton Williams and Creed Humphrey
SELECT 
    player_id, 
    gsis_id, 
    pfr_id, 
    full_name, 
    primary_position, 
    birth_date,
    rookie_year,
    final_year,
    is_active
FROM players 
WHERE full_name IN ('Milton Williams', 'Creed Humphrey')
   OR gsis_id IN ('00-0036916', '00-0036623')
ORDER BY full_name;

-- 2. Team Stints Check: Verify franchise stints registered in database
SELECT 
    p.player_id, 
    p.full_name, 
    p.gsis_id,
    pts.franchise_id, 
    pts.season_year, 
    pts.games_played, 
    pts.games_started
FROM player_team_stints pts
JOIN players p ON p.player_id = pts.player_id
WHERE p.full_name IN ('Milton Williams', 'Creed Humphrey')
ORDER BY p.full_name, pts.season_year DESC;
