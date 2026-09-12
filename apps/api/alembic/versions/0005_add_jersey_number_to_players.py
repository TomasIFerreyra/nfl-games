"""Add jersey_number column to players table and refresh vw_players_with_age

Revision ID: 0005_add_jersey_number
Revises: 0004_add_birth_date_to_players
Create Date: 2026-09-11 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_jersey_number"
down_revision: Union[str, None] = "0004_add_birth_date_to_players"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add jersey_number column to players table
    op.add_column(
        "players",
        sa.Column(
            "jersey_number",
            sa.SmallInteger(),
            nullable=True,
            comment="Active NFL jersey number (0-99)"
        ),
    )

    # 2. Recreate vw_players_with_age view (must drop first because column positions changed)
    op.execute("DROP VIEW IF EXISTS vw_players_with_age;")
    op.execute("""
        CREATE VIEW vw_players_with_age AS
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
    op.drop_column("players", "jersey_number")
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
