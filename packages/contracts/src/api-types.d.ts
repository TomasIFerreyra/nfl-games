/**
 * Auto-generated and maintained API Wire Formats & Domain Contracts
 * Corresponding to OpenAPI 3.1 definitions in apps/api
 */
export interface ProblemDetail {
    type: string;
    title: string;
    status: number;
    detail: string;
    instance: string;
    error_code: string;
    timestamp: string;
    invalid_params?: Array<{
        name: string;
        reason: string;
    }>;
}
export interface PlayerSummary {
    player_id: string;
    full_name: string;
    position: string;
    headshot_url?: string | null;
}
/**
 * Compact Array-of-Arrays row schema: [id, name, pos, start_year, end_year, is_active]
 */
export interface SearchIndexResponse {
    version: string;
    fields: string[];
    players: Array<[string, string, string, number, number | null, 0 | 1]>;
}
export interface GridCriterion {
    criterion_id: string;
    type: "FRANCHISE" | "STAT_SEASON" | "STAT_CAREER" | "ACCOLADE" | "DRAFT_ROUND" | "COLLEGE";
    display_title: string;
    subtitle?: string | null;
    icon_url?: string | null;
    parameters?: Record<string, unknown> | null;
}
export interface GridPuzzleData {
    rows: GridCriterion[];
    columns: GridCriterion[];
    min_cardinality_guarantee: number;
    cell_cardinalities?: number[][];
}
export interface GridValidateRequest {
    puzzle_id: string;
    row_index: number;
    col_index: number;
    player_id: string;
}
export interface GridValidateResponse {
    is_valid: boolean;
    row_index: number;
    col_index: number;
    player?: PlayerSummary | null;
    rarity_score?: number | null;
    total_picks_for_cell?: number | null;
    player_picks_for_cell?: number | null;
    possible_answers_count?: number | null;
    failed_criteria?: string[] | null;
    reason?: string | null;
}
export interface ConnectionsItem {
    item_id: string;
    display_text: string;
    subtext?: string | null;
    headshot_url?: string | null;
    position?: string | null;
}
export interface ConnectionsGroup {
    group_id: string;
    tier: 1 | 2 | 3 | 4;
    title: string;
    item_ids: [string, string, string, string];
    explanation: string;
}
export interface ConnectionsPuzzleData {
    items: ConnectionsItem[];
    groups?: ConnectionsGroup[];
}
export interface ConnectionsValidateRequest {
    puzzle_id: string;
    selected_item_ids: [string, string, string, string];
}
export interface ConnectionsValidateResponse {
    is_match: boolean;
    group?: ConnectionsGroup | null;
    is_one_away: boolean;
    matched_count?: number | null;
}
export interface Top10Entry {
    rank: number;
    player_id: string;
    player_name: string;
    metric_value: number;
    formatted_value: string;
    headshot_url?: string | null;
    active_years?: string | null;
    primary_franchise?: string | null;
    tied_player_ids?: string[] | null;
}
export interface Top10PuzzleData {
    category_id: string;
    title: string;
    description?: string | null;
    metric_label: string;
    slots_count?: number;
    leaderboard?: Top10Entry[];
}
export interface Top10GuessRequest {
    puzzle_id: string;
    player_id: string;
    previous_guesses?: string[];
}
export interface Top10GuessResponse {
    is_hit: boolean;
    entry?: Top10Entry | null;
    player_name?: string | null;
    strikes_added: number;
    current_strikes?: number | null;
    max_strikes?: number;
    is_game_over?: boolean;
    is_repeated?: boolean;
    reason?: string | null;
    total_found?: number | null;
    remaining_unrevealed?: number | null;
}
export interface DailyPuzzleResponse {
    puzzle_id: string;
    puzzle_number: number;
    target_date: string;
    game_type: "grid" | "reverse_grid" | "connections" | "top10";
    puzzle_data: Record<string, unknown>;
    created_at: string;
}
export interface Top10UserState {
    puzzle_id: string;
    revealed_slots: Record<number, Top10Entry>;
    strikes: number;
    strikes_remaining: number;
    submitted_player_ids: string[];
    missed_guesses: string[];
    is_completed: boolean;
    is_resigned?: boolean;
}
export interface ClientLocalStorageState {
    version: 1;
    client_id: string;
    games: {
        grid: {
            active_date: string;
            puzzle_id: string;
            guesses_remaining: number;
            is_completed: boolean;
            cells: Record<string, {
                player_id: string;
                player_name: string;
                is_correct: boolean;
                rarity_score: number;
            } | null>;
            used_player_ids: string[];
            summary_checksum: string;
        };
        connections: {
            active_date: string;
            puzzle_id: string;
            strikes_remaining: number;
            is_completed: boolean;
            solved_groups: ConnectionsGroup[];
            guess_history: string[][];
        };
        top10: {
            active_date: string;
            puzzle_id: string;
            strikes_remaining: number;
            strikes?: number;
            is_completed: boolean;
            revealed_ranks: number[];
            revealed_slots?: Record<number, Top10Entry>;
            missed_guesses: string[];
            submitted_player_ids?: string[];
            is_resigned?: boolean;
        };
    };
    streaks: {
        grid: {
            current: number;
            max: number;
            last_played: string;
        };
        connections: {
            current: number;
            max: number;
            last_played: string;
        };
        top10: {
            current: number;
            max: number;
            last_played: string;
        };
    };
}
