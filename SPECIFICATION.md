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
- **Board Composition:** A 16-element set $S = \{e_1, e_2, \dots, e_{16}\}$ of NFL entities (typically players, coaches, or franchises).
- **Partition Invariant:** There exists exactly one unique partition of $S$ into 4 disjoint subsets $\{G_1, G_2, G_3, G_4\}$ such that $|G_k| = 4$ for all $k \in \{1, 2, 3, 4\}$, and each $G_k$ satisfies a distinct thematic rule $T_k$.
- **Difficulty Grading:** 4 tiers color-coded by complexity:
  - *Tier 1 (Yellow):* Straightforward historical facts (e.g., "Heisman Trophy Winning Quarterbacks").
  - *Tier 2 (Green):* Statistical thresholds (e.g., "5,000+ Passing Yards in a Single Season").
  - *Tier 3 (Blue):* Common teammates, drafts, or coaching tree overlaps (e.g., "2004 NFL Draft Round 1 QBs").
  - *Tier 4 (Purple):* Cryptic, wordplay, jersey number quirks, or obscure cross-franchise trivia (e.g., "Players with surnames that are US Capitals").
- **Attempt Budget:** 4 incorrect guess strikes before game over.
- **"One Away" Heuristic:** If a submitted 4-element guess overlaps with any target group $G_k$ by exactly 3 elements ($|G_{\text{guess}} \cap G_k| = 3$), the system returns a non-penalizing advisory signal: `is_one_away: true`.

#### 1.1.4 Top 10 Leaderboard Trivia
- **Prompt:** An ordered statistical or historical query (e.g., "All-Time NFL Career Sacks Leaders").
- **Board Representation:** 10 masked slots ranked 1 to 10.
- **Guess Evaluation:** User submits player names. If player $P \in \text{Top10}$, reveal slot with rank, player name, and metric value.
- **Strike Budget:** 3 incorrect strikes (players outside the top 10).
- **Completion States:** Solved (all 10 revealed), Struck Out (3 strikes reached), or Surrendered. Final score weighted by rank discovery and strike penalty.

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
- Body: `{ puzzle_id, selected_item_ids: [id1, id2, id3, id4] }`
- Returns: `{ is_match, group: { group_id, tier, title, explanation, item_ids }, is_one_away }`

#### 3.2.5 `POST /api/v1/top10/guess`
- Body: `{ puzzle_id, player_id }`
- Returns: `{ is_hit, entry: { rank, player_id, player_name, metric_value, formatted_value }, strikes_added, current_strikes, is_game_over }`

---

## 4. Algorithmic Specifications & Deterministic Logic

### 4.1 Daily 3x3 Grid Generation Algorithm
1. **RNG Seeding:** Seeded deterministically using `seed = YYYYMMDD + 9973`.
2. **Template Selection:** 2 Franchises + 1 Stat for Rows; 1 Franchise + 1 Accolade + 1 Draft Round for Columns.
3. **Intersection Cardinality Bound:** Pre-indexed bitset intersections are calculated for all 9 cells $(r, c)$.
   $$\forall r, c \in \{0, 1, 2\}: |P(R_r) \cap P(C_c)| \ge 3$$
4. **Density Bound:** Total log-density $D = \sum_{r, c} \log_{10}(|P(R_r) \cap P(C_c)|)$ must fall within $[12.0, 22.0]$.

### 4.2 Bayesian Rarity Scoring Formula
$$R^*(p, c) = \frac{n(p, c) + M \cdot \pi(p, c)}{N(c) + M} \times 100$$
Where $M = 25$, $\pi(p, c) = \frac{1}{|S_c|}$ (uniform prior over historically valid answers).
Guarantees smooth convergence and eliminates cold-start anomalies for early-day players.

### 4.3 Connections 4x4 Uniqueness Verification
Validated via Knuth's Algorithm X (Exact Cover). The generator verifies that across all valid 4-element groupings in the domain, there is **strictly one unique 4-way disjoint partition** of the 16 elements.

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
