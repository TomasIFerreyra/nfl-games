-- ============================================================================
-- verify_player_metadata.sql
-- ----------------------------------------------------------------------------
-- Verification and Audit Script for Player Metadata, Rosters, Jersey Numbers,
-- and CDN Headshots.
-- Output Target: Drake Maye, Jaxon Smith-Njigba, Daniel Jones, Cooper Kupp, A.J. Brown
-- ============================================================================

-- 1. Main Metadata Inspection Query
WITH latest_player_teams AS (
    SELECT DISTINCT ON (s.player_id)
        s.player_id,
        s.franchise_id AS team,
        s.season_year
    FROM player_team_stints s
    ORDER BY s.player_id, s.season_year DESC, s.games_played DESC
),
target_players AS (
    SELECT
        p.player_id,
        p.gsis_id,
        p.full_name,
        COALESCE(t.team, 'FA') AS team,
        p.primary_position AS position,
        p.jersey_number,
        p.headshot_url
    FROM players p
    LEFT JOIN latest_player_teams t ON p.player_id = t.player_id
    WHERE p.full_name IN (
        'Drake Maye',
        'Jaxon Smith-Njigba',
        'Daniel Jones',
        'Cooper Kupp',
        'A.J. Brown'
    )
)
SELECT 
    full_name,
    team,
    position,
    jersey_number,
    headshot_url
FROM target_players
ORDER BY full_name;

-- ============================================================================
-- 2. Automated Assertions & Guardrail Invariant Checks
-- ============================================================================
DO $$
DECLARE
    rec RECORD;
    target_count INT;
BEGIN
    -- Check that all 5 target players exist in database
    SELECT COUNT(*) INTO target_count
    FROM players
    WHERE full_name IN ('Drake Maye', 'Jaxon Smith-Njigba', 'Daniel Jones', 'Cooper Kupp', 'A.J. Brown');

    IF target_count < 5 THEN
        RAISE EXCEPTION 'ASSERTION FAILED: Expected 5 target players, found %', target_count;
    END IF;

    -- Validate Drake Maye
    SELECT p.full_name, p.primary_position, p.jersey_number, p.headshot_url, t.franchise_id INTO rec
    FROM players p
    LEFT JOIN LATERAL (
        SELECT franchise_id FROM player_team_stints s WHERE s.player_id = p.player_id ORDER BY s.season_year DESC LIMIT 1
    ) t ON true
    WHERE p.full_name = 'Drake Maye';

    IF rec.jersey_number <> 10 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Drake Maye: expected jersey #10, got #%', rec.jersey_number;
    END IF;
    IF rec.franchise_id <> 'NE' THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Drake Maye: expected team NE, got %', rec.franchise_id;
    END IF;
    IF rec.headshot_url IS NULL OR length(rec.headshot_url) < 10 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Drake Maye: missing headshot URL';
    END IF;

    -- Validate Jaxon Smith-Njigba
    SELECT p.full_name, p.primary_position, p.jersey_number, p.headshot_url, t.franchise_id INTO rec
    FROM players p
    LEFT JOIN LATERAL (
        SELECT franchise_id FROM player_team_stints s WHERE s.player_id = p.player_id ORDER BY s.season_year DESC LIMIT 1
    ) t ON true
    WHERE p.full_name = 'Jaxon Smith-Njigba';

    IF rec.jersey_number <> 11 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Jaxon Smith-Njigba: expected jersey #11, got #%', rec.jersey_number;
    END IF;
    IF rec.franchise_id <> 'SEA' THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Jaxon Smith-Njigba: expected team SEA, got %', rec.franchise_id;
    END IF;
    IF rec.headshot_url IS NULL OR length(rec.headshot_url) < 10 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Jaxon Smith-Njigba: missing headshot URL';
    END IF;

    -- Validate Daniel Jones
    SELECT p.full_name, p.primary_position, p.jersey_number, p.headshot_url, t.franchise_id INTO rec
    FROM players p
    LEFT JOIN LATERAL (
        SELECT franchise_id FROM player_team_stints s WHERE s.player_id = p.player_id ORDER BY s.season_year DESC LIMIT 1
    ) t ON true
    WHERE p.full_name = 'Daniel Jones';

    IF rec.jersey_number <> 17 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Daniel Jones: expected jersey #17, got #%', rec.jersey_number;
    END IF;
    IF rec.franchise_id <> 'IND' THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Daniel Jones: expected team IND, got %', rec.franchise_id;
    END IF;
    IF rec.headshot_url IS NULL OR length(rec.headshot_url) < 10 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Daniel Jones: missing headshot URL';
    END IF;

    -- Validate Cooper Kupp
    SELECT p.full_name, p.primary_position, p.jersey_number, p.headshot_url, t.franchise_id INTO rec
    FROM players p
    LEFT JOIN LATERAL (
        SELECT franchise_id FROM player_team_stints s WHERE s.player_id = p.player_id ORDER BY s.season_year DESC LIMIT 1
    ) t ON true
    WHERE p.full_name = 'Cooper Kupp';

    IF rec.jersey_number <> 10 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Cooper Kupp: expected jersey #10, got #%', rec.jersey_number;
    END IF;
    IF rec.franchise_id <> 'SEA' THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Cooper Kupp: expected team SEA, got %', rec.franchise_id;
    END IF;
    IF rec.headshot_url IS NULL OR length(rec.headshot_url) < 10 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for Cooper Kupp: missing headshot URL';
    END IF;

    -- Validate A.J. Brown (Patriots Trade Confirmation)
    SELECT p.full_name, p.primary_position, p.jersey_number, p.headshot_url, t.franchise_id INTO rec
    FROM players p
    LEFT JOIN LATERAL (
        SELECT franchise_id FROM player_team_stints s WHERE s.player_id = p.player_id ORDER BY s.season_year DESC LIMIT 1
    ) t ON true
    WHERE p.full_name = 'A.J. Brown';

    IF rec.jersey_number <> 1 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for A.J. Brown: expected jersey #1, got #%', rec.jersey_number;
    END IF;
    IF rec.franchise_id <> 'NE' THEN
        RAISE EXCEPTION 'ASSERTION FAILED for A.J. Brown: expected team NE (Patriots), got %', rec.franchise_id;
    END IF;
    IF rec.headshot_url IS NULL OR length(rec.headshot_url) < 10 THEN
        RAISE EXCEPTION 'ASSERTION FAILED for A.J. Brown: missing headshot URL';
    END IF;

    -- Validate Cooper Kupp and Daniel Jones have DISTINCT headshots (No Swapped Photos)
    IF (SELECT headshot_url FROM players WHERE full_name = 'Cooper Kupp') =
       (SELECT headshot_url FROM players WHERE full_name = 'Daniel Jones') THEN
        RAISE EXCEPTION 'ASSERTION FAILED: Swapped/Duplicate photo detected between Cooper Kupp and Daniel Jones';
    END IF;

    RAISE NOTICE 'ALL ASSERTIONS PASSED: Player metadata, active teams, jersey numbers, and CDN headshots are 100%% verified.';
END $$;
