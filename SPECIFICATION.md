# Software Architecture Specification (SDD-001)
## NFL Daily Mini-Games Platform
**Document Version:** 1.0.0-PROD-SPEC  
**Author:** Principal Software Architect & Data Systems Engineer  
**Status:** APPROVED & FINALIZED FOR IMPLEMENTATION  
**Target Systems:** FastAPI (Backend Core), PostgreSQL 16+ (Data Engine), Next.js 14+ (App Router Client)

---

## 1. System Requirements & Domain Invariants

### 1.1 Functional Requirements by Mini-Game

#### 1.1.1 3x3 Grid (Immaculate Grid Style)
- **Grid Structure:** A 2D matrix indexed $(r, c)$ where $r \in \{0, 1, 2\}$ and $c \in \{0, 1, 2\}$, representing 9 discrete intersection cells.
- **Criteria Assignment:** 3 distinct row criteria $R_0, R_1, R_2$ and 3 distinct column criteria $C_0, C_1, C_2$.
- **Guess Budget:** A hard ceiling of nine (9) total guess attempts per daily puzzle instance. Each submission burns one guess regardless of correctness.
- **Player Uniqueness Invariant:** A player entity $P$ can only be used once per 3x3 puzzle instance. If $P$ is successfully placed in cell $(r_1, c_1)$, $P$ is permanently disqualified from cells $(r_2, c_2)$ for that user session.
- **Correctness Rule:** A guess $P$ for cell $(r, c)$ is valid if and only if:
  $$\text{Satisfies}(P, R_r) \land \text{Satisfies}(P, C_c) = \text{TRUE}$$
- **Rarity Metric:** Each correct guess yields a cell rarity score $R \in (0.00, 100.00\%]$. The total puzzle rarity score is $\sum_{i=0}^8 R_i$ (lower is superior).

#### 1.1.2 Reverse Grid
- **Inverse Mechanics:** The 3x3 player matrix is pre-populated with 9 known historical players $P_{r, c}$. The row/column criteria labels are masked or presented as an unassigned criteria pool.
- **Objective:** The user must correctly identify the underlying criteria $(R_0..R_2, C_0..C_2)$ from a set of distractors and valid candidates that simultaneously satisfy all 9 cells.
- **State Validation:** A candidate criteria assignment $\mathbf{A} = \{R_0, R_1, R_2, C_0, C_1, C_2\}$ is verified against the static player set:
  $$\forall r \in \{0,1,2\}, \forall c \in \{0,1,2\}: \text{Satisfies}(P_{r, c}, R_r) \land \text{Satisfies}(P_{r, c}, C_c) = \text{TRUE}$$
- **Attempt Budget:** 3 incorrect criteria assignment attempts before puzzle failure.

