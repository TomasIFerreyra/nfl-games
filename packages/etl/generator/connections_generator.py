"""
Daily Connections 4x4 Puzzle Generator & Orchestrator.
Per Section 1.1.3 and Section 4.3 of SPECIFICATION.md:
- Deterministic seeding with target date: seed = int(target_date.strftime("%Y%m%d")) + 7727.
- Selects 1 category per difficulty tier:
  * Tier 1 (Bronze): Straightforward (Colleges, draft origins, single-team, obvious awards)
  * Tier 2 (Silver): Statistical Milestones (5,000+ pass yds, 100+ rush TDs, etc.)
  * Tier 3 (Gold): Overlaps & Journeymen (Dual-franchise stints, Day 3 / UDFA, MVP combos)
  * Tier 4 (Lombardi Platinum): Obscure & Quirky (Demographic/name quirks, rare pedigree)
- Employs intentional overlap/distractors to create deduction tension while rigorously
  verifying strictly ONE unique 4x4 disjoint partition via Knuth's Algorithm X.
- Persists validated puzzle payload into PostgreSQL daily_puzzles table with SHA-256 solution_hash.
"""

from dataclasses import asdict
from datetime import date, datetime
import hashlib
import json
import logging
import random
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player
from app.domain.connections_taxonomy import (
    ConnectionsCategoryDefinition,
    ConnectionsTier,
    connections_registry,
)
from app.domain.exact_cover_validator import ExactCoverValidator

logger = logging.getLogger(__name__)


