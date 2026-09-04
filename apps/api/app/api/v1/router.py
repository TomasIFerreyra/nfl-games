from fastapi import APIRouter

from app.api.v1.endpoints.connections import router as connections_router
from app.api.v1.endpoints.grid import router as grid_router
from app.api.v1.endpoints.players import router as players_router
from app.api.v1.endpoints.puzzles import router as puzzles_router
from app.api.v1.endpoints.top10 import router as top10_router

api_router = APIRouter()

api_router.include_router(puzzles_router)
api_router.include_router(grid_router)
api_router.include_router(players_router)
api_router.include_router(connections_router)
api_router.include_router(top10_router)
