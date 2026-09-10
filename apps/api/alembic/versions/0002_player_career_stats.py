"""Add player_career_stats table

Revision ID: 0002_player_career_stats
Revises: 0001_initial_schema
Create Date: 2026-09-10 14:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_player_career_stats"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_career_stats",
        sa.Column("player_id", sa.String(length=36), nullable=False, comment="Foreign key to players.player_id"),
        sa.Column("seasons_played", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("games_played", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("passing_yards", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("passing_tds", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("interceptions", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("rushing_yards", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rushing_tds", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("receptions", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("receiving_yards", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("receiving_tds", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("sacks", sa.Numeric(precision=5, scale=1), server_default=sa.text("0.0"), nullable=False, comment="Career official sacks"),
        sa.Column("defensive_interceptions", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("pro_bowls", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("all_pros", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("franchises_played_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False, comment="Count of distinct franchises where player logged >= 1 game"),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.player_id"],
            name="fk_player_career_stats_player_id_players",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_id", name="pk_player_career_stats"),
    )
    op.create_index("idx_career_rush_yds", "player_career_stats", ["rushing_yards"])
    op.create_index("idx_career_pass_yds", "player_career_stats", ["passing_yards"])
    op.create_index("idx_career_rec_yds", "player_career_stats", ["receiving_yards"])
    op.create_index("idx_career_sacks", "player_career_stats", ["sacks"])
    op.create_index("idx_career_franchises_cnt", "player_career_stats", ["franchises_played_count"])


def downgrade() -> None:
    op.drop_index("idx_career_franchises_cnt", table_name="player_career_stats")
    op.drop_index("idx_career_sacks", table_name="player_career_stats")
    op.drop_index("idx_career_rec_yds", table_name="player_career_stats")
    op.drop_index("idx_career_pass_yds", table_name="player_career_stats")
    op.drop_index("idx_career_rush_yds", table_name="player_career_stats")
    op.drop_table("player_career_stats")
