import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.player import Player


class DailyPuzzle(Base):
    """
    Central daily puzzle registry for all mini-game modes.
    Contains verified, unsolvable-proof puzzle payloads with SHA-256 solution hashes.
    """
    __tablename__ = "daily_puzzles"
    __table_args__ = (
        UniqueConstraint("target_date", "game_type", name="uq_daily_puzzles_date_type"),
        CheckConstraint(
            "game_type IN ('GRID', 'REVERSE_GRID', 'CONNECTIONS', 'TOP10')",
            name="chk_puzzle_game_type",
        ),
        Index("idx_daily_puzzles_jsonb", "puzzle_data", postgresql_using="gin"),
    )

    puzzle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Immutable puzzle instance UUID"
    )
    target_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Target UTC calendar release date"
    )
    game_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="GRID, REVERSE_GRID, CONNECTIONS, or TOP10"
    )
    puzzle_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monotonically increasing puzzle sequence number"
    )
    puzzle_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full JSON payload conforming to game-type specific JSON Schema"
    )
    solution_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 checksum of correct solution set for server-side verification"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp()
    )

    # Relationships
    submissions: Mapped[List["GameSubmission"]] = relationship(
        "GameSubmission",
        back_populates="puzzle",
        cascade="all, delete-orphan"
    )
    answer_stats: Mapped[List["AggregatedAnswerStats"]] = relationship(
        "AggregatedAnswerStats",
        back_populates="puzzle",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DailyPuzzle(id={self.puzzle_id}, date={self.target_date}, type='{self.game_type}')>"


class GameSubmission(Base):
    """
    Session-level game submission records for auditability and leaderboard computations.
    """
    __tablename__ = "game_submissions"
    __table_args__ = (
        Index("idx_submissions_puzzle_created", "puzzle_id", "created_at"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    puzzle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_puzzles.puzzle_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    session_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Client UUID or hashed session identifier"
    )
    submission_payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full state snapshot at submission time"
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    total_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Final calculated score (rarity sum for Grid, score for Top10, etc.)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp()
    )

    # Relationships
    puzzle: Mapped["DailyPuzzle"] = relationship("DailyPuzzle", back_populates="submissions")

    def __repr__(self) -> str:
        return f"<GameSubmission(id={self.submission_id}, puzzle={self.puzzle_id}, done={self.is_completed})>"


class AggregatedAnswerStats(Base):
    """
    Tracks answer frequencies per cell in Grid puzzles to dynamically compute empirical rarity.
    """
    __tablename__ = "aggregated_answer_stats"
    __table_args__ = (
        UniqueConstraint(
            "puzzle_id", "cell_identifier", "player_id",
            name="uq_answer_stats_puzzle_cell_player"
        ),
        Index(
            "idx_answer_stats_ranking",
            "puzzle_id",
            "cell_identifier",
            "selection_count",
        ),
    )

    stat_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )
    puzzle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_puzzles.puzzle_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    cell_identifier: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Coordinate code: r0_c0, r0_c1, ..., r2_c2"
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("players.player_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    selection_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=1,
        comment="Total valid submissions selecting this player for this cell"
    )
    pick_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Pre-calculated percentage share of all picks for this cell"
    )

    # Relationships
    puzzle: Mapped["DailyPuzzle"] = relationship("DailyPuzzle", back_populates="answer_stats")
    player: Mapped["Player"] = relationship("Player", back_populates="aggregated_answers")

    def __repr__(self) -> str:
        return (
            f"<AggregatedAnswerStats(puzzle={self.puzzle_id}, cell='{self.cell_identifier}', "
            f"player='{self.player_id}', picks={self.selection_count})>"
        )
