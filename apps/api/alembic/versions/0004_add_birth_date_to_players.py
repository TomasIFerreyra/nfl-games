"""Add birth_date column and dynamic age view to players table

Revision ID: 0004_add_birth_date_to_players
Revises: 0003_add_weddle_game_type
Create Date: 2026-09-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_birth_date_to_players"
down_revision: Union[str, None] = "0003_add_weddle_game_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add canonical birth_date column to players table
    op.add_column(
        "players",
        sa.Column(
            "birth_date",
            sa.Date(),
            nullable=True,
            comment="Canonical date of birth (YYYY-MM-DD)"
        ),
    )
    op.create_index("ix_players_birth_date", "players", ["birth_date"])

    # 2. Create database view computing dynamic current_age relative to CURRENT_DATE
    # Note: PostgreSQL generated columns cannot use non-immutable functions like CURRENT_DATE.
    # Therefore, a database view provides zero-cost dynamic real-time age computation.
    op.execute("""
        CREATE OR REPLACE VIEW vw_players_with_age AS
        SELECT 
            p.*,
            CASE 
                WHEN p.birth_date IS NOT NULL THEN
                    EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birth_date))::INT
                ELSE NULL
            END AS current_age
        FROM players p;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_players_with_age;")
    op.drop_index("ix_players_birth_date", table_name="players")
    op.drop_column("players", "birth_date")
