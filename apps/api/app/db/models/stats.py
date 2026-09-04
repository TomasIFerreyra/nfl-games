from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.franchise import Franchise, TeamSeason
    from app.db.models.player import Player


class PlayerSeasonStat(Base):
    """
    Aggregated regular season individual statistics per player, team-manifestation, and season.
    Contains partial indexes targeting common Grid milestone thresholds (1k rush, 4k pass, etc.).
    """
    __tablename__ = "player_season_stats"
    __table_args__ = (
        UniqueConstraint(
            "player_id", "team_season_id", "season_year",
            name="uq_stats_player_team_year"
        ),
        Index(
            "idx_stats_pass_yds",
            "passing_yards",
            postgresql_where=text("passing_yards >= 3000"),
        ),
        Index(
            "idx_stats_rush_yds",
            "rushing_yards",
            postgresql_where=text("rushing_yards >= 1000"),
        ),
        Index(
            "idx_stats_rec_yds",
            "receiving_yards",
            postgresql_where=text("receiving_yards >= 1000"),
        ),
        Index(
            "idx_stats_sacks",
            "sacks",
            postgresql_where=text("sacks >= 10.0"),
        ),
    )

    stat_id: Mapped[int] = mapped_column(
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
    team_season_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("team_seasons.team_season_id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        index=True
    )
    passing_yards: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    passing_tds: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0
    )
    interceptions: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0
    )
    rushing_yards: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    rushing_tds: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0
    )
    receptions: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0
    )
    receiving_yards: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    receiving_tds: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0
    )
    sacks: Mapped[Decimal] = mapped_column(
        Numeric(4, 1),
        nullable=False,
        default=Decimal("0.0"),
        comment="Official regular season sacks (post-1982)"
    )
    defensive_interceptions: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0
    )

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="season_stats")
    team_season: Mapped["TeamSeason"] = relationship("TeamSeason", back_populates="player_stats")

    def __repr__(self) -> str:
        return (
            f"<PlayerSeasonStat(player='{self.player_id}', "
            f"team='{self.team_season_id}', year={self.season_year})>"
        )


class Accolade(Base):
    """
    Formal career and seasonal honors (Pro Bowl, First-Team All-Pro, MVP, Super Bowl, HoF).
    """
    __tablename__ = "accolades"
    __table_args__ = (
        Index("idx_accolades_lookup", "accolade_type", "season_year", "player_id"),
    )

    accolade_id: Mapped[int] = mapped_column(
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
    franchise_id: Mapped[Optional[str]] = mapped_column(
        String(10),
        ForeignKey("franchises.franchise_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Associated franchise when honor was earned; null for general HoF"
    )
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="Season of honor (or induction year for HoF)"
    )
    accolade_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="PRO_BOWL, FIRST_TEAM_ALL_PRO, MVP, SUPER_BOWL_CHAMPION, HALL_OF_FAME, etc."
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Subcategory (e.g., OFFENSE, DEFENSE)"
    )

    # Relationships
    player: Mapped["Player"] = relationship("Player", back_populates="accolades")
    franchise: Mapped[Optional["Franchise"]] = relationship("Franchise", back_populates="accolades")

    def __repr__(self) -> str:
        return (
            f"<Accolade(player='{self.player_id}', type='{self.accolade_type}', year={self.season_year})>"
        )