#### 1.1.3 Connections 4x4
- **Board Composition:** A 16-element set $S = \{e_1, e_2, \dots, e_{16}\}$ of NFL entities (players, coaches, or franchises).
- **Partition Invariant:** There exists strictly one unique partition of $S$ into 4 disjoint subsets $\{G_1, G_2, G_3, G_4\}$ such that $|G_k| = 4$ for all $k \in \{1, 2, 3, 4\}$, and each $G_k$ satisfies a distinct thematic category rule $T_k$.
- **Difficulty Grading:** 4 strictly graded tiers:
  - *Tier 1 (Bronze / Straightforward):* Colleges (Alabama, Ohio State, LSU), draft year/class (1st Round picks, #1 Overall), single-team tenure, obvious hardware (Heisman Trophy, Pro Football Hall of Fame).
  - *Tier 2 (Silver / Statistical Milestones):* Single-season or career metrics (5,000+ passing yds season, 1,500+ rushing yds, 100+ career sacks, 100+ career rushing TDs, 5+ Pro Bowls).
  - *Tier 3 (Gold / Overlaps & Journeymen):* Multi-franchise dual tenures ("Played for both NE and NYJ", "Played for both GB and MIN"), draft round origins ("Drafted in 4th round or later / UDFA", Day 2 picks), hardware combinations (AP MVP, Super Bowl MVPs, OROY/DROY).
  - *Tier 4 (Lombardi Platinum or Obsidian / Obscure & Quirky):* Demographic/name quirks ("First name Michael/Mike", "First name Chris"), unique pedigree/statistical quirks ("Drafted #1 Overall and won a Super Bowl", "Won both Heisman & NFL MVP").
- **Attempt Budget:** 4 incorrect guess strikes before game over.
- **"One Away" Heuristic:** If a submitted 4-element guess overlaps with any target group $G_k$ by exactly 3 elements ($|G_{\text{guess}} \cap G_k| = 3$), the system returns a non-penalizing advisory signal: `is_one_away: true`.


#### 1.1.4 Top 10 Leaderboard Trivia
- **Prompt:** An ordered statistical or historical query (e.g., "Top 10 Passing Touchdowns in a Single Season (2020s)" or "All-Time NFL Career Sacks Leaders").
- **Board Representation:** 10 masked slots ranked #1 to #10.
- **Guess Evaluation:** User submits player names one by one. If player $P \in \text{Top10}$ (or is tied at a valid rank $\le 10$), reveal slot with rank, official player headshot, player name, and formatted statistical value.
- **Strike Budget:** Hard ceiling of 3 incorrect strikes (players outside the top 10).
- **Repeated Guess Invariant:** Submitting a player already guessed in the current session does not burn a strike (`is_repeated: true`, `strikes_added: 0`).
- **Completion States:** Solved (all 10 slots revealed), Struck Out (3 strikes reached), or Surrendered/Resigned. Final score weighted by rank discovery and strike penalty.

#### 1.1.5 Guess the Player (Weddle Mode)
- **Objective:** Guess the mystery active NFL player chosen deterministically each calendar day.
- **Guess Limit:** Hard ceiling of six (6) total guess attempts.
- **Feedback Table Attributes:** Guessed player is evaluated against target player across 8 attributes:
  0. Player Name & Headshot preview
  1. Team (Current NFL Franchise)
  2. Side of Ball (Offense vs. Defense)
  3. Position (e.g., QB, WR, CB, DE)
  4. Conference (AFC vs. NFC)
  5. Division (East, North, South, West)
  6. Age (in years)
  7. Height (in inches, formatted as feet/inches: e.g., 6'2")
  8. Jersey Number (e.g., #15)
- **Color Grading & Directional Clues:**
  - *Green (Exact Match):* Attribute exactly matches target player.
  - *Yellow (Partial / Close Match):*
    - Positional sub-groups: OL (`OT`, `OG`, `C`, `OL`), DB (`CB`, `S`, `FS`, `SS`, `DB`), DL/EDGE (`DE`, `DT`, `NT`, `DL`, `EDGE`), LB (`LB`, `ILB`, `OLB`, `MLB`), WR/TE (`WR`, `TE`), RB/FB (`RB`, `FB`).
    - Age: Within $\pm 2$ years of target.
    - Height: Within $\pm 2$ inches of target.
    - Jersey Number: Within $\pm 2$ of target.
  - *Gray (Incorrect):* Criteria not satisfied.
  - *Directional Indicators:* For Age, Height, and Jersey Number, non-exact matches display `↑` if target is higher or `↓` if target is lower.
- **Anti-Cheat Invariant:** Target player identity is omitted from client payloads until `is_game_over == true`.

---

### 1.2 Domain Rules, Edge Cases & Franchise Lineage Invariants

#### 1.2.1 Franchise Identity vs. Team Season Identity
- **Franchise Invariant (Continuity Rule):** Puzzles querying franchise affiliation evaluate against the *Franchise Continuum ID*, not the historic transient city acronym.
  - *Houston Oilers / Tennessee Titans:* Houston Oilers (1960–1996), Tennessee Oilers (1997–1998), and Tennessee Titans (1999–present) share Franchise ID `TEN`.
  - *Los Angeles / St. Louis Rams:* Cleveland Rams (1937–1945), Los Angeles Rams (1946–1994, 2016–present), and St. Louis Rams (1995–2015) share Franchise ID `LAR`.
  - *The Cleveland Browns / Baltimore Ravens Exception:* Per official NFL legal settlement (1996): Baltimore Ravens (`BAL`) are categorized as a 1996 expansion franchise. Pre-1996 Cleveland Browns records and history remained with the suspended Cleveland franchise, reactivated in 1999 (`CLE`). A player playing for the 1994 Browns does NOT satisfy a "Played for Ravens" criterion.
  - *Commanders Lineage:* Boston Braves (1932) -> Boston Redskins (1933–1936) -> Washington Redskins (1937–2019) -> Washington Football Team (2020–2021) -> Washington Commanders (2022–present) share Franchise ID `WAS`.

#### 1.2.2 Mid-Season Trades, Snap Thresholds & Regular Season Eligibility
- **Official Game Appearance Rule:** A player is credited with playing for team $T$ in season $S$ if and only if:
  $$\text{regular\_season\_games\_played}(P, T, S) \ge 1$$
- **Edge Cases Disallowed:**
  - *Offseason Roster / Preseason Only:* Cut during training camp/preseason without appearing in $\ge 1$ regular season game is INVALID.
  - *Practice Squad / Inactive Reserve (IR):* Player rostered on IR or Practice Squad without logging an official active game appearance is INVALID.
  - *Mid-Season Trade / Multi-Team Seasons:* If Player $P$ played 4 games for Indianapolis (`IND`) and was traded to Seattle (`SEA`) where he played 6 games in season 2020, $P$ satisfies both "Played for IND" and "Played for SEA".

#### 1.2.3 Accolades & Statistical Threshold Disambiguation
- **Pro Bowl Criterion:** Official Pro Bowl roster selection status for the season (includes original ballot selections and official alternates who accepted and were named to the official roster).
- **All-Pro Criterion:** AP (Associated Press) First-Team All-Pro selection only.
- **Super Bowl Champion Criterion:** Player must have been on the official 53-man active roster or injured reserve of the Super Bowl winning team on the date of the Super Bowl game.
- **Statistical Milestones:** Single-season thresholds refer strictly to regular season records. Career sacks count official sacks from 1982 onward.

#### 1.2.4 Minimum Intersection Cardinality ($k$-Guaranteed Solvability)
- For every cell $(r, c)$ in a generated 3x3 Grid, the cardinality of the candidate intersection set $S_{r, c} = \{P \mid \text{Satisfies}(P, R_r) \land \text{Satisfies}(P, C_c)\}$ must satisfy:
  $$|S_{r, c}| \ge k \quad \text{where } k = 3$$
- Puzzles containing any cell with $|S_{r, c}| < 3$ are rejected by the generation engine as "bottleneck cells."

---

### 1.3 Non-Functional Requirements (NFRs) & Performance Budgets

| Metric | Threshold | Target Environment / Context |
| :--- | :--- | :--- |
| **Client Search Autocomplete P95** | $\le 50\text{ ms}$ | In-memory client-side Trie / Fuse index scan (mobile 4G) |
| **API Guess Validation P95** | $\le 150\text{ ms}$ | FastAPI -> PostgreSQL indexed query + Redis cache |
| **Search Bundle Payload Size** | $\le 400\text{ KB}$ | Gzipped transfer size for complete active/historical catalog |
| **Search Bundle Memory Footprint** | $\le 4.5\text{ MB}$ | Client browser heap footprint once parsed into memory |
| **Daily Puzzle Generation SLA** | $\le 120\text{ sec}$ | Batch computation run daily at 00:00:00 UTC for Day $D+7$ |
| **API Availability / Uptime** | $99.9\%$ | Redundant serverless/container deployment |

---

## 2. Domain Data Model & Entity Specifications

### 2.1 Entity-Relationship Architecture

```
+---------------------------------------------------------------------------------------+
|                                    RELATIONAL SCHEMA                                  |
+---------------------------------------------------------------------------------------+

   [ franchises ] 1 ----< N [ team_seasons ]
          |                        |
          | 1                      | 1
          |                        |
          v N                      v N
   [ player_team_stints ] >---- [ player_season_stats ]
          ^                                |
          | N                              | N
          |                                |
          +----------- [ players ] <-------+
                            | 1
                            |
                            v N
                       [ accolades ]

   [ daily_puzzles ] 1 ----< N [ game_submissions ]
          | 1
          |
          v N
   [ aggregated_answer_stats ] >---- N [ players ]
```

### 2.2 Relational Schema Specifications

#### 2.2.1 Table: `franchises`
- `franchise_id` VARCHAR(10) PRIMARY KEY (e.g., `TEN`, `ARI`, `LAR`, `BAL`)
- `canonical_name` VARCHAR(100) NOT NULL
- `established_year` SMALLINT NOT NULL CHECK (established_year >= 1920)

#### 2.2.2 Table: `team_seasons`
- `team_season_id` VARCHAR(10) PRIMARY KEY (e.g., `HOU_1993`, `TEN_2023`)
- `franchise_id` VARCHAR(10) NOT NULL REFERENCES franchises(franchise_id) ON DELETE RESTRICT
- `season_year` SMALLINT NOT NULL CHECK (season_year BETWEEN 1920 AND 2100)
- `team_name` VARCHAR(100) NOT NULL
- `team_abbr` VARCHAR(5) NOT NULL
- *Unique Constraint:* `(franchise_id, season_year)`

#### 2.2.3 Table: `players`
- `player_id` VARCHAR(36) PRIMARY KEY (Canonical UUID)
- `gsis_id` VARCHAR(50) UNIQUE NULLABLE (Official NFL GSIS ID)
- `pfr_id` VARCHAR(20) UNIQUE NULLABLE (Pro-Football-Reference ID)
- `full_name` VARCHAR(100) NOT NULL
- `first_name` VARCHAR(50) NOT NULL
- `last_name` VARCHAR(50) NOT NULL
- `primary_position` VARCHAR(10) NOT NULL
- `draft_year` SMALLINT NULLABLE
- `draft_round` SMALLINT NULLABLE
- `draft_overall` SMALLINT NULLABLE
- `college` VARCHAR(100) NULLABLE
- `rookie_year` SMALLINT NOT NULL
- `final_year` SMALLINT NULLABLE
- `is_active` BOOLEAN NOT NULL DEFAULT FALSE
- `headshot_url` VARCHAR(255) NULLABLE
- *Indexes:* `GIN(full_name gin_trgm_ops)`, `B-Tree(primary_position, is_active)`

#### 2.2.4 Table: `player_team_stints`
- `stint_id` BIGSERIAL PRIMARY KEY
- `player_id` VARCHAR(36) NOT NULL REFERENCES players(player_id) ON DELETE CASCADE
- `franchise_id` VARCHAR(10) NOT NULL REFERENCES franchises(franchise_id) ON DELETE RESTRICT
- `season_year` SMALLINT NOT NULL
- `games_played` SMALLINT NOT NULL DEFAULT 0 CHECK (games_played >= 0)
- `games_started` SMALLINT NOT NULL DEFAULT 0 CHECK (games_started >= 0)
- *Unique Constraint:* `(player_id, franchise_id, season_year)`
- *Index:* `(franchise_id, games_played) WHERE games_played > 0`

#### 2.2.5 Table: `player_season_stats`
- `stat_id` BIGSERIAL PRIMARY KEY
- `player_id` VARCHAR(36) NOT NULL REFERENCES players(player_id) ON DELETE CASCADE
- `team_season_id` VARCHAR(10) NOT NULL REFERENCES team_seasons(team_season_id) ON DELETE RESTRICT
- `season_year` SMALLINT NOT NULL
- `passing_yards` INTEGER NOT NULL DEFAULT 0
- `passing_tds` SMALLINT NOT NULL DEFAULT 0
- `interceptions` SMALLINT NOT NULL DEFAULT 0
- `rushing_yards` INTEGER NOT NULL DEFAULT 0
- `rushing_tds` SMALLINT NOT NULL DEFAULT 0
- `receptions` SMALLINT NOT NULL DEFAULT 0
- `receiving_yards` INTEGER NOT NULL DEFAULT 0
- `receiving_tds` SMALLINT NOT NULL DEFAULT 0
- `sacks` NUMERIC(4,1) NOT NULL DEFAULT 0.0
- `defensive_interceptions` SMALLINT NOT NULL DEFAULT 0
- *Unique Constraint:* `(player_id, team_season_id, season_year)`

#### 2.2.6 Table: `accolades`
- `accolade_id` BIGSERIAL PRIMARY KEY
- `player_id` VARCHAR(36) NOT NULL REFERENCES players(player_id) ON DELETE CASCADE
- `franchise_id` VARCHAR(10) NULLABLE REFERENCES franchises(franchise_id) ON DELETE RESTRICT
- `season_year` SMALLINT NOT NULL
- `accolade_type` VARCHAR(50) NOT NULL
- `category` VARCHAR(50) NULLABLE
- *Index:* `(accolade_type, season_year, player_id)`

#### 2.2.7 Table: `daily_puzzles`
- `puzzle_id` UUID PRIMARY KEY DEFAULT gen_random_uuid()
- `target_date` DATE NOT NULL
- `game_type` VARCHAR(20) NOT NULL
- `puzzle_number` INTEGER NOT NULL
- `puzzle_data` JSONB NOT NULL
- `solution_hash` VARCHAR(64) NOT NULL
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
- *Unique Constraint:* `(target_date, game_type)`

#### 2.2.8 Table: `aggregated_answer_stats`
- `stat_id` BIGSERIAL PRIMARY KEY
- `puzzle_id` UUID NOT NULL REFERENCES daily_puzzles(puzzle_id) ON DELETE CASCADE
- `cell_identifier` VARCHAR(10) NOT NULL
- `player_id` VARCHAR(36) NOT NULL REFERENCES players(player_id) ON DELETE CASCADE
- `selection_count` BIGINT NOT NULL DEFAULT 1
- `pick_percentage` NUMERIC(5,2) NOT NULL DEFAULT 0.00
- *Unique Constraint:* `(puzzle_id, cell_identifier, player_id)`

---

## 3. API Contracts & Wire Formats (OpenAPI 3.1)

### 3.1 Standardized RFC 7807 Error Response Contract
```json
{
  "type": "https://api.nflminigames.com/v1/errors/INVALID_SUBMISSION",
  "title": "Invalid Guess Submission",
  "status": 422,
  "detail": "Player '00-0033873' has already been used in cell (0, 1) for this puzzle session.",
  "instance": "/api/v1/grid/validate",
  "error_code": "PLAYER_ALREADY_USED",
  "timestamp": "2026-09-04T20:00:45Z",
  "invalid_params": [
    {
      "name": "player_id",
      "reason": "Entity uniqueness invariant violated across active grid."
    }
  ]
}
```

### 3.2 Endpoints

#### 3.2.1 `GET /api/v1/puzzles/{game_type}/daily`
- Query param: `date` (YYYY-MM-DD, optional)
- Returns sanitized daily puzzle configuration (criteria, clues, masked slots). Answers are excluded.

#### 3.2.2 `POST /api/v1/grid/validate`
- Body: `{ puzzle_id, row_index, col_index, player_id }`
- Returns: `{ is_valid, player, rarity_score, total_picks_for_cell, player_picks_for_cell, possible_answers_count }`

#### 3.2.3 `GET /api/v1/players/search-index`
- Response: Compact Array-of-Arrays wire protocol (`[id, name, pos, start, end, active]`)
- Caching: `Cache-Control: public, max-age=86400, immutable` (320 KB gzipped)

#### 3.2.4 `POST /api/v1/connections/validate-group`
- **Request Body:** `{ puzzle_id: UUID | string, selected_item_ids: string[4] }`
- **Validation Constraints:**
  - `selected_item_ids` must have exactly 4 items (`INVALID_ITEM_COUNT`, 422).
  - `selected_item_ids` must contain distinct items without duplicates (`DUPLICATE_ITEMS_SUBMITTED`, 422).
  - All items must exist on the active puzzle board (`INVALID_ITEM_ID`, 422).
  - Target puzzle must exist with `game_type = 'CONNECTIONS'` (`PUZZLE_NOT_FOUND`, 404).
- **Success Response (200 OK):**
  - Match: `{ is_match: true, group: { group_id, tier, title, explanation, item_ids }, is_one_away: false, matched_count: 4 }`
  - Incorrect (One Away): `{ is_match: false, group: null, is_one_away: true, matched_count: 3 }`
  - Incorrect (No One Away): `{ is_match: false, group: null, is_one_away: false, matched_count: max_matched_count }`

##### 3.2.5 `POST /api/v1/top10/guess`
- **Request Body:** `{ puzzle_id: UUID | string, player_id: string, previous_guesses?: string[] }`
- **Validation Constraints:**
  - `puzzle_id` must reference an existing puzzle with `game_type = 'TOP10'` (`PUZZLE_NOT_FOUND`, 404).
  - `player_id` must not be blank (`INVALID_PLAYER_ID`, 422).
- **Success Response (200 OK):**
  - **Hit:** `{ is_hit: true, entry: { rank, player_id, player_name, metric_value, formatted_value, headshot_url, active_years, primary_franchise, tied_player_ids }, strikes_added: 0 }`
  - **Miss / Strike:** `{ is_hit: false, entry: null, strikes_added: 1, reason: "Player is not in the Top 10 for this category." }`
  - **Repeated Guess:** `{ is_hit: false, entry: null, strikes_added: 0, is_repeated: true, reason: "Player has already been submitted in this session." }`

#### 3.2.6 `POST /api/v1/weddle/guess`
- **Request Body:** `{ puzzle_id: string, player_id: string, previous_guesses?: string[] }`
- **Validation Constraints:**
  - `puzzle_id` must reference a valid daily Weddle puzzle or daily date identifier (`PUZZLE_NOT_FOUND`, 404).
  - `player_id` must reference an identifiable NFL player (`INVALID_PLAYER_ID`, 422).
- **Success Response (200 OK):**
  ```json
  {
    "is_correct": false,
    "guesses_remaining": 5,
    "is_game_over": false,
    "comparison": {
      "player": {
        "player_id": "00-0033873",
        "full_name": "Patrick Mahomes",
        "headshot_url": "https://...",
        "team": "KC",
        "position": "QB",
        "side_of_ball": "Offense",
        "conference": "AFC",
        "division": "West",
        "age": 28,
        "height_inches": 74,
        "height_formatted": "6'2\"",
        "jersey_number": 15
      },
      "attributes": {
        "team": { "status": "gray", "direction": null },
        "side_of_ball": { "status": "green", "direction": null },
        "position": { "status": "green", "direction": null },
        "conference": { "status": "green", "direction": null },
        "division": { "status": "gray", "direction": null },
        "age": { "status": "yellow", "direction": "higher" },
        "height": { "status": "green", "direction": null },
        "jersey_number": { "status": "yellow", "direction": "lower" }
      }
    },
    "revealed_target": null
  }
  ```

---

## 4. Algorithmic Specifications & Deterministic Logic

### 4.1 Daily 3x3 Grid Generation Algorithm
1. **RNG Seeding:** Seeded deterministically using `seed = YYYYMMDD + 9973`.
2. **Criteria Taxonomy & Catalog (`criteria_registry.py`):** 60+ production criteria categorized into 6 distinct archetypes:
   - *Hardware & Accolades:* MVP, Super Bowl MVP, OROY, DROY, CPOY, WPMOTY, Pro Bowl (1+, 3+, 5+), All-Pro (1+, 3+), Super Bowl Champion, Hall of Fame.
   - *College Pedigree & Draft Quirks:* Power 5 bluebloods (Alabama, Ohio State, LSU, USC, etc.), 1st Round, Top 5 Overall, Day 2 (Rounds 2-3), Round 4+, Undrafted.
   - *Career Totals:* 10k+ Rush, 40k+ Pass, 300+ Pass TD, 10k+ Rec, 100+ Sacks, 50+ Sacks, etc.
   - *Single-Season Milestones:* 4k/5k Pass Yds, 30 Pass TD, 1k/1.5k Rush Yds, 10/15 Rush TD, 1k/1.5k Rec Yds, 10 Rec TD, 100 Rec, 10/15 Sacks, 6 INTs.
   - *Positional Quirks:* QB 500+ Rush Yds, TE 10+ Rec TD, TE 1,000+ Rec Yds, RB 50+ Rec.
   - *Era / Franchise / Divisions:* 32 Franchises, 8 Divisions (AFC/NFC East/North/South/West), Conferences, Journeymen (3+ or 4+ franchises).
3. **Weighted Dynamic Templates (`grid_templates.py`):**
   - *Template A (Franchise Heavy, 35%):* Rows (2 Franchises + 1 Era/Division/Journeyman) x Cols (1 Franchise + 1 Accolade + 1 Stat).
   - *Template B (College & Draft, 25%):* Rows (1 Franchise + 1 College + 1 Career Stat) x Cols (2 Franchises + 1 Draft Status).
   - *Template C (Accolade & Hardware Milestone, 25%):* Rows (2 Franchises + 1 Hardware) x Cols (1 Division + 1 Season Milestone + 1 College).
   - *Template D (Journeyman & Positional Quirks, 15%):* Rows (1 Franchise + 1 Journeyman/Division + 1 Positional Quirk) x Cols (1 Franchise + 1 Career Stat + 1 Draft/Accolade).
4. **Anti-Clash & Domain Invariants:**
   - Prohibits duplicate criteria, duplicate franchises, and duplicate divisions on any axis.
   - Prohibits franchise-division containment overlap on intersecting cells (e.g., NE Patriots intersecting with AFC East).
   - Prohibits mutually exclusive draft rounds (Round 1 vs Round 4+/Undrafted) and conflicting positions.
5. **Rotation Memory & Recency Fatigue (`rotation_tracker.py`):**
   - Implements decay penalties across 7–14 days history: $\le 3$ days (0.0x weight, locked out), 4–7 days (0.25x weight), 8–14 days (0.60x weight), $>14$ days (1.00x weight).
6. **Intersection Cardinality & Density Bounds:**
   - Pre-indexed bitset/relational intersections are calculated for all 9 cells $(r, c)$:
     $$\forall r, c \in \{0, 1, 2\}: |P(R_r) \cap P(C_c)| \ge 3$$
   - Total log-density $D = \sum_{r, c} \log_{10}(|P(R_r) \cap P(C_c)|)$ evaluated against target range $[12.0, 22.0]$.
7. **Coverage Validation & Fallback Ladder:**
   - Evaluates PostgreSQL database coverage before activation; criteria with $<50$ qualifying players are set to `is_active = False`.
   - Fallback ladder automatically selects next template if candidate attempts fail cardinality constraints within 50 attempts.

### 4.2 Bayesian Rarity Scoring Formula
$$R^*(p, c) = \frac{n(p, c) + M \cdot \pi(p, c)}{N(c) + M} \times 100$$
Where $M = 25$, $\pi(p, c) = \frac{1}{|S_c|}$ (uniform prior over historically valid answers).
Guarantees smooth convergence and eliminates cold-start anomalies for early-day players.

### 4.3 Connections 4x4 Exact Cover Uniqueness Engine (Knuth's Algorithm X)
1. **Deterministic Seeding Formula:**
   $$\text{seed} = \text{int}(\text{target\_date.strftime}("\%Y\%m\%d")) + 7727$$
2. **Category Selection & Tier Balancing:**
   - Samples 1 category from Tier 1 (Bronze), 1 from Tier 2 (Silver), 1 from Tier 3 (Gold), and 1 from Tier 4 (Lombardi Platinum).
   - Resolves matching player pools from PostgreSQL schema.
   - Samples 4 candidate players per tier, injecting cross-category distractor tension (e.g., a Tier 2 player satisfying the Tier 1 criterion).
3. **Exact Cover Solver Formulation:**
   - Let universe $U = \{p_0, p_1, \dots, p_{15}\}$ be the 16 candidate board items ($|U| = 16$).
   - For every active category $C_j$ in the taxonomy, find all valid 4-item subsets $S_{j, k} \subseteq C_j \cap U$ where $|S_{j, k}| = 4$.
   - Represent each valid 4-element subset as a 16-bit integer mask $M \in [0, 2^{16}-1]$ with Hamming weight $w(M) = 4$.
   - Execute Knuth's Algorithm X using Dancing Links (DLX) and Bitset-accelerated backtracking with Minimum Remaining Values (MRV) branch selection.
4. **Strict Partition Uniqueness Invariant:**
   - The puzzle board is valid if and only if the total count of disjoint exact covers is **strictly 1**:
     $$\text{ExactCovers}(U) = \{ \{G_1, G_2, G_3, G_4\} \mid G_a \cap G_b = \emptyset \, \forall a \ne b, \; \bigcup_{k=1}^4 G_k = U \} \implies |\text{ExactCovers}(U)| = 1$$
   - Any candidate board where distractors produce $\ge 2$ valid 4x4 partitions is **rejected as ambiguous**.
   - Validated puzzles are persisted to `daily_puzzles` with JSONB payload and SHA-256 solution checksum.

### 4.4 Top 10 Leaderboard Generation & Ranking Invariants
1. **Deterministic Seeding Formula:**
   $$\text{seed} = \text{int}(\text{target\_date.strftime}("\%Y\%m\%d")) + 4409$$
2. **Archetype Family Rotation:**
   Rotates through 4 discrete archetype families by modulo arithmetic on calendar day ordinal index:
   - `SINGLE_SEASON_MILESTONE`: Post-2010/2015 individual season milestones.
   - `CHRONOLOGICAL_ACCOLADE`: Reverse chronological major NFL awards (rank 1 = most recent season).
   - `RECENT_DRAFT_PEDIGREE`: Strictly post-2015 draft classes.
   - `ALL_TIME_HISTORICAL_LEADERBOARD`: Universal recognizable all-time statistical totals.
3. **Strict Tie-Breaking Invariants:**
   - Secondary tie-breaker evaluates:
     1. Fewer games played in season/career (higher efficiency per appearance),
     2. Secondary statistical criteria,
     3. Chronological recency.
   - All players sharing the exact qualifying metric threshold at a rank boundary $\le 10$ are indexed in `tied_player_ids` and are evaluated as valid hits.
4. **Validation Performance Guarantee:**
   Evaluates player guesses in $O(1)$ against precomputed ranked slots with fuzzy normalization and duplicate guess deduplication.

### 4.5 Guess the Player (Weddle) Deterministic Selection & Comparison Engine
1. **Deterministic Seeding Formula:**
   $$\text{seed} = \text{int}(\text{target\_date.strftime}("\%Y\%m\%d")) + 5503$$
2. **Active Player Pool Eligibility Invariants:**
   - Must be an active NFL player (`is_active == true`).
   - Must have complete metadata: non-null team, jersey number, height in inches, age, and position code.
   - Practice-squad-only or incomplete records are excluded from the target selection pool.
3. **Attribute Comparison Engine Rules:**
   - `team`: `green` if exact franchise match, else `gray`.
   - `side_of_ball`: `green` if both are Offense or both Defense, else `gray`.
   - `position`: `green` if exact match. `yellow` if in same positional subgroup:
     - OL: `OT`, `T`, `OG`, `G`, `C`, `OL`, `LT`, `RT`, `LG`, `RG`
     - DB: `CB`, `S`, `FS`, `SS`, `DB`
     - DL / Edge: `DE`, `DT`, `NT`, `DL`, `EDGE`
     - LB: `LB`, `ILB`, `OLB`, `MLB`
     - Receivers: `WR`, `TE`
     - Backfield: `RB`, `FB`
     - Otherwise `gray`.
   - `conference`: `green` if both AFC or both NFC, else `gray`.
   - `division`: `green` if both East, both North, both South, or both West, else `gray`.
   - `age`: `green` (direction: `null`) if equal. If $|age_{\text{guess}} - age_{\text{target}}| \le 2$: `yellow`. Else `gray`. Direction is `higher` if $age_{\text{target}} > age_{\text{guess}}$, `lower` if $age_{\text{target}} < age_{\text{guess}}$.
   - `height`: `green` (direction: `null`) if equal. If $|height_{\text{guess}} - height_{\text{target}}| \le 2$: `yellow`. Else `gray`. Direction is `higher` if $height_{\text{target}} > height_{\text{guess}}$, `lower` if $height_{\text{target}} < height_{\text{guess}}$.
   - `jersey_number`: `green` (direction: `null`) if equal. If $|jersey_{\text{guess}} - jersey_{\text{target}}| \le 2$: `yellow`. Else `gray`. Direction is `higher` if $jersey_{\text{target}} > jersey_{\text{guess}}$, `lower` if $jersey_{\text{target}} < jersey_{\text{guess}}$.

---

## 5. Architectural & Deployment Topology Spec

### 5.1 Monorepo Layout (Turborepo)
- `apps/web`: Next.js 14+ (App Router, Tailwind CSS, Fuse.js / Trie in-memory search)
- `apps/api`: FastAPI (Python 3.11+, SQLAlchemy 2.0 async, Redis cache)
- `packages/contracts`: Shared TypeScript interfaces generated from OpenAPI spec
- `packages/etl`: `nfl_data_py` extraction, relational reconciliation, puzzle generator

### 5.2 Client LocalStorage Schema (`nfl_games_state_v1`)
Tracks active puzzle date, remaining guesses/strikes, revealed cells, and HMAC-SHA256 tamper-detection checksum. Automatically archives and resets upon UTC date transition.

### 5.3 ETL Ingestion Semantics
Idempotent UPSERT statements on conflict with canonical NFL GSIS identifiers. Staging -> Reconciler -> Relational DB -> CDN static search catalog deployment.

### 5.4 Player Catalog & Search Index Specification
- **Canonical Career Span Rules:**
  - `rookie_year`: Sourced from nflverse canonical `rookie_season` or `draft_year`, falling back to minimum season year in historical franchise stints.
  - `final_year`: Sourced from canonical retirement/last active season metadata. For active players, `final_year = NULL` and `is_active = TRUE`.
  - Inactive Player Stint Fallback: If an inactive/retired player has `final_year IS NULL`, search index serialization dynamically evaluates `final_year = MAX(season_year)` across all regular season stints (`player_team_stints`).
- **Frontend Display Contract (`PlayerSearchModal`):**
  - Active (`is_active === true`): `${rookie_year} - Present`
  - Retired (`is_active === false` and `final_year != null`): `${rookie_year} - ${final_year}`
  - Guardrail (`is_active === false` and `final_year == null`): `${rookie_year} - Unknown`