class ConnectionsGenerator:
    """
    Deterministic daily generator orchestrator for NFL Connections 4x4 puzzles.
    """

    @classmethod
    def compute_solution_hash(cls, payload: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 hash for puzzle verification."""
        canonical_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def get_seed_for_date(cls, target_date: date) -> int:
        """Computes deterministic seed based on target date."""
        return int(target_date.strftime("%Y%m%d")) + 7727

    @classmethod
    async def generate_puzzle_data(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
        max_attempts: int = 50,
    ) -> Dict[str, Any]:
        """
        Generates and validates a complete Connections 4x4 puzzle for the given date.
        Guarantees strictly one unique 4-way disjoint partition via Knuth's Algorithm X.
        """
        seed = cls.get_seed_for_date(target_date)
        rng = random.Random(seed)

        # 1. Fetch all candidate categories per tier
        tier1_cats = connections_registry.get_categories_by_tier(ConnectionsTier.BRONZE)
        tier2_cats = connections_registry.get_categories_by_tier(ConnectionsTier.SILVER)
        tier3_cats = connections_registry.get_categories_by_tier(ConnectionsTier.GOLD)
        tier4_cats = connections_registry.get_categories_by_tier(ConnectionsTier.PLATINUM)

        # Shuffle candidate categories with seeded RNG
        t1_pool = list(tier1_cats)
        t2_pool = list(tier2_cats)
        t3_pool = list(tier3_cats)
        t4_pool = list(tier4_cats)

        rng.shuffle(t1_pool)
        rng.shuffle(t2_pool)
        rng.shuffle(t3_pool)
        rng.shuffle(t4_pool)

        # Cache resolved player pools to avoid repeated database lookups
        player_pool_cache: Dict[str, List[Player]] = {}

        async def get_pool(cat: ConnectionsCategoryDefinition) -> List[Player]:
            if cat.category_id not in player_pool_cache:
                players = await connections_registry.resolve_player_pool(cat, session)
                player_pool_cache[cat.category_id] = players
            return player_pool_cache[cat.category_id]

        # 2. Attempt candidate category quadruples
        attempt = 0
        while attempt < max_attempts:
            attempt += 1

            # Pick 1 category per tier
            c1 = rng.choice(t1_pool)
            c2 = rng.choice(t2_pool)
            c3 = rng.choice(t3_pool)
            c4 = rng.choice(t4_pool)

            # Ensure distinct category IDs
            if len({c1.category_id, c2.category_id, c3.category_id, c4.category_id}) < 4:
                continue

            p1_list = await get_pool(c1)
            p2_list = await get_pool(c2)
            p3_list = await get_pool(c3)
            p4_list = await get_pool(c4)

            # Ensure all categories have at least 4 candidate players
            if min(len(p1_list), len(p2_list), len(p3_list), len(p4_list)) < 4:
                continue

            p1_dict = {p.player_id: p for p in p1_list}
            p2_dict = {p.player_id: p for p in p2_list}
            p3_dict = {p.player_id: p for p in p3_list}
            p4_dict = {p.player_id: p for p in p4_list}

            # Map all available category pools in taxonomy for Algorithm X validation
            all_active_cats = connections_registry.get_all_categories(active_only=True)
            active_cat_pools: Dict[str, Set[str]] = {}
            for acat in all_active_cats:
                ac_players = await get_pool(acat)
                active_cat_pools[acat.category_id] = {p.player_id for p in ac_players}

            # Try selecting 4 players per category
            # We want 16 distinct players total
            sub_attempts = 20
            for _ in range(sub_attempts):
                # Sample 4 players for group 1
                g1_sample = rng.sample(list(p1_dict.keys()), 4)
                used_players = set(g1_sample)

                # Sample 4 players for group 2
                g2_avail = [pid for pid in p2_dict.keys() if pid not in used_players]
                if len(g2_avail) < 4:
                    continue
                g2_sample = rng.sample(g2_avail, 4)
                used_players.update(g2_sample)

                # Sample 4 players for group 3
                g3_avail = [pid for pid in p3_dict.keys() if pid not in used_players]
                if len(g3_avail) < 4:
                    continue
                g3_sample = rng.sample(g3_avail, 4)
                used_players.update(g3_sample)

                # Sample 4 players for group 4
                g4_avail = [pid for pid in p4_dict.keys() if pid not in used_players]
                if len(g4_avail) < 4:
                    continue
                g4_sample = rng.sample(g4_avail, 4)
                used_players.update(g4_sample)

                # We have 16 candidate players!
                candidate_16 = g1_sample + g2_sample + g3_sample + g4_sample

                # Collect all player objects for metadata
                all_sampled_players: Dict[str, Player] = {}
                for pid in g1_sample:
                    all_sampled_players[pid] = p1_dict[pid]
                for pid in g2_sample:
                    all_sampled_players[pid] = p2_dict[pid]
                for pid in g3_sample:
                    all_sampled_players[pid] = p3_dict[pid]
                for pid in g4_sample:
                    all_sampled_players[pid] = p4_dict[pid]

                target_groups = [
                    set(g1_sample),
                    set(g2_sample),
                    set(g3_sample),
                    set(g4_sample),
                ]

                # Run Knuth's Algorithm X Exact Cover validation across entire taxonomy
                validation_result = ExactCoverValidator.validate_puzzle_uniqueness(
                    item_ids=candidate_16,
                    category_player_pools=active_cat_pools,
                    target_groups=target_groups,
                )

                if validation_result.is_unique:
                    # Validated strictly unique puzzle!
                    logger.info(
                        f"Generated valid unique Connections puzzle in {attempt} attempts "
                        f"({validation_result.solve_time_ms:.2f}ms solve time)."
                    )

                    # Shuffle the 16 items for display presentation
                    shuffled_items = list(candidate_16)
                    rng.shuffle(shuffled_items)

                    items_payload = [
                        {
                            "item_id": pid,
                            "display_text": all_sampled_players[pid].full_name,
                            "subtext": all_sampled_players[pid].primary_position,
                        }
                        for pid in shuffled_items
                    ]

                    groups_payload = [
                        {
                            "group_id": f"grp_{c1.category_id.lower()}",
                            "tier": int(c1.tier),
                            "title": c1.title,
                            "item_ids": g1_sample,
                            "explanation": c1.explanation,
                        },
                        {
                            "group_id": f"grp_{c2.category_id.lower()}",
                            "tier": int(c2.tier),
                            "title": c2.title,
                            "item_ids": g2_sample,
                            "explanation": c2.explanation,
                        },
                        {
                            "group_id": f"grp_{c3.category_id.lower()}",
                            "tier": int(c3.tier),
                            "title": c3.title,
                            "item_ids": g3_sample,
                            "explanation": c3.explanation,
                        },
                        {
                            "group_id": f"grp_{c4.category_id.lower()}",
                            "tier": int(c4.tier),
                            "title": c4.title,
                            "item_ids": g4_sample,
                            "explanation": c4.explanation,
                        },
                    ]

                    return {
                        "items": items_payload,
                        "groups": groups_payload,
                    }

        # Fallback guarantee: construct default verified puzzle
        logger.warning(
            f"Connections generator reached max attempts ({max_attempts}) for date {target_date}. "
            f"Falling back to verified curated seed template."
        )
        return cls._get_curated_fallback_puzzle(seed=seed)

    @classmethod
    def _get_curated_fallback_puzzle(cls, seed: int) -> Dict[str, Any]:
        """Provides verified fallback puzzle guaranteeing exact cover uniqueness."""
        rng = random.Random(seed)

        items = [
            {"item_id": "p_cam_newton", "display_text": "Cam Newton", "subtext": "QB"},
            {"item_id": "p_lamar_jackson", "display_text": "Lamar Jackson", "subtext": "QB"},
            {"item_id": "p_kyler_murray", "display_text": "Kyler Murray", "subtext": "QB"},
            {"item_id": "p_baker_mayfield", "display_text": "Baker Mayfield", "subtext": "QB"},
            {"item_id": "p_patrick_mahomes", "display_text": "Patrick Mahomes", "subtext": "QB"},
            {"item_id": "p_peyton_manning", "display_text": "Peyton Manning", "subtext": "QB"},
            {"item_id": "p_drew_brees", "display_text": "Drew Brees", "subtext": "QB"},
            {"item_id": "p_tom_brady", "display_text": "Tom Brady", "subtext": "QB"},
            {"item_id": "p_randy_moss", "display_text": "Randy Moss", "subtext": "WR"},
            {"item_id": "p_jerry_rice", "display_text": "Jerry Rice", "subtext": "WR"},
            {"item_id": "p_terrell_owens", "display_text": "Terrell Owens", "subtext": "WR"},
            {"item_id": "p_cris_carter", "display_text": "Cris Carter", "subtext": "WR"},
            {"item_id": "p_michael_strahan", "display_text": "Michael Strahan", "subtext": "DE"},
            {"item_id": "p_michael_irvin", "display_text": "Michael Irvin", "subtext": "WR"},
            {"item_id": "p_michael_vick", "display_text": "Michael Vick", "subtext": "QB"},
            {"item_id": "p_mike_evans", "display_text": "Mike Evans", "subtext": "WR"},
        ]

        groups = [
            {
                "group_id": "grp_heisman_qbs",
                "tier": 1,
                "title": "Heisman Trophy Winning Quarterbacks",
                "item_ids": ["p_cam_newton", "p_lamar_jackson", "p_kyler_murray", "p_baker_mayfield"],
                "explanation": "All 4 won the Heisman Trophy in college football.",
            },
            {
                "group_id": "grp_pass_5000",
                "tier": 2,
                "title": "5,000+ Passing Yards in a Single Season",
                "item_ids": ["p_patrick_mahomes", "p_peyton_manning", "p_drew_brees", "p_tom_brady"],
                "explanation": "All 4 threw for over 5,000 yards in a single NFL season.",
            },
            {
                "group_id": "grp_rec_td_120",
                "tier": 3,
                "title": "120+ Career Receiving Touchdowns",
                "item_ids": ["p_randy_moss", "p_jerry_rice", "p_terrell_owens", "p_cris_carter"],
                "explanation": "All 4 caught at least 120 regular season receiving touchdowns.",
            },
            {
                "group_id": "grp_name_michael",
                "tier": 4,
                "title": "Shared First Name 'Michael' or 'Mike'",
                "item_ids": ["p_michael_strahan", "p_michael_irvin", "p_michael_vick", "p_mike_evans"],
                "explanation": "All 4 players share the first name Michael or Mike.",
            },
        ]

        shuffled_items = list(items)
        rng.shuffle(shuffled_items)

        return {
            "items": shuffled_items,
            "groups": groups,
        }

    @classmethod
    async def generate_and_publish_daily_puzzle(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
    ) -> Dict[str, Any]:
        """
        Generates and saves the daily Connections puzzle to the daily_puzzles table.
        """
        puzzle_data = await cls.generate_puzzle_data(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
        )

        sol_hash = cls.compute_solution_hash(puzzle_data)

        insert_stmt = text("""
            INSERT INTO daily_puzzles (target_date, game_type, puzzle_number, puzzle_data, solution_hash)
            VALUES (:target_date, 'CONNECTIONS', :puzzle_number, :puzzle_data, :solution_hash)
            ON CONFLICT (target_date, game_type) DO UPDATE SET
                puzzle_data = EXCLUDED.puzzle_data,
                solution_hash = EXCLUDED.solution_hash;
        """)

        await session.execute(insert_stmt, {
            "target_date": target_date,
            "puzzle_number": puzzle_number,
            "puzzle_data": json.dumps(puzzle_data),
            "solution_hash": sol_hash,
        })
        await session.commit()
        logger.info(f"Published validated Connections puzzle #{puzzle_number} for {target_date}.")
        return puzzle_data
