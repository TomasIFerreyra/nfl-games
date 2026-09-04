import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.franchise import Franchise
    from app.db.models.puzzle import AggregatedAnswerStats
    from app.db.models.stats import Accolade, PlayerSeasonStat


class Player(Base):
    """
    Canonical player directory for active and historical NFL players.
    Indexed with GIN trigram for sub-10ms autocomplete search fallback.
    """
    __tablename__ = "players"
    __table_args__ = (
        Index(
            "idx_players_full_name_trgm",
            "full_name",
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ),
        Index(
            "idx_players_pos_active",
            "primary_position",
            "is_active",
        ),
    )

    player_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Canonical UUID string identifier"
    )
    gsis_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        comment="Official NFL GSIS player identifier (e.g., '00-0033873')"
    )
    pfr_id: Mapped[Optional[str]] = mapped_column(
        String(40),
        unique=True,
        nullable=True,
        index=True,
        comment="Pro-Football-Reference identifier (e.g., 'MahoPa00')"
    )
    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name (e.g., 'Patrick Mahomes')"
    )
    first_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )
    last_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )
    primary_position: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Primary position code (QB, RB, WR, TE, DE, etc.)"
    )
    draft_year: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True
    )
    draft_round: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True
    )
    draft_overall: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True
    )
    college: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    rookie_year: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False
    )
    final_year: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Null if player is currently active"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    headshot_url: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # Relationships
    stints: Mapped[List["PlayerTeamStint"]] = relationship(
        "PlayerTeamStint",
        back_populates="player",
        cascade="all, delete-orphan",
        order_by="PlayerTeamStint.season_year.desc()"
    )
    season_stats: Mapped[List["PlayerSeasonStat"]] = relationship(
        "PlayerSeasonStat",
        back_populates="player",
        cascade="all, delete-orphan",
        order_by="PlayerSeasonStat.season_year.desc()"
    )
    accolades: Mapped[List["Accolade"]] = relationship(
        "Accolade",
        back_populates="player",
        cascade="all, delete-orphan",
        order_by="Accolade.season_year.desc()"
    )
    aggregated_answers: Mapped[List["AggregatedAnswerStats"]] = relationship(
        "AggregatedAnswerStats",
        back_populates="player",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Player(id='{self.player_id}', name='{self.full_name}', pos='{self.primary_position}')>"


class PlayerTeamStint(Base):
    """
    Tracks regular season game appearances per player, franchise, and season.
    Crucial domain rule: A player is only credited for a franchise if games_played >= 1.
    """
    __tablename__ = "player_team_stints"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "franchise_id", "season_year",
            name="uq_player_franchise_season"
        ),
        CheckConstraint("games_played >= 0", name="chk_stints_games_played"),
        CheckConstraint("games_started >= 0", name="chk_stints_games_started"),
        Index(
            "idx_stints_lookup",
            "franchise_id",
            "games_played",
            postgresql_where=text("games_played > 0"),
        ),
    )

    stint_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )
    player_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("players.player_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    franchise_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("franchises.franchise_id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False
    )
    games_played: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Official regular season game appearances"
    )
    games_started: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0
    )

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="stints")
    franchise: Mapped["Franchise"] = relationship("Franchise", back_populates="player_stints")

    def __repr__(self) -> str:
        return (
            f"<PlayerTeamStint(player='{self.player_id}', "
            f"franchise='{self.franchise_id}', year={self.season_year}, gp={self.games_played})>"
        )
