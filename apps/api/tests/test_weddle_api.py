from datetime import date
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.db.session import AsyncSessionLocal
from app.services.puzzle_pipeline import PuzzlePipelineService



@pytest.mark.asyncio
async def test_weddle_daily_generation_and_api():
    async with AsyncSessionLocal() as session:
        target_date = date(2026, 9, 11)

        puzzle = await PuzzlePipelineService.generate_daily_weddle(
            session=session,
            target_date=target_date,
        )
        assert puzzle.game_type == "WEDDLE"
        assert puzzle.puzzle_number > 0

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Test GET /api/v1/puzzles/weddle/daily (Sanitized response)
        res = await ac.get("/api/v1/puzzles/weddle/daily?date=2026-09-11")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["game_type"] == "weddle"
        assert "target_player_id" not in data["puzzle_data"]  # Anti-cheat check

        puzzle_id = data["puzzle_id"]

        # 2. Test POST /api/v1/weddle/guess with Josh Allen
        guess_res = await ac.post(
            "/api/v1/weddle/guess",
            json={
                "puzzle_id": puzzle_id,
                "player_id": "00-0034857",  # Josh Allen
                "previous_guesses": [],
            },
        )
        assert guess_res.status_code == 200, f"Expected 200, got {guess_res.status_code}: {guess_res.text}"
        guess_data = guess_res.json()
        assert "comparison" in guess_data
        assert "attributes" in guess_data["comparison"]
        assert guess_data["guesses_remaining"] == 5
        assert guess_data["is_game_over"] is False
        assert guess_data["revealed_target"] is None  # Anti-cheat check

        # 3. Collision Prevention: Guess Milton Williams by name and verify no Creed Humphrey collision
        res_mw_name = await ac.post(
            "/api/v1/weddle/guess",
            json={
                "puzzle_id": puzzle_id,
                "player_id": "Milton Williams",
                "previous_guesses": ["00-0034857"],
            },
        )
        assert res_mw_name.status_code == 200
        data_mw_name = res_mw_name.json()
        guessed_player_mw = data_mw_name["comparison"]["player"]
        assert guessed_player_mw["full_name"] == "Milton Williams"
        assert guessed_player_mw["full_name"] != "Creed Humphrey"

        # 4. Guess Creed Humphrey by name
        res_ch = await ac.post(
            "/api/v1/weddle/guess",
            json={
                "puzzle_id": puzzle_id,
                "player_id": "Creed Humphrey",
                "previous_guesses": ["00-0034857", "f1c9af6b-6329-4132-8a0d-b08d84a58a93"],
            },
        )
        assert res_ch.status_code == 200
        data_ch = res_ch.json()
        guessed_player_ch = data_ch["comparison"]["player"]
        assert guessed_player_ch["full_name"] == "Creed Humphrey"
        assert guessed_player_ch["position"] == "C"

        # 5. Guess Creed Humphrey by canonical GSIS ID 00-0036623
        res_ch_id = await ac.post(
            "/api/v1/weddle/guess",
            json={
                "puzzle_id": puzzle_id,
                "player_id": "00-0036623",
                "previous_guesses": ["00-0034857"],
            },
        )
        assert res_ch_id.status_code == 200
        data_ch_id = res_ch_id.json()
        assert data_ch_id["comparison"]["player"]["full_name"] == "Creed Humphrey"


