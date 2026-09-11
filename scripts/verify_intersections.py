import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("apps/api"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.services.grid_precompute_service import GridPrecomputeService
from app.domain.criteria_registry import registry

async def test():
    engine = create_async_engine(settings.async_database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        # Resolve target player aliases
        favre_p = (await session.execute(text("SELECT player_id FROM players WHERE full_name = 'Brett Favre' LIMIT 1"))).scalar()
        wilson_p = (await session.execute(text("SELECT player_id FROM players WHERE full_name = 'Garrett Wilson' LIMIT 1"))).scalar()
        love_p = (await session.execute(text("SELECT player_id FROM players WHERE full_name = 'Jordan Love' LIMIT 1"))).scalar()

        favre_aliases = await GridPrecomputeService.resolve_player_canonical_ids(session, favre_p)
        wilson_aliases = await GridPrecomputeService.resolve_player_canonical_ids(session, wilson_p)
        love_aliases = await GridPrecomputeService.resolve_player_canonical_ids(session, love_p)

        print("Favre ID:", favre_p, "Aliases:", favre_aliases)
        print("Wilson ID:", wilson_p, "Aliases:", wilson_aliases)
        print("Love ID:", love_p, "Aliases:", love_aliases)

        # Test criteria
        crit_gnb = registry.get_criterion("FRAN_GNB").to_dict()
        crit_min = registry.get_criterion("FRAN_MIN").to_dict()
        crit_nyj = registry.get_criterion("FRAN_NYJ").to_dict()
        crit_hof = registry.get_criterion("ACCOLADE_HOF").to_dict()
        crit_rd1 = registry.get_criterion("DRAFT_RD1").to_dict()

        set_gnb = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, crit_gnb)
        set_min = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, crit_min)
        set_nyj = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, crit_nyj)
        set_hof = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, crit_hof)
        set_rd1 = await GridPrecomputeService.get_qualifying_player_ids_for_criterion(session, crit_rd1)

        print("\n=== EVALUATION RESULTS ===")
        print("1. Favre in GNB:", bool(favre_aliases & set_gnb))
        print("   Favre in MIN:", bool(favre_aliases & set_min))
        print("   Favre in NYJ:", bool(favre_aliases & set_nyj))
        print("   Favre in HOF:", bool(favre_aliases & set_hof))
        print("   Favre in (GNB x MIN):", bool(favre_aliases & set_gnb) and bool(favre_aliases & set_min))
        print("   Favre in (NYJ x MIN):", bool(favre_aliases & set_nyj) and bool(favre_aliases & set_min))
        print("   Favre in (GNB x HOF):", bool(favre_aliases & set_gnb) and bool(favre_aliases & set_hof))

        print("\n2. Wilson in NYJ:", bool(wilson_aliases & set_nyj))
        print("   Wilson in RD1:", bool(wilson_aliases & set_rd1))
        print("   Wilson in (NYJ x RD1):", bool(wilson_aliases & set_nyj) and bool(wilson_aliases & set_rd1))

        print("\n3. Love in GNB:", bool(love_aliases & set_gnb))
        print("   Love in RD1:", bool(love_aliases & set_rd1))
        print("   Love in (GNB x RD1):", bool(love_aliases & set_gnb) and bool(love_aliases & set_rd1))

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test())
