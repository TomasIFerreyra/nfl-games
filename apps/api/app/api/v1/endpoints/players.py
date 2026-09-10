from datetime import datetime, timezone
from typing import List, Union
from fastapi import APIRouter, Depends, Response
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player, PlayerTeamStint
from app.db.session import get_async_session
from app.schemas.player import SearchIndexResponse

router = APIRouter(prefix="/players", tags=["Players"])


@router.get(
    "/search-index",
    response_model=SearchIndexResponse,
    summary="Download lightweight compressed player search catalog",
)
async def get_player_search_index(
    response: Response,
    session: AsyncSession = Depends(get_async_session),
) -> SearchIndexResponse:
    """
    Returns the complete searchable directory of NFL players in a compact row-oriented format.
    Fields: [id, full_name, primary_position, rookie_year, final_year, is_active]
    Transfer size: ~320 KB gzipped.
    """
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"

    max_stint_subquery = (
        select(func.max(PlayerTeamStint.season_year))
        .where(PlayerTeamStint.player_id == Player.player_id)
        .scalar_subquery()
    )

    computed_final_year = case(
        (
            (Player.is_active.is_(False)) & (Player.final_year.is_(None)),
            max_stint_subquery,
        ),
        else_=Player.final_year,
    ).label("final_year")

    query = (
        select(
            Player.player_id,
            Player.full_name,
            Player.primary_position,
            Player.rookie_year,
            computed_final_year,
            Player.is_active,
        )
        .order_by(
            Player.is_active.desc(),
            computed_final_year.desc().nulls_first(),
            Player.full_name.asc(),
        )
    )

    result = await session.execute(query)
    rows = result.all()

    player_records: List[List[Union[str, int, None]]] = [
        [
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            1 if row[5] else 0,
        ]
        for row in rows
    ]

    version_str = datetime.now(timezone.utc).strftime("%Y.%m.%d.1")

    return SearchIndexResponse(
        version=version_str,
        fields=["id", "name", "pos", "start", "end", "active"],
        players=player_records,
    )
