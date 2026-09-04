from typing import TYPE_CHECKING, List
from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.player import PlayerTeamStint
    from app.db.models.stats import Accolade, PlayerSeasonStat


class Franchise(Base):
    """
    Represents continuous NFL franchise entities surviving relocation and rebranding.
    Examples:
        TEN -> Houston Oilers (1960-1996), Tennessee Oilers (1997-1998), Tennessee Titans (1999+)
        LAR -> Cleveland Rams (1937-1945), LA Rams (1946-1994, 2016+), St. Louis Rams (1995-2015)
        BAL -> Baltimore Ravens (1996+ expansion, separated from CLE history per 1996 settlement)
        CLE -> Cleveland Browns (1946-1995, 1999+ reactivation)
        WAS -> Boston Braves/Redskins (1932-1936), Washington Redskins/Football Team/Commanders
    """
    __tablename__ = "franchises"
    __table_args__ = (
        CheckConstraint("established_year >= 1920", name="chk_franchise_established_year"),
    )

    franchise_id: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        comment="Canonical Franchise Code (e.g., TEN, LAR, BAL, CLE, WAS)"
    )
    canonical_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Current canonical team brand name (e.g., 'Tennessee Titans')"
    )
    established_year: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="NFL foundation or entry year"
    )

    # Relationships
    team_seasons: Mapped[List["TeamSeason"]] = relationship(
        "TeamSeason",
        back_populates="franchise",
        cascade="all, delete-orphan",
        order_by="TeamSeason.season_year.desc()"
    )
    player_stints: Mapped[List["PlayerTeamStint"]] = relationship(
        "PlayerTeamStint",
        back_populates="franchise",
        passive_deletes=True
    )
    accolades: Mapped[List["Accolade"]] = relationship(
        "Accolade",
        back_populates="franchise"
    )

    def __repr__(self) -> str:
        return f"<Franchise(id='{self.franchise_id}', name='{self.canonical_name}')>"


class TeamSeason(Base):
    """
    Represents an individual team's specific seasonal manifestation.
    Captures historical identity per season (e.g., Houston Oilers in 1993 vs Tennessee Titans in 2023).
    """
    __tablename__ = "team_seasons"
    __table_args__ = (
        UniqueConstraint("franchise_id", "season_year", name="uq_team_seasons_franchise_year"),
        CheckConstraint("season_year BETWEEN 1920 AND 2100", name="chk_team_season_year"),
    )

    team_season_id: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        comment="Natural composite key format: {team_abbr}_{season_year} (e.g., 'HOU_1993')"
    )
    franchise_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("franchises.franchise_id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )
    season_year: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="NFL season year"
    )
    team_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Historical seasonal name (e.g., 'Houston Oilers')"
    )
    team_abbr: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        comment="Official historical abbreviation (e.g., 'HOU', 'TEN')"
    )

    # Relationships
    franchise: Mapped["Franchise"] = relationship("Franchise", back_populates="team_seasons")
    player_stats: Mapped[List["PlayerSeasonStat"]] = relationship(
        "PlayerSeasonStat",
        back_populates="team_season"
    )

    def __repr__(self) -> str:
        return f"<TeamSeason(id='{self.team_season_id}', name='{self.team_name}', year={self.season_year})>"
