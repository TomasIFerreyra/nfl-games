from datetime import datetime
from typing import List, Union
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player
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
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"

    query = (
        select(
            Player.player_id,
            Player.full_name,
            Player.primary_position,
            Player.rookie_year,
            Player.final_year,
            Player.is_active,
        )
        .order_by(
            Player.is_active.desc(),
            Player.final_year.desc().nulls_first(),
            Player.full_name.asc(),
        )
    )

    result = await session.execute(query)
    rows = result.all()

    player_records: List[List[Union[str, int, None]]] = [
        [
            row.player_id,
            row.full_name,
            row.primary_position,
            row.rookie_year,
            row.final_year,
            1 if row.is_active else 0,
        ]
        for row in rows
    ]

    version_str = datetime.utcnow().strftime("%Y.%m.%d.1")

    return SearchIndexResponse(
        version=version_str,
        fields=["id", "name", "pos", "start", "end", "active"],
        players=player_records,
    )
