"""Initial schema setup for NFL Daily Mini-Games Platform

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-04 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 0. PostgreSQL Extensions
    # -------------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # -------------------------------------------------------------------------
    # 1. Franchises Table
    # -------------------------------------------------------------------------
    op.create_table(
        "franchises",
        sa.Column("franchise_id", sa.String(length=10), nullable=False, comment="Canonical Franchise Code (e.g., TEN, LAR, BAL, CLE, WAS)"),
        sa.Column("canonical_name", sa.String(length=100), nullable=False, comment="Current canonical team brand name"),
        sa.Column("established_year", sa.SmallInteger(), nullable=False, comment="NFL foundation or entry year"),
        sa.CheckConstraint("established_year >= 1920", name="chk_franchise_established_year"),
        sa.PrimaryKeyConstraint("franchise_id", name="pk_franchises"),
    )

    # -------------------------------------------------------------------------
    # 2. Team Seasons Table
    # -------------------------------------------------------------------------
    op.create_table(
        "team_seasons",
        sa.Column("team_season_id", sa.String(length=10), nullable=False, comment="Natural composite key format: {abbr}_{year}"),
        sa.Column("franchise_id", sa.String(length=10), nullable=False),
        sa.Column("season_year", sa.SmallInteger(), nullable=False, comment="NFL season year"),
        sa.Column("team_name", sa.String(length=100), nullable=False, comment="Historical seasonal name"),
        sa.Column("team_abbr", sa.String(length=5), nullable=False, comment="Official historical abbreviation"),
        sa.CheckConstraint("season_year BETWEEN 1920 AND 2100", name="chk_team_season_year"),
        sa.ForeignKeyConstraint(
            ["franchise_id"],
            ["franchises.franchise_id"],
            name="fk_team_seasons_franchise_id_franchises",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("team_season_id", name="pk_team_seasons"),
        sa.UniqueConstraint("franchise_id", "season_year", name="uq_team_seasons_franchise_year"),
    )
    op.create_index("ix_team_seasons_franchise_id", "team_seasons", ["franchise_id"])

    # -------------------------------------------------------------------------
    # 3. Players Table
    # -------------------------------------------------------------------------
    op.create_table(
        "players",
        sa.Column("player_id", sa.String(length=36), nullable=False, comment="Canonical UUID string identifier"),
        sa.Column("gsis_id", sa.String(length=50), nullable=True, comment="Official NFL GSIS player identifier"),
        sa.Column("pfr_id", sa.String(length=20), nullable=True, comment="Pro-Football-Reference identifier"),
        sa.Column("full_name", sa.String(length=100), nullable=False, comment="Display name"),
        sa.Column("first_name", sa.String(length=50), nullable=False),
        sa.Column("last_name", sa.String(length=50), nullable=False),
        sa.Column("primary_position", sa.String(length=10), nullable=False, comment="Primary position code"),
        sa.Column("draft_year", sa.SmallInteger(), nullable=True),
        sa.Column("draft_round", sa.SmallInteger(), nullable=True),
        sa.Column("draft_overall", sa.SmallInteger(), nullable=True),
        sa.Column("college", sa.String(length=100), nullable=True),
        sa.Column("rookie_year", sa.SmallInteger(), nullable=False),
        sa.Column("final_year", sa.SmallInteger(), nullable=True, comment="Null if active"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("headshot_url", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("player_id", name="pk_players"),
        sa.UniqueConstraint("gsis_id", name="uq_players_gsis_id"),
        sa.UniqueConstraint("pfr_id", name="uq_players_pfr_id"),
    )
    op.create_index("ix_players_gsis_id", "players", ["gsis_id"])
    op.create_index("ix_players_pfr_id", "players", ["pfr_id"])
    op.create_index(
        "idx_players_full_name_trgm",
        "players",
        ["full_name"],
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.create_index("idx_players_pos_active", "players", ["primary_position", "is_active"])

    # -------------------------------------------------------------------------
    # 4. Player Team Stints Table
    # -------------------------------------------------------------------------
    op.create_table(
        "player_team_stints",
        sa.Column("stint_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("franchise_id", sa.String(length=10), nullable=False),
        sa.Column("season_year", sa.SmallInteger(), nullable=False),
        sa.Column("games_played", sa.SmallInteger(), server_default=sa.text("0"), nullable=False, comment="Official regular season game appearances"),
        sa.Column("games_started", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint("games_played >= 0", name="chk_stints_games_played"),
        sa.CheckConstraint("games_started >= 0", name="chk_stints_games_started"),
        sa.ForeignKeyConstraint(
            ["franchise_id"],
            ["franchises.franchise_id"],
            name="fk_player_team_stints_franchise_id_franchises",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.player_id"],
            name="fk_player_team_stints_player_id_players",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("stint_id", name="pk_player_team_stints"),
        sa.UniqueConstraint("player_id", "franchise_id", "season_year", name="uq_player_franchise_season"),
    )
    op.create_index("ix_player_team_stints_player_id", "player_team_stints", ["player_id"])
    op.create_index("ix_player_team_stints_franchise_id", "player_team_stints", ["franchise_id"])
    op.create_index(
        "idx_stints_lookup",
        "player_team_stints",
        ["franchise_id", "games_played"],
        postgresql_where=sa.text("games_played > 0"),
    )

    # -------------------------------------------------------------------------
    # 5. Player Season Stats Table
    # -------------------------------------------------------------------------
    op.create_table(
        "player_season_stats",
        sa.Column("stat_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("team_season_id", sa.String(length=10), nullable=False),
        sa.Column("season_year", sa.SmallInteger(), nullable=False),
        sa.Column("passing_yards", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("passing_tds", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("interceptions", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("rushing_yards", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rushing_tds", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("receptions", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("receiving_yards", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("receiving_tds", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("sacks", sa.Numeric(precision=4, scale=1), server_default=sa.text("0.0"), nullable=False, comment="Official regular season sacks (post-1982)"),
        sa.Column("defensive_interceptions", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.player_id"],
            name="fk_player_season_stats_player_id_players",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_season_id"],
            ["team_seasons.team_season_id"],
            name="fk_player_season_stats_team_season_id_team_seasons",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("stat_id", name="pk_player_season_stats"),
        sa.UniqueConstraint("player_id", "team_season_id", "season_year", name="uq_stats_player_team_year"),
    )
    op.create_index("ix_player_season_stats_player_id", "player_season_stats", ["player_id"])
    op.create_index("ix_player_season_stats_team_season_id", "player_season_stats", ["team_season_id"])
    op.create_index("ix_player_season_stats_season_year", "player_season_stats", ["season_year"])
    op.create_index(
        "idx_stats_pass_yds",
        "player_season_stats",
        ["passing_yards"],
        postgresql_where=sa.text("passing_yards >= 3000"),
    )
    op.create_index(
        "idx_stats_rush_yds",
        "player_season_stats",
        ["rushing_yards"],
        postgresql_where=sa.text("rushing_yards >= 1000"),
    )
    op.create_index(
        "idx_stats_rec_yds",
        "player_season_stats",
        ["receiving_yards"],
        postgresql_where=sa.text("receiving_yards >= 1000"),
    )
    op.create_index(
        "idx_stats_sacks",
        "player_season_stats",
        ["sacks"],
        postgresql_where=sa.text("sacks >= 10.0"),
    )

    # -------------------------------------------------------------------------
    # 6. Accolades Table
    # -------------------------------------------------------------------------
    op.create_table(
        "accolades",
        sa.Column("accolade_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("franchise_id", sa.String(length=10), nullable=True),
        sa.Column("season_year", sa.SmallInteger(), nullable=False, comment="Season of honor"),
        sa.Column("accolade_type", sa.String(length=50), nullable=False, comment="PRO_BOWL, FIRST_TEAM_ALL_PRO, MVP, etc."),
        sa.Column("category", sa.String(length=50), nullable=True, comment="Subcategory"),
        sa.ForeignKeyConstraint(
            ["franchise_id"],
            ["franchises.franchise_id"],
            name="fk_accolades_franchise_id_franchises",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.player_id"],
            name="fk_accolades_player_id_players",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("accolade_id", name="pk_accolades"),
    )
    op.create_index("ix_accolades_player_id", "accolades", ["player_id"])
    op.create_index("ix_accolades_franchise_id", "accolades", ["franchise_id"])
    op.create_index("idx_accolades_lookup", "accolades", ["accolade_type", "season_year", "player_id"])

    # -------------------------------------------------------------------------
    # 7. Daily Puzzles Table
    # -------------------------------------------------------------------------
    op.create_table(
        "daily_puzzles",
        sa.Column("puzzle_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False, comment="Target UTC calendar date"),
        sa.Column("game_type", sa.String(length=20), nullable=False, comment="GRID, REVERSE_GRID, CONNECTIONS, TOP10"),
        sa.Column("puzzle_number", sa.Integer(), nullable=False, comment="Monotonic sequence number"),
        sa.Column("puzzle_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="JSON payload conforming to schema"),
        sa.Column("solution_hash", sa.String(length=64), nullable=False, comment="SHA-256 hash of solution set"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("game_type IN ('GRID', 'REVERSE_GRID', 'CONNECTIONS', 'TOP10')", name="chk_puzzle_game_type"),
        sa.PrimaryKeyConstraint("puzzle_id", name="pk_daily_puzzles"),
        sa.UniqueConstraint("target_date", "game_type", name="uq_daily_puzzles_date_type"),
    )
    op.create_index("idx_daily_puzzles_jsonb", "daily_puzzles", ["puzzle_data"], postgresql_using="gin")

    # -------------------------------------------------------------------------
    # 8. Game Submissions Table
    # -------------------------------------------------------------------------
    op.create_table(
        "game_submissions",
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("puzzle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_fingerprint", sa.String(length=64), nullable=False, comment="Client UUID or hashed session identifier"),
        sa.Column("submission_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("total_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["puzzle_id"],
            ["daily_puzzles.puzzle_id"],
            name="fk_game_submissions_puzzle_id_daily_puzzles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("submission_id", name="pk_game_submissions"),
    )
    op.create_index("ix_game_submissions_puzzle_id", "game_submissions", ["puzzle_id"])
    op.create_index("ix_game_submissions_session_fingerprint", "game_submissions", ["session_fingerprint"])
    op.create_index("idx_submissions_puzzle_created", "game_submissions", ["puzzle_id", "created_at"])

    # -------------------------------------------------------------------------
    # 9. Aggregated Answer Stats Table
    # -------------------------------------------------------------------------
    op.create_table(
        "aggregated_answer_stats",
        sa.Column("stat_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("puzzle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cell_identifier", sa.String(length=10), nullable=False, comment="Coordinate code: r0_c0, etc."),
        sa.Column("player_id", sa.String(length=36), nullable=False),
        sa.Column("selection_count", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("pick_percentage", sa.Numeric(precision=5, scale=2), server_default=sa.text("0.00"), nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.player_id"],
            name="fk_aggregated_answer_stats_player_id_players",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["puzzle_id"],
            ["daily_puzzles.puzzle_id"],
            name="fk_aggregated_answer_stats_puzzle_id_daily_puzzles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("stat_id", name="pk_aggregated_answer_stats"),
        sa.UniqueConstraint("puzzle_id", "cell_identifier", "player_id", name="uq_answer_stats_puzzle_cell_player"),
    )
    op.create_index("ix_aggregated_answer_stats_puzzle_id", "aggregated_answer_stats", ["puzzle_id"])
    op.create_index("ix_aggregated_answer_stats_player_id", "aggregated_answer_stats", ["player_id"])
    op.create_index("idx_answer_stats_ranking", "aggregated_answer_stats", ["puzzle_id", "cell_identifier", "selection_count"])


def downgrade() -> None:
    # Drop tables in reverse order of foreign key dependencies
    op.drop_table("aggregated_answer_stats")
    op.drop_table("game_submissions")
    op.drop_table("daily_puzzles")
    op.drop_table("accolades")
    op.drop_table("player_season_stats")
    op.drop_table("player_team_stints")
    op.drop_table("players")
    op.drop_table("team_seasons")
    op.drop_table("franchises")
