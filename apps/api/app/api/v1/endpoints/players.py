import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.models.player import Player, PlayerTeamStint
from app.db.session import get_async_session
from app.schemas.player import SearchIndexResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/players", tags=["Players"])

SEARCH_INDEX_REDIS_KEY = "nfl:catalog:search_index:v1"
SEARCH_INDEX_CACHE_TTL = 86400  # 24 hours


@router.get(
    "/search-index",
    response_model=SearchIndexResponse,
    summary="Download lightweight compressed player search catalog",
)
async def get_player_search_index(
    response: Response,
    session: AsyncSession = Depends(get_async_session),
    redis_client: Optional[Redis] = Depends(get_redis),
) -> SearchIndexResponse:
    """
    Returns the complete searchable directory of NFL players in a compact row-oriented format.
    Fields: [id, full_name, primary_position, rookie_year, final_year, is_active]
    Cached in Redis and edge CDNs to prevent database strain under high concurrent traffic.
    """
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"

    # 1. Attempt Redis Cache Lookup
    if redis_client is not None:
        try:
            cached_index = await redis_client.get(SEARCH_INDEX_REDIS_KEY)
            if cached_index:
                parsed_data = json.loads(cached_index)
                return SearchIndexResponse(**parsed_data)
        except Exception as exc:
            logger.warning(f"Redis cache lookup for search index failed: {exc}. Falling back to PostgreSQL.")

    # 2. Database Precomputation
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

    index_response = SearchIndexResponse(
        version=version_str,
        fields=["id", "name", "pos", "start", "end", "active"],
        players=player_records,
    )

    # 3. Populate Redis Cache
    if redis_client is not None:
        try:
            await redis_client.setex(
                SEARCH_INDEX_REDIS_KEY,
                SEARCH_INDEX_CACHE_TTL,
                json.dumps(index_response.model_dump()),
            )
        except Exception as exc:
            logger.warning(f"Failed to cache search index in Redis: {exc}")

    return index_response
