"""Add WEDDLE to daily_puzzles game_type check constraint

Revision ID: 0003_add_weddle_game_type
Revises: 0002_player_career_stats
Create Date: 2026-09-11 14:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_add_weddle_game_type"
down_revision: Union[str, None] = "0002_player_career_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("chk_puzzle_game_type", "daily_puzzles", type_="check")
    op.create_check_constraint(
        "chk_puzzle_game_type",
        "daily_puzzles",
        "game_type IN ('GRID', 'REVERSE_GRID', 'CONNECTIONS', 'TOP10', 'WEDDLE')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_puzzle_game_type", "daily_puzzles", type_="check")
    op.create_check_constraint(
        "chk_puzzle_game_type",
        "daily_puzzles",
        "game_type IN ('GRID', 'REVERSE_GRID', 'CONNECTIONS', 'TOP10')",
    )
