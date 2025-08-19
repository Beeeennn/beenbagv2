# inside your Base cog (or new cog)
import asyncio, io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import asyncpg
import discord
from discord.ext import commands
from PIL import Image

from services import base_shop
from services.room_gen2 import generate_base
from utils.game_helpers import get_items, take_items, give_items, gid_from_ctx

from services.monetization import IS_DEV
# --------------------------------------------------------------------
# Shop catalogs (authoritative, code-driven)
# --------------------------------------------------------------------
# Toggle: if True, anything not present below will be auto-disabled (not deleted).
AUTO_DISABLE_MISSING = True

# Base Shop: item_id -> definition
BASE_SHOP_CATALOG: dict[int, dict] = {
    # EXAMPLE ITEMS — replace with your real catalog
    1: {
        "name": "wood",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 10},        # currency -> amount
    },
    2: {
        "name": "light_wood",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 20},        # currency -> amount
    },
    3: {
        "name": "dark_wood",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 20},        # currency -> amount
    },
    4: {
        "name": "bricks",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 20,
        "costs": {"cobblestone": 10},        # currency -> amount
    },
    5: {
        "name": "quartz",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 20,
        "costs": {"gold": 5},        # currency -> amount
    },
    6: {
        "name": "black_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    7: {
        "name": "dark_blue_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    8: {
        "name": "light_blue_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    9: {
        "name": "dark_green_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    10: {
        "name": "light_green_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    11: {
        "name": "orange_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    12: {
        "name": "pink_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    13: {
        "name": "purple_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    14: {
        "name": "red_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    15: {
        "name": "yellow_wool",
        "description": "basic flooring.",
        "category": "floors",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    101: {
        "name": "wood",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 10},        # currency -> amount
    },
    102: {
        "name": "light_wood",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 20},        # currency -> amount
    },
    103: {
        "name": "dark_wood",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 20},        # currency -> amount
    },
    104: {
        "name": "bricks",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 20,
        "costs": {"cobblestone": 10},        # currency -> amount
    },
    105: {
        "name": "quartz",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 20,
        "costs": {"gold": 5},        # currency -> amount
    },
    106: {
        "name": "black_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    107: {
        "name": "dark_blue_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    108: {
        "name": "light_blue_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    109: {
        "name": "dark_green_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    110: {
        "name": "light_green_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    111: {
        "name": "orange_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    112: {
        "name": "pink_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    113: {
        "name": "purple_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    114: {
        "name": "red_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    115: {
        "name": "yellow_wool",
        "description": "wall inside the base.",
        "category": "inside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    201: {
        "name": "wood",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 10},        # currency -> amount
    },
    202: {
        "name": "light_wood",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 20},        # currency -> amount
    },
    203: {
        "name": "dark_wood",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"wood": 20},        # currency -> amount
    },
    204: {
        "name": "bricks",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 20,
        "costs": {"cobblestone": 10},        # currency -> amount
    },
    205: {
        "name": "quartz",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 20,
        "costs": {"gold": 5},        # currency -> amount
    },
    206: {
        "name": "black_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    207: {
        "name": "dark_blue_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    208: {
        "name": "light_blue_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    209: {
        "name": "dark_green_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    210: {
        "name": "light_green_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    211: {
        "name": "orange_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    212: {
        "name": "pink_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    213: {
        "name": "purple_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    214: {
        "name": "red_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },
    215: {
        "name": "yellow_wool",
        "description": "wall outlining the base.",
        "category": "outside walls",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 30,
        "costs": {"gold": 10},        # currency -> amount
    },

    301: {
        "name": "blue_bed",
        "description": "a blue bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },

    301: {
        "name": "blue_bed",
        "description": "a blue bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },

    301: {
        "name": "blue_bed",
        "description": "a blue bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },

    301: {
        "name": "blue_bed",
        "description": "a blue bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },

    302: {
        "name": "red_bed",
        "description": "a red bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },

    303: {
        "name": "pink_bed",
        "description": "a pink bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },

    304: {
        "name": "green_bed",
        "description": "a green bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },

    305: {
        "name": "orange_bed",
        "description": "a blue bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },
    306: {
        "name": "yellow_bed",
        "description": "a blue bed.",
        "category": "beds",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"wood":10},        # currency -> amount
    },
    401:{
        "name": "blurryface",
        "description": "a TOP poster.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20,"gold":5},        # currency -> amount
    },
    402:{
        "name": "Breach",
        "description": "a TOP poster.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20,"gold":5},        # currency -> amount
    },
    403:{
        "name": "cat1",
        "description": "a poster of a cat.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20},        # currency -> amount
    },
    405:{
        "name": "clancy",
        "description": "a TOP poster.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20,"gold":5},        # currency -> amount
    },
    406:{
        "name": "earth_from_moon",
        "description": "a space poster.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"gold":5,"iron":5},        # currency -> amount
    },
    407:{
        "name": "galaxy",
        "description": "a space poster.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10,"gold":5,"iron":5},        # currency -> amount
    },
    408:{
        "name": "hot_pockets",
        "description": "7 hot pocket packets. (use 3 times for 21 hot pockets)",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20},        # currency -> amount
    },
    409:{
        "name": "kirstie_guns",
        "description": "scary.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20},        # currency -> amount
    },
    410:{
        "name": "puppet",
        "description": "drawn by UrLocalCosplayer",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20},        # currency -> amount
    },
    411:{
        "name": "scaled_and_icy",
        "description": "a TOP poster.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20,"gold":5},        # currency -> amount
    },
    412:{
        "name": "stary_night",
        "description": "vincent van gough.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20,"gold":5},        # currency -> amount
    },
    413:{
        "name": "trench",
        "description": "a TOP poster.",
        "category": "posters",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 20,"gold":5},        # currency -> amount
    },
    601:{
        "name": "Australian_shepherd",
        "description": "Based on Freckles.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    602:{
        "name": "blue_cat",
        "description": "a black cat with blue collar.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    603:{
        "name": "brown_chihuahua",
        "description": "Smaller than most.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    604:{
        "name": "cream_chihuahua",
        "description": "Smaller than most.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    605:{
        "name": "green_cat",
        "description": "A ginger cat with green collar.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 47},        # currency -> amount
    },
    606:{
        "name": "dog1",
        "description": "Based on Finndog.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    607:{
        "name": "pink_cat",
        "description": "A grey cat with pink collar.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    608:{
        "name": "red_cat",
        "description": "A light grey cat with red collar.",
        "category": "pets",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    701:{
        "name": "blue_tulip",
        "description": "A blue tulip on a desk.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10, "wood":15},        # currency -> amount
    },
    702:{
        "name": "orange_tulip",
        "description": "An orange tulip on a desk.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10, "wood":15},        # currency -> amount
    },
    703:{
        "name": "pink_rose",
        "description": "A pink rose on a desk.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10, "wood":15},        # currency -> amount
    },
    704:{
        "name": "red_poppy",
        "description": "A blue tulip on a desk.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10, "wood":15},        # currency -> amount
    },
    705:{
        "name": "chest",
        "description": "A worn out double chest.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 50},        # currency -> amount
    },
    706:{
        "name": "silver_play_button",
        "description": "A sliver play button and a cup of water.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10, "wood":15, "gold":10},        # currency -> amount
    },
    901:{
        "name": "brown",
        "description": "A wooden pet house.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10, "wood":30},        # currency -> amount
    },
    901:{
        "name": "grey",
        "description": "An iron pet house.",
        "category": "furniture",
        "purchase_limit": None,      # or an int
        "disabled": False,
        "sort_order": 10,
        "costs": {"emeralds": 10, "iron":20},        # currency -> amount
    },



}

# Upgrades Shop: upgrade_id -> definition
UPGRADES_CATALOG: dict[int, dict] = {
    # EXAMPLE UPGRADES — replace with your real catalog
    100: {
        "name": "Basic Room",
        "description": "Unlocks a basic room.",
        "room_type": "basic_room",
        "disabled": False,
        "sort_order": 10,
        "costs": {},
    },
    # 101: {
    #     "name": "Large Room",
    #     "description": "Unlocks a large room.",
    #     "room_type": "large_room",
    #     "disabled": False,
    #     "sort_order": 20,
    #     "costs": {"stone": 50, "wood": 50},
    # },
    # ...
}

# --------------------------------------------------------------------
# Sync routines (run at startup). Idempotent; preserves inventories.
# --------------------------------------------------------------------
async def _sync_base_shop(con: asyncpg.Connection):
    # Upsert items
    for item_id, d in BASE_SHOP_CATALOG.items():
        await con.execute("""
            INSERT INTO base_shop_items
                (item_id, name, description, category, purchase_limit, disabled, sort_order)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT (item_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                purchase_limit = EXCLUDED.purchase_limit,
                disabled = EXCLUDED.disabled,
                sort_order = EXCLUDED.sort_order
        """,
        item_id,
        d.get("name"),
        d.get("description"),
        d.get("category"),
        d.get("purchase_limit"),
        d.get("disabled", False),
        d.get("sort_order", 0),
        )

        # Replace costs for this item (simple & clean)
        await con.execute("DELETE FROM base_shop_item_costs WHERE item_id=$1", item_id)
        costs = d.get("costs", {}) or {}
        if costs:
            await con.executemany(
                "INSERT INTO base_shop_item_costs (item_id, currency_item, amount) VALUES ($1,$2,$3)",
                [(item_id, cur, int(amt)) for cur, amt in costs.items() if int(amt) > 0]
            )

    if AUTO_DISABLE_MISSING:
        # Disable any item_ids not in the catalog (keeps old inventories usable)
        catalog_ids = list(BASE_SHOP_CATALOG.keys())
        await con.execute("""
            UPDATE base_shop_items
               SET disabled = TRUE
             WHERE NOT disabled
               AND item_id NOT IN (SELECT UNNEST($1::bigint[]))
        """, catalog_ids)

async def _sync_upgrades_shop(con: asyncpg.Connection):
    for up_id, d in UPGRADES_CATALOG.items():
        await con.execute("""
            INSERT INTO upgrades_shop_items
                (upgrade_id, name, description, room_type, disabled, sort_order)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (upgrade_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                room_type = EXCLUDED.room_type,
                disabled = EXCLUDED.disabled,
                sort_order = EXCLUDED.sort_order
        """,
        up_id,
        d.get("name"),
        d.get("description"),
        d.get("room_type"),
        d.get("disabled", False),
        d.get("sort_order", 0),
        )

        # Replace costs for this upgrade
        await con.execute("DELETE FROM upgrades_shop_costs WHERE upgrade_id=$1", up_id)
        costs = d.get("costs", {}) or {}
        if costs:
            await con.executemany(
                "INSERT INTO upgrades_shop_costs (upgrade_id, currency_item, amount) VALUES ($1,$2,$3)",
                [(up_id, cur, int(amt)) for cur, amt in costs.items() if int(amt) > 0]
            )

    if AUTO_DISABLE_MISSING:
        catalog_ids = list(UPGRADES_CATALOG.keys())
        await con.execute("""
            UPDATE upgrades_shop_items
               SET disabled = TRUE
             WHERE NOT disabled
               AND upgrade_id NOT IN (SELECT UNNEST($1::bigint[]))
        """, catalog_ids)

async def sync_shops_from_code(pool):
    """Run once at startup. No truncation; inventories untouched."""
    async with pool.acquire() as con, con.transaction():
        await _sync_base_shop(con)
        await _sync_upgrades_shop(con)
# --------------------------------------------------------------------
# Config / constants
# --------------------------------------------------------------------

ASSETS_ROOT = Path("assets/house/")
_EXEC = ThreadPoolExecutor(max_workers=2)  # offload PIL/file I/O

# Slots → acceptable categories (lowercased), to be tolerant of singular/plural/case
SLOT_TO_CATEGORIES: dict[str, List[str]] = {
    # Structure (pipelines into generate_base)
    "flooring": ["floors", "floor"],
    "inside_wall": ["inside wall", "inside walls", "wall inside", "inside"],
    "outline_wall": ["outside wall", "outside walls", "wall outside", "outside", "walls"],

    # Decor examples (extend as you add more)
    "beds": ["beds", "bed"],
    "poster1": ["posters", "poster"],
    "poster2": ["posters", "poster"],
    "poster3": ["posters", "poster"],
    "furniture1": ["furniture"],
    "furniture2": ["furniture"],
    "pet": ["pets", "pet"],
}
FALLBACKS = {"flooring": "dirt", "inside_wall": "dirt", "outline_wall": "dirt"}

STRUCTURE_SLOTS = {"flooring", "inside_wall", "outline_wall"}


# --------------------------------------------------------------------
# Inventory helpers (consume / refund one copy by item_id)
# --------------------------------------------------------------------

async def _inv_count(conn, guild_id: int, user_id: int, item_id: int) -> int:
    return await conn.fetchval("""
        SELECT COUNT(*)::int
        FROM base_inventory
        WHERE guild_id=$1 AND user_id=$2 AND item_id=$3
    """, guild_id, user_id, item_id) or 0


async def _inv_take_one(conn, guild_id: int, user_id: int, item_id: int) -> bool:
    row = await conn.fetchrow("""
        DELETE FROM base_inventory
        WHERE ctid IN (
          SELECT ctid
          FROM base_inventory
          WHERE guild_id=$1 AND user_id=$2 AND item_id=$3
          LIMIT 1
        )
        RETURNING 1
    """, guild_id, user_id, item_id)
    return bool(row)


async def _inv_give_one(conn, guild_id: int, user_id: int, item_id: int):
    await conn.execute("""
        INSERT INTO base_inventory(guild_id, user_id, item_id) VALUES($1,$2,$3)
    """, guild_id, user_id, item_id)


# --------------------------------------------------------------------
# Load/save placements (note: base_decorations.item_id is TEXT in DB)
# --------------------------------------------------------------------

async def _load_slots(conn, room_id: int) -> dict[str, int]:
    """
    Returns {slot: item_id_int}, coercing TEXT item_id -> int.
    Silently skips rows that can't be parsed.
    """
    rows = await conn.fetch(
        "SELECT slot, item_id FROM base_decorations WHERE room_id=$1", room_id
    )
    out: dict[str, int] = {}
    for r in rows:
        try:
            out[str(r["slot"])] = int(r["item_id"])
        except (TypeError, ValueError):
            # skip bad rows
            continue
    return out


async def _set_slot(conn, guild_id: int, user_id: int, room_id: int, slot: str, new_item_id: int):
    """
    Upsert slot; returns previous item_id (int) if any.
    Column base_decorations.item_id is BIGINT now, so pass an int (not str).
    """
    prev = await conn.fetchval(
        "SELECT item_id FROM base_decorations WHERE room_id=$1 AND slot=$2",
        room_id, slot
    )
    if prev is not None:
        try:
            prev = int(prev)
        except (TypeError, ValueError):
            prev = None

    # IMPORTANT: pass `new_item_id` as int; the ::bigint cast is optional but explicit.
    await conn.execute("""
        INSERT INTO base_decorations (guild_id, user_id, room_id, slot, item_id)
        VALUES ($1,$2,$3,$4,$5::bigint)
        ON CONFLICT (room_id, slot) DO UPDATE SET item_id = EXCLUDED.item_id
    """, guild_id, user_id, room_id, slot, int(new_item_id))

    return prev


async def _clear_slot(conn, room_id: int, slot: str) -> Optional[int]:
    row = await conn.fetchrow("""
        DELETE FROM base_decorations
        WHERE room_id=$1 AND slot=$2
        RETURNING item_id
    """, room_id, slot)
    if not row:
        return None
    try:
        return int(row["item_id"])
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------
# Item metadata (name/category)
# --------------------------------------------------------------------

async def _item_meta(conn, item_id: int) -> tuple[str, str]:
    r = await conn.fetchrow(
        "SELECT name, category FROM base_shop_items WHERE item_id=$1", item_id
    )
    if not r:
        raise KeyError("Unknown item_id")
    return r["name"], r["category"]


# --------------------------------------------------------------------
# Split placements for generator
# --------------------------------------------------------------------

def _split_for_generate(slots_to_item_id: dict[str, int], id_to_name: dict[int, str]):
    flooring = id_to_name.get(slots_to_item_id.get("flooring"), FALLBACKS["flooring"])
    inside = id_to_name.get(slots_to_item_id.get("inside_wall"), FALLBACKS["inside_wall"])
    outline = id_to_name.get(slots_to_item_id.get("outline_wall"), FALLBACKS["outline_wall"])

    decorations: dict[str, str] = {}
    for slot, iid in slots_to_item_id.items():
        if slot in STRUCTURE_SLOTS:
            continue
        nm = id_to_name.get(iid)
        if nm:
            decorations[slot] = nm
    return flooring, inside, outline, decorations


# --------------------------------------------------------------------
# Shop browsing helpers
# --------------------------------------------------------------------

async def _fetch_categories(conn) -> list[str]:
    rows = await conn.fetch("""
        SELECT category
        FROM base_shop_items
        WHERE NOT disabled
        GROUP BY category
        ORDER BY lower(category)
    """)
    return [r["category"] for r in rows] or ["General"]


async def _fetch_items_in_category(conn, category: str) -> list[asyncpg.Record]:
    # Case-insensitive match for safety
    return await conn.fetch("""
        SELECT item_id, name, description, category, purchase_limit, sort_order
          FROM base_shop_items
         WHERE lower(category) = lower($1) AND NOT disabled
         ORDER BY sort_order, item_id
    """, category)


async def _fetch_costs_map(conn, item_ids: list[int]) -> dict[int, dict[str, int]]:
    if not item_ids:
        return {}
    rows = await conn.fetch("""
        SELECT item_id, currency_item, amount
          FROM base_shop_item_costs
         WHERE item_id = ANY($1::bigint[])
         ORDER BY currency_item
    """, item_ids)
    out: dict[int, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["item_id"], {})[r["currency_item"]] = r["amount"]
    return out


async def _base_get_costs(conn, item_id: int) -> dict[str, int]:
    rows = await conn.fetch(
        "SELECT currency_item, amount FROM base_shop_item_costs WHERE item_id=$1 ORDER BY currency_item",
        item_id,
    )
    return {r["currency_item"]: r["amount"] for r in rows}


def _fmt_costs(costs: dict[str, int]) -> str:
    if not costs:
        return "free"
    return " + ".join(f"{amt} × {cur}" for cur, amt in costs.items() if amt > 0)


# --------------------------------------------------------------------
# Asset helpers
# --------------------------------------------------------------------

def _sanitize_segment(s: str) -> str:
    s2 = "".join(ch if ch.isalnum() or ch in ("_", "-", " ") else "_" for ch in s.strip())
    s2 = s2.strip().replace("\\", "_").replace("/", "_")
    if ".." in s2 or s2.startswith(("/", ".")):
        raise ValueError("bad path segment")
    return s2


def _folder_for_category(category: str) -> str:
    c = category.strip().lower()
    if c in {"floor", "floors"}:
        return "floors"
    if c in {"inside wall", "inside walls", "outside wall", "outside walls", "walls"}:
        return "walls"
    return str("decorations/"+_sanitize_segment(category).lower().replace(" ", "_"))


def _is_inside_wall(category: str) -> bool:
    return category.strip().lower() in {"inside wall", "inside walls", "wall inside", "inside"}


def _find_image_path(folder: str, name: str) -> Optional[Path]:
    nm = _sanitize_segment(name).lower().replace(" ", "_")
    for ext in (".png", ".webp"):
        p = ASSETS_ROOT / folder / f"{nm}{ext}"
        if p.exists():
            return p
    return None


async def _load_preview_bytes(path: Path, *, tint_inside: bool) -> bytes:
    loop = asyncio.get_running_loop()

    def _do():
        im = Image.open(path).convert("RGBA")
        if tint_inside:
            tint = Image.new("RGBA", im.size, (0, 0, 0, 196))
            im = Image.alpha_composite(im, tint)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    return await loop.run_in_executor(_EXEC, _do)


# --------------------------------------------------------------------
# Inventory list
# --------------------------------------------------------------------

async def _fetch_unplaced_inventory(conn, guild_id: int, user_id: int):
    """
    Returns list rows: (item_id, name, category, qty)
    Currently all owned copies are 'unused' because there is no placement yet.
    """
    rows = await conn.fetch("""
        SELECT i.item_id,
               i.name,
               i.category,
               COUNT(*)::int AS qty
          FROM base_inventory bi
          JOIN base_shop_items i ON i.item_id = bi.item_id
         WHERE bi.guild_id = $1
           AND bi.user_id  = $2
         GROUP BY i.item_id, i.name, i.category
         ORDER BY lower(i.category), lower(i.name)
    """, guild_id, user_id)
    return rows


def _inventory_pages(rows, per_page: int = 12):
    if not rows:
        return ["(No unused items.)"]

    cats: dict[str, list[asyncpg.Record]] = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r)

    lines: list[str] = []
    for cat in sorted(cats.keys(), key=lambda c: c.lower()):
        lines.append(f"__**{cat}**__")
        for r in cats[cat]:
            lines.append(f"• **{r['name']}** (#{r['item_id']}) — x{r['qty']}")

    pages = []
    for i in range(0, len(lines), per_page):
        pages.append("\n".join(lines[i:i + per_page]))
    return pages


# --------------------------------------------------------------------
# Shared fetch for a single item + costs
# --------------------------------------------------------------------

async def _fetch_item_and_costs(conn: asyncpg.Connection, item_id: int):
    row = await conn.fetchrow(
        "SELECT item_id, name, description, category FROM base_shop_items WHERE item_id = $1",
        item_id,
    )
    if not row:
        raise KeyError("no such item")
    cost_rows = await conn.fetch(
        "SELECT currency_item, amount FROM base_shop_item_costs WHERE item_id = $1 ORDER BY currency_item",
        item_id,
    )
    costs: Dict[str, int] = {r["currency_item"]: r["amount"] for r in cost_rows}
    return row, costs


def _format_costs(costs: Dict[str, int]) -> str:
    if not costs:
        return "free"
    parts = [f"{amt} × {cur}" for cur, amt in costs.items() if amt > 0]
    return " + ".join(parts) if parts else "free"


# --------------------------------------------------------------------
# UI: Browsing the shop
# --------------------------------------------------------------------

class BaseBrowseView(discord.ui.View):
    def __init__(self, ctx: commands.Context, pool, initial_category: str, categories: list[str]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.pool = pool
        self.category = initial_category
        self.categories = categories
        self.items_cache: dict[str, list[asyncpg.Record]] = {}
        self.costs_cache: dict[str, dict[int, dict[str, int]]] = {}
        self.idx = 0
        self.message: Optional[discord.Message] = None
        self._lock = asyncio.Lock()

        # seed dropdown options
        self.category_select.options = [
            discord.SelectOption(label=c, value=c, default=(c == initial_category))
            for c in categories
        ]

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    async def _load_category(self):
        async with self.pool.acquire() as con:
            if self.category not in self.items_cache:
                items = await _fetch_items_in_category(con, self.category)
                self.items_cache[self.category] = items
                ids = [r["item_id"] for r in items]
                self.costs_cache[self.category] = await _fetch_costs_map(con, ids)

    async def _item_embed_and_file(self, item: asyncpg.Record) -> tuple[discord.Embed, discord.File]:
        name = item["name"]
        category = item["category"]
        folder = _folder_for_category(category)
        path = _find_image_path(folder, name)
        if not path:
            buf = io.BytesIO()
            Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(buf, format="PNG")
            png_bytes = buf.getvalue()
        else:
            tint_inside = _is_inside_wall(category)
            png_bytes = await _load_preview_bytes(path, tint_inside=tint_inside)

        file = discord.File(io.BytesIO(png_bytes), filename="preview.png")

        costs = (self.costs_cache.get(self.category, {}).get(item["item_id"], {}))
        e = discord.Embed(
            title=name,
            description=item["description"] or "",
            color=discord.Color.blurple()
        )
        e.add_field(name="ID", value=str(item["item_id"]), inline=True)
        e.add_field(name="Category", value=category, inline=True)
        e.add_field(name="Price", value=_format_costs(costs), inline=False)
        e.set_footer(text=f"{self.idx+1} / {len(self.items_cache.get(self.category, []))} • Buy: {self.ctx.clean_prefix}base buy {item['item_id']}")
        e.set_image(url="attachment://preview.png")
        return e, file

    async def _send_first(self):
        await self._load_category()
        items = self.items_cache.get(self.category, [])
        if not items:
            self.prev_btn.disabled = True
            self.next_btn.disabled = True
            e = discord.Embed(
                title=f"Base Shop — {self.category}",
                description="No items in this category.",
                color=discord.Color.blurple()
            )
            self.message = await self.ctx.send(embed=e, view=self)
            return
        self.idx = 0
        self.prev_btn.disabled = True
        self.next_btn.disabled = (len(items) <= 1)
        e, file = await self._item_embed_and_file(items[self.idx])
        self.message = await self.ctx.send(embed=e, file=file, view=self)

    async def _update_message(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass

        await self._load_category()
        items = self.items_cache.get(self.category, [])
        self.idx = max(0, min(self.idx, max(0, len(items) - 1)))

        self.prev_btn.disabled = (self.idx <= 0)
        self.next_btn.disabled = (self.idx >= len(items) - 1)

        if not items:
            e = discord.Embed(
                title=f"Base Shop — {self.category}",
                description="No items in this category.",
                color=discord.Color.blurple()
            )
            if self.message:
                await self.message.edit(embed=e, attachments=[], view=self)
            return

        e, file = await self._item_embed_and_file(items[self.idx])
        if self.message:
            await self.message.edit(embed=e, attachments=[file], view=self)

    async def _reset_to_category(self, category: str):
        self.category = category
        self.idx = 0
        for o in self.category_select.options:
            o.default = (o.value == self.category)

    # ---- UI components ----
    @discord.ui.select(placeholder="Pick a category…", min_values=1, max_values=1, row=0)
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        async with self._lock:
            await self._reset_to_category(select.values[0])
            await self._update_message(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, _):
        async with self._lock:
            self.idx -= 1
            await self._update_message(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, _):
        async with self._lock:
            self.idx += 1
            await self._update_message(interaction)


# --------------------------------------------------------------------
# UI: Rooms viewer
# --------------------------------------------------------------------

class RoomsViewer(discord.ui.View):
    def __init__(self, ctx, pool, member: discord.Member, rooms: list[asyncpg.Record]):
        super().__init__(timeout=120)
        self.ctx, self.pool, self.member, self.rooms = ctx, pool, member, rooms
        self.idx = 0
        self.cache: dict[int, bytes] = {}  # room_id -> image bytes
        self.message: Optional[discord.Message] = None
        self._lock = asyncio.Lock()

        self.add_item(discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0))
        self.children[-1].callback = self._prev
        self.add_item(discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0))
        self.children[-1].callback = self._next

    async def start(self):
        e, file = await self._embed_and_file(self.rooms[self.idx])
        self.message = await self.ctx.send(embed=e, file=file, view=self)
        await self._update_buttons()

    async def _prev(self, interaction: discord.Interaction):
        async with self._lock:
            self.idx = (self.idx - 1) % len(self.rooms)
            await self._update(interaction)

    async def _next(self, interaction: discord.Interaction):
        async with self._lock:
            self.idx = (self.idx + 1) % len(self.rooms)
            await self._update(interaction)

    async def _update(self, interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        e, file = await self._embed_and_file(self.rooms[self.idx])
        await self._update_buttons()
        if self.message:
            await self.message.edit(embed=e, attachments=[file], view=self)

    async def _embed_and_file(self, room):
        async with self.pool.acquire() as con:
            placed = await _load_slots(con, room["room_id"])
            # Build int-only ID list for name lookup
            ids = sorted({int(v) for v in placed.values() if v is not None})
            name_rows = []
            if ids:
                name_rows = await con.fetch("""
                    SELECT item_id, name
                      FROM base_shop_items
                     WHERE item_id = ANY($1::bigint[])
                """, ids)
        id_to_name = {r["item_id"]: r["name"] for r in name_rows}
        flooring, inside, outline, decorations = _split_for_generate(placed, id_to_name)

        img_bytes = self.cache.get(room["room_id"])
        if not img_bytes:
            out = generate_base(
                room_type=room["room_type"],
                flooring=flooring,
                walls={"inside": inside, "outline": outline},
                decorations=decorations,
                lights={}, left_door=False, right_door=False
            )
            # out is BytesIO → cache its bytes
            out.seek(0)
            img_bytes = out.getvalue()
            self.cache[room["room_id"]] = img_bytes

        file = discord.File(io.BytesIO(img_bytes), filename="room.png")
        e = (discord.Embed(
            title=f"{self.member.display_name}'s Room #{room['room_id']} — {room['name']} ({room['room_type']})",
            color=discord.Color.blurple()
        ).set_image(url="attachment://room.png").set_footer(text=f"{self.idx+1}/{len(self.rooms)}"))
        return e, file

    async def _update_buttons(self):
        single = (len(self.rooms) <= 1)
        for c in self.children:
            if isinstance(c, discord.ui.Button):
                c.disabled = single


# --------------------------------------------------------------------
# UI: Decorator (place/clear items)
# --------------------------------------------------------------------

def _slot_categories(slot: str) -> list[str]:
    return [s.lower() for s in SLOT_TO_CATEGORIES.get(slot, [])]


class DecoratorView(discord.ui.View):
    def __init__(self, ctx: commands.Context, pool, rooms: list[asyncpg.Record], start_idx: int = 0):
        super().__init__(timeout=240)
        self.ctx = ctx
        self.pool = pool
        self.rooms = rooms
        self.room_idx = start_idx
        self.current_slot: Optional[str] = None
        self.current_item_id: Optional[int] = None
        self.message: Optional[discord.Message] = None
        self._lock = asyncio.Lock()

        self.room_select: Optional[discord.ui.Select] = None
        self.slot_select: Optional[discord.ui.Select] = None
        self.item_select: Optional[discord.ui.Select] = None

        self.add_item(discord.ui.Button(label="Preview", style=discord.ButtonStyle.secondary, row=3))
        self.children[-1].callback = self._on_preview
        self.add_item(discord.ui.Button(label="Confirm", style=discord.ButtonStyle.primary, row=3))
        self.children[-1].callback = self._on_confirm
        self.add_item(discord.ui.Button(label="Clear slot", style=discord.ButtonStyle.danger, row=3))
        self.children[-1].callback = self._on_clear

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    async def start(self):
        # Room select
        self.room_select = discord.ui.Select(
            placeholder="Pick a room…",
            min_values=1, max_values=1, row=0,
            options=[
                discord.SelectOption(
                    label=f"#{r['room_id']} {r['name']} ({r['room_type']})",
                    value=str(i), default=(i == self.room_idx)
                ) for i, r in enumerate(self.rooms)
            ]
        )
        self.room_select.callback = self._on_room_select
        self.add_item(self.room_select)

        # Slot select
        self.slot_select = discord.ui.Select(
            placeholder="Pick a slot…",
            min_values=1, max_values=1, row=1,
            options=[discord.SelectOption(label=s, value=s) for s in SLOT_TO_CATEGORIES.keys()]
        )
        self.slot_select.callback = self._on_slot_select
        self.add_item(self.slot_select)

        embed = await self._build_embed(preview=False)
        self.message = await self.ctx.send(embed=embed, view=self)

    async def _on_room_select(self, interaction: discord.Interaction):
        async with self._lock:
            self.room_idx = int(self.room_select.values[0])
            self.current_slot = None
            self.current_item_id = None
            await self._remove_item_select()
            await self._refresh_b(interaction)

    async def _on_slot_select(self, interaction: discord.Interaction):
        async with self._lock:
            self.current_slot = self.slot_select.values[0]
            self.current_item_id = None
            await self._rebuild_item_select()
            await self._refresh_b(interaction)

    async def _remove_item_select(self):
        if self.item_select and self.item_select in self.children:
            self.remove_item(self.item_select)
        self.item_select = None

    async def _rebuild_item_select(self):
        await self._remove_item_select()
        if not self.current_slot:
            return
        guild_id, user_id = gid_from_ctx(self.ctx), self.ctx.author.id
        cats = _slot_categories(self.current_slot)  # lowercased list

        async with self.pool.acquire() as con:
            rows = await con.fetch("""
                SELECT i.item_id, i.name, COUNT(*)::int AS qty
                  FROM base_inventory bi
                  JOIN base_shop_items i ON i.item_id = bi.item_id
                 WHERE bi.guild_id=$1
                   AND bi.user_id=$2
                   AND lower(i.category) = ANY($3::text[])
                 GROUP BY i.item_id, i.name
                 ORDER BY lower(i.name)
            """, guild_id, user_id, cats)

        if rows:
            options = [discord.SelectOption(label=f"{r['name']} (x{r['qty']})", value=str(r["item_id"]))
                       for r in rows]
        else:
            options = [discord.SelectOption(label="No compatible items owned", value="__none__", default=True)]

        self.item_select = discord.ui.Select(
            placeholder=f"Pick an item for {self.current_slot}…",
            min_values=1, max_values=1,
            options=options, row=2
        )

        async def _cb(interaction: discord.Interaction):
            async with self._lock:
                val = self.item_select.values[0]
                self.current_item_id = None if val == "__none__" else int(val)
                await self._refresh_b(interaction)

        self.item_select.callback = _cb
        self.add_item(self.item_select)

    async def _on_preview(self, interaction: discord.Interaction):
        async with self._lock:
            embed = await self._build_embed(preview=True)
            await self._edit(interaction, embed)

    async def _on_confirm(self, interaction: discord.Interaction):
        async with self._lock:
            if not self.current_slot or not self.current_item_id:
                return await self._toast(interaction, "Pick a slot and an item first.")
            room = self.rooms[self.room_idx]
            guild_id, user_id = gid_from_ctx(self.ctx), self.ctx.author.id

            async with self.pool.acquire() as con, con.transaction():
                own = await con.fetchval("""
                    SELECT 1 FROM base_rooms WHERE room_id=$1 AND guild_id=$2 AND user_id=$3
                """, room["room_id"], guild_id, user_id)
                if not own:
                    return await self._toast(interaction, "You don't own that room.")

                if await _inv_count(con, guild_id, user_id, self.current_item_id) <= 0:
                    return await self._toast(interaction, "You no longer own that item.")

                took = await _inv_take_one(con, guild_id, user_id, self.current_item_id)
                if not took:
                    return await self._toast(interaction, "Failed to take item from inventory.")

                prev = await _set_slot(con, guild_id, user_id, room["room_id"], self.current_slot, self.current_item_id)
                if prev and prev != self.current_item_id:
                    await _inv_give_one(con, guild_id, user_id, prev)

            await self._refresh_b(interaction, toast="Saved!")

    async def _on_clear(self, interaction: discord.Interaction):
        async with self._lock:
            if not self.current_slot:
                return await self._toast(interaction, "Pick a slot first.")
            room = self.rooms[self.room_idx]
            guild_id, user_id = gid_from_ctx(self.ctx), self.ctx.author.id

            async with self.pool.acquire() as con, con.transaction():
                prev = await _clear_slot(con, room["room_id"], self.current_slot)
                if prev:
                    await _inv_give_one(con, guild_id, user_id, prev)

            await self._refresh_b(interaction, toast="Cleared.")

    async def _build_embed(self, preview: bool) -> discord.Embed:
        room = self.rooms[self.room_idx]

        # Current persisted placements and name cache
        async with self.pool.acquire() as con:
            placed = await _load_slots(con, room["room_id"])

            # Merge transient selection (for preview info) BEFORE building ids
            if self.current_slot and self.current_item_id:
                placed[self.current_slot] = int(self.current_item_id)

            ids = sorted({int(v) for v in placed.values() if v is not None})
            name_rows = []
            if ids:
                name_rows = await con.fetch(
                    "SELECT item_id, name FROM base_shop_items WHERE item_id = ANY($1::bigint[])",
                    ids
                )
        id_to_name = {r["item_id"]: r["name"] for r in name_rows}

        flooring, inside, outline, decorations = _split_for_generate(placed, id_to_name)

        title = f"Decorate: #{room['room_id']} {room['name']} ({room['room_type']})"
        e = discord.Embed(
            title=title,
            description=f"Slot: `{self.current_slot or '—'}` • Item: `{(id_to_name.get(self.current_item_id) if self.current_item_id else '—')}`",
            color=discord.Color.green()
        )
        e.add_field(name="Floor", value=flooring or FALLBACKS["flooring"], inline=True)
        e.add_field(name="Inside wall", value=inside or FALLBACKS["inside_wall"], inline=True)
        e.add_field(name="Outline wall", value=outline or FALLBACKS["outline_wall"], inline=True)

        if preview:
            buf = generate_base(
                room_type=room["room_type"],
                flooring=flooring,
                walls={"inside": inside, "outline": outline},
                decorations=decorations,
                lights={},
                left_door=False, right_door=False
            )
            buf.seek(0)
            f = discord.File(buf, filename="preview.png")
            e.set_image(url="attachment://preview.png")
            if self.message:
                await self.message.edit(attachments=[f], embed=e, view=self)
        return e

    async def _refresh_b(self, interaction: discord.Interaction, toast: Optional[str] = None):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        embed = await self._build_embed(preview=False)
        if self.message:
            await self.message.edit(embed=embed, view=self)
        if toast:
            await self._toast(interaction, toast)

    async def _edit(self, interaction: discord.Interaction, embed: discord.Embed):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        if self.message:
            await self.message.edit(embed=embed, view=self)

    async def _toast(self, interaction: discord.Interaction, msg: str):
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            try:
                await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass


# --------------------------------------------------------------------
# Cog
# --------------------------------------------------------------------

class BaseViewCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot  # expects bot.db_pool

    @commands.group(name="base", invoke_without_command=True)
    async def base_group(self, ctx: commands.Context, *args):
        await ctx.send(f"Use `{ctx.clean_prefix}base rooms <user>` to look around someones base.")

    @base_group.command(name="shop")
    async def base_shop_cmd(self, ctx: commands.Context):
        await base_shop.base_shop_run(self.bot.db_pool, ctx)

    @base_group.command(name="browse")
    async def base_browse(self, ctx: commands.Context, *, category: Optional[str] = None):
        """Browse items by category with arrows and a category dropdown."""
        async with self.bot.db_pool.acquire() as con:
            cats = await _fetch_categories(con)
        if not cats:
            return await ctx.send("There are no categories in the base shop yet.")

        if category:
            cat_map = {c.lower(): c for c in cats}
            chosen = cat_map.get(category.lower())
            if not chosen:
                return await ctx.send(f"Unknown category **{category}**. Try one of: " + ", ".join(cats))
        else:
            chosen = cats[0]

        view = BaseBrowseView(ctx, self.bot.db_pool, chosen, cats)
        await view._send_first()

    @base_group.command(name="view")
    async def base_view(self, ctx: commands.Context, item_id: int):
        """Preview a base shop item by ID (embed with image, name, price, id)."""
        async with self.bot.db_pool.acquire() as con:
            try:
                row, costs = await _fetch_item_and_costs(con, item_id)
            except KeyError:
                return await ctx.send(f"❌ No item with ID **{item_id}**.")

        name = row["name"]
        category = row["category"]
        folder = _folder_for_category(category)

        img_path = _find_image_path(folder, name)
        if not img_path:
            return await ctx.send(
                f"❌ Image not found for **{name}**. Looked in `assets/house/decorations/{folder}/`."
            )

        tint_inside = _is_inside_wall(category)

        try:
            png_bytes = await _load_preview_bytes(img_path, tint_inside=tint_inside)
        except Exception as e:
            return await ctx.send(f"❌ Failed to load image: {e!s}")

        file = discord.File(io.BytesIO(png_bytes), filename="preview.png")
        e = discord.Embed(
            title=name,
            description=row["description"] or "",
            color=discord.Color.blurple(),
        )
        e.add_field(name="ID", value=str(item_id), inline=True)
        e.add_field(name="Category", value=category, inline=True)
        e.add_field(name="Price", value=_format_costs(costs), inline=False)
        e.set_image(url="attachment://preview.png")

        await ctx.send(embed=e, file=file)

    @base_group.command(name="decorate")
    async def base_decorate(self, ctx: commands.Context, room_id: Optional[int] = None):
        gid, uid = gid_from_ctx(ctx), ctx.author.id
        async with self.bot.db_pool.acquire() as con:
            rooms = await con.fetch("""
                SELECT room_id, room_type, name
                  FROM base_rooms
                 WHERE guild_id=$1 AND user_id=$2
                 ORDER BY room_id
            """, gid, uid)
        if not rooms:
            return await ctx.send("You don't own any rooms. Buy one with `!base upgrades`.")
        start = 0
        if room_id is not None:
            for i, r in enumerate(rooms):
                if r["room_id"] == room_id:
                    start = i
                    break
        view = DecoratorView(ctx, self.bot.db_pool, rooms, start)
        await view.start()

    @base_group.command(name="rooms")
    async def base_rooms(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        target = user or ctx.author
        gid = gid_from_ctx(ctx)
        async with self.bot.db_pool.acquire() as con:
            rooms = await con.fetch("""
                SELECT room_id, room_type, name
                  FROM base_rooms
                 WHERE guild_id=$1 AND user_id=$2
                 ORDER BY room_id
            """, gid, target.id)
        if not rooms:
            return await ctx.send(f"{target.display_name} doesn't own any rooms yet.")
        view = RoomsViewer(ctx, self.bot.db_pool, target, rooms)
        await view.start()

    @base_group.group(name="upgrades", invoke_without_command=True)
    async def base_upgrades(self, ctx: commands.Context):
        """List all room upgrades (one per room type)."""
        gid, uid = gid_from_ctx(ctx), ctx.author.id

        async with self.bot.db_pool.acquire() as con:
            ups = await _up_fetch_all(con)
            if not ups:
                return await ctx.send("No room upgrades are available right now.")
            costs = await _up_costs_map(con, [u["upgrade_id"] for u in ups])
            owned = await _owned_room_types(con, gid, uid)

        e = discord.Embed(title="🏠 House Upgrades", color=discord.Color.gold())
        for u in ups:
            up_id = u["upgrade_id"]
            name = u["name"]
            desc = u["description"] or ""
            rtype = u["room_type"]
            have = (rtype in owned)
            lines = []
            if desc:
                lines.append(desc)
            lines.append(f"**Room type:** `{rtype}` • **Status:** {'✅ Owned' if have else '🛒 Buyable'}")
            if not have:
                lines.append(f"**Price:** {_fmt_costs(costs.get(up_id, {}))}")
                lines.append(f"Buy: `{ctx.clean_prefix}base upgrades buy {up_id}`")
            e.add_field(name=f"#{up_id} — {name}", value="\n".join(lines), inline=False)

        e.set_footer(text="Each room type can be purchased once per user.")
        await ctx.send(embed=e)

    @base_upgrades.command(name="buy")
    async def base_upgrades_buy(self, ctx: commands.Context, upgrade_id: int):
        """Buy a room upgrade (one per type)."""
        gid, uid = gid_from_ctx(ctx), ctx.author.id

        async with self.bot.db_pool.acquire() as con:
            up = await con.fetchrow("""
                SELECT upgrade_id, name, description, room_type, disabled
                  FROM upgrades_shop_items
                 WHERE upgrade_id=$1
            """, upgrade_id)
            if not up:
                return await ctx.send("❌ Unknown upgrade id.")
            if up["disabled"]:
                return await ctx.send("❌ That upgrade is not available right now.")

            room_type = up["room_type"]
            already = await con.fetchval("""
                SELECT 1 FROM base_rooms WHERE guild_id=$1 AND user_id=$2 AND room_type=$3
            """, gid, uid, room_type)
            if already:
                return await ctx.send(f"❌ You already own the **{room_type}** room.")

            rows = await con.fetch("""
                SELECT currency_item, amount FROM upgrades_shop_costs WHERE upgrade_id=$1
            """, upgrade_id)
            costs = {r["currency_item"]: r["amount"] for r in rows}

            deficits = []
            for cur, amt in costs.items():
                have = await get_items(con, uid, cur, gid)
                if have < amt:
                    deficits.append((cur, amt, have))
            if deficits:
                msg = ["❌ Not enough:"]
                msg += [f"• {c}: need **{n}**, have **{h}**" for c, n, h in deficits]
                return await ctx.send("\n".join(msg))

            async with con.transaction():
                for cur, amt in costs.items():
                    if amt > 0:
                        await take_items(uid, cur, amt, con, gid)

                try:
                    await con.execute("""
                        INSERT INTO base_rooms (guild_id, user_id, room_type, seed, name)
                        VALUES ($1,$2,$3,(random()*2147483647)::int,$4)
                    """, gid, uid, room_type, up["name"])
                except asyncpg.UniqueViolationError:
                    # rare race: refund and tell the user
                    for cur, amt in costs.items():
                        if amt > 0:
                            await give_items(uid, cur, amt, "items", False, con, gid)
                    return await ctx.send("❌ Looks like you already got that room in a parallel action. Refunded.")

        await ctx.send(f"🏠 Upgrade purchased: **{up['name']}** → unlocked **{room_type}** room.")

    @base_group.command(name="inv")
    async def base_inventory(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """
        Show a user's UNUSED base items (grouped & counted).
        Usage: !base inv [@user]
        """
        target = user or ctx.author
        guild_id = ctx.guild.id
        user_id = target.id

        async with self.bot.db_pool.acquire() as con:
            rows = await _fetch_unplaced_inventory(con, guild_id, user_id)

        pages = _inventory_pages(rows, per_page=12)
        view = BaseInvView(ctx, target.display_name, pages)
        await view.send_first()

    @base_group.command(name="buy")
    async def base_buy(self, ctx: commands.Context, item_id: int, qty: Optional[int] = None):
        """Buy base shop items by ID. Usage: !base buy <id> [qty]"""
        quantity = 1 if qty is None else max(1, int(qty))
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        async with self.bot.db_pool.acquire() as con:
            item = await con.fetchrow(
                "SELECT item_id, name, disabled FROM base_shop_items WHERE item_id=$1",
                item_id,
            )
            if not item:
                return await ctx.send(f"❌ No base shop item with ID **{item_id}**.")
            if item["disabled"]:
                return await ctx.send("❌ That item is not available right now.")

            name = item["name"]

            rows = await con.fetch(
                "SELECT currency_item, amount FROM base_shop_item_costs WHERE item_id=$1",
                item_id,
            )
            costs = {r["currency_item"]: r["amount"] for r in rows}
            total_costs = {cur: amt * quantity for cur, amt in costs.items() if amt > 0}

            deficits = []
            for cur, need in total_costs.items():
                have = await get_items(con, user_id, cur, guild_id)
                if have < need:
                    deficits.append((cur, need, have))
            if deficits and not IS_DEV:
                msg = ["❌ Not enough currency:"]
                for cur, need, have in deficits:
                    msg.append(f"• {cur}: need **{need}**, have **{have}**")
                return await ctx.send("\n".join(msg))

            async with con.transaction():
                for cur, need in total_costs.items():
                    if need > 0 and not IS_DEV:
                        await take_items(user_id, cur, need, con, guild_id)

                await con.execute("""
                    INSERT INTO base_inventory (guild_id, user_id, item_id)
                    SELECT $1, $2, $3 FROM generate_series(1, $4)
                """, guild_id, user_id, item_id, quantity)

        def fmt_costs(c: dict[str, int]) -> str:
            if not c:
                return "free"
            return " + ".join(f"{amt} × {cur}" for cur, amt in c.items())

        unit_price = fmt_costs(costs)
        total_price = fmt_costs(total_costs)
        if quantity == 1:
            await ctx.send(f"✅ You bought **{name}** (#{item_id}) • **Price:** {unit_price}")
        else:
            await ctx.send(
                f"✅ You bought **{quantity}× {name}** (#{item_id}) • Unit: {unit_price} • Total: {total_price}"
            )


# --------------------------------------------------------------------
# Upgrades helpers
# --------------------------------------------------------------------

async def _up_fetch_all(conn):
    return await conn.fetch("""
        SELECT upgrade_id, name, description, room_type, sort_order, disabled
          FROM upgrades_shop_items
         WHERE NOT disabled
         ORDER BY sort_order, upgrade_id
    """)


async def _up_costs_map(conn, ids: list[int]) -> dict[int, dict[str, int]]:
    if not ids:
        return {}
    rows = await conn.fetch("""
        SELECT upgrade_id, currency_item, amount
          FROM upgrades_shop_costs
         WHERE upgrade_id = ANY($1::bigint[])
         ORDER BY currency_item
    """, ids)
    out: dict[int, dict[str, int]] = {}
    for r in rows:
        out.setdefault(r["upgrade_id"], {})[r["currency_item"]] = r["amount"]
    return out


async def _owned_room_types(conn, guild_id: int, user_id: int) -> set[str]:
    rows = await conn.fetch(
        "SELECT room_type FROM base_rooms WHERE guild_id=$1 AND user_id=$2",
        guild_id, user_id
    )
    return {r["room_type"] for r in rows}


def _fmt_costs(costs: dict[str, int]) -> str:
    return " + ".join(f"{amt} × {cur}" for cur, amt in costs.items() if amt > 0) or "free"


# --------------------------------------------------------------------
# Inventory view UI
# --------------------------------------------------------------------

class BaseInvView(discord.ui.View):
    def __init__(self, ctx: commands.Context, username: str, pages: list[str]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.username = username
        self.pages = pages
        self.idx = 0
        self.message: Optional[discord.Message] = None
        self._lock = asyncio.Lock()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def _embed(self):
        e = discord.Embed(
            title=f"{self.username}'s Base Inventory (unused)",
            description=self.pages[self.idx],
            color=discord.Color.green()
        )
        e.set_footer(text=f"Page {self.idx+1}/{len(self.pages)}")
        return e

    async def send_first(self):
        self.prev_btn.disabled = True
        self.next_btn.disabled = (len(self.pages) <= 1)
        self.message = await self.ctx.send(embed=self._embed(), view=self)

    async def _update(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass
        self.idx = max(0, min(self.idx, len(self.pages) - 1))
        self.prev_btn.disabled = (self.idx <= 0)
        self.next_btn.disabled = (self.idx >= len(self.pages) - 1)
        if self.message:
            await self.message.edit(embed=self._embed(), view=self)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, _):
        async with self._lock:
            self.idx -= 1
            await self._update(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, _):
        async with self._lock:
            self.idx += 1
            await self._update(interaction)


# --------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------
async def setup(bot):
    # 1) Sync the shops from the catalogs above (idempotent, safe)
    try:
        await sync_shops_from_code(bot.db_pool)
    except Exception as e:
        # Don't block the cog if sync fails; just log to your console
        print(f"[Base] Shop sync failed: {e!r}")

    # 2) Register the cog
    await bot.add_cog(BaseViewCog(bot))
