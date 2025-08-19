# room_gen.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Union, Iterable
from PIL import Image, ImageChops, ImageDraw
from pathlib import Path
import io, os, random, math

TILE = 64
ASSETS_BASE = Path("assets/house")

# ---- Lighting / shading tunables ----
INSIDE_TINT_A = 196  # base alpha for inside shading (0..255)
# light level -> (radius in tiles, strength 0..1 where 1 cuts all tint at center)
LIGHT_LEVELS = {
    1: (2.0, 0.60),
    2: (3.0, 0.80),
    3: (4.0, 1.00),
}

Edge = str            # {"N","E","S","W"}
TileXY = Tuple[int,int]

# --- Optional aliases so multiple keys share the same folder (no randomness) ---
DECORATION_TYPE_MAP: Dict[str, str] = {
    "poster1": "posters",
    "poster2": "posters",
    "poster3": "posters",
    "furniture1": "furniture",
    "furniture2": "furniture",
}

@dataclass
class RoomConfig:
    size_tiles: Tuple[int, int]
    open_edges: set[Edge] = field(default_factory=lambda: {"S"})
    decoration_spots: Dict[str, Union[List[TileXY], TileXY, List[int]]] = field(default_factory=dict)
    light_spots: Dict[str, Union[List[TileXY], TileXY, List[int]]] = field(default_factory=dict)
    fill_inside_walls_first: bool = True
    seed: Optional[int] = None

    # Floors & stairs (heights measured in tiles above ground; origin bottom-left)
    second_floor_height: Optional[int] = None                  # tiles above ground
    third_floor_height: Optional[int] = None                   # tiles above ground
    second_floor_stairs: Optional[Tuple[int, str]] = None      # (x, "l"|"r"), ground -> second
    third_floor_stairs: Optional[Tuple[int, str]] = None       # (x, "l"|"r"), second -> third
    # Per-floor "continue" options (True = draw full platform; False = leave gap along stair run)
    second_floor_continue: bool = True
    third_floor_continue: bool = True

ROOM_TYPES: Dict[str, RoomConfig] = {
    "basic_room": RoomConfig(
        size_tiles=(10, 5),
        open_edges={"S"},
        decoration_spots={
            "beds":[(6, 4)],
            "furniture1":[(8, 4)],
            "furniture2":[(2, 4)],
            "poster1":[(7, 2)],
            "poster2":[(5, 2)],
            "poster3":[(3, 2)],
            "pet_house":[(4,3)],
            "pets":[(4,4)]
        },
        light_spots={
            "bg_torch": [(4, 2)],
            "window": [(2,2)]
        },
        seed=None,

        # Examples (uncomment to test):
        # second_floor_height=3,
        # third_floor_height=4,
        # second_floor_stairs=(2, "r"),
        # third_floor_stairs=(7, "l"),
        # second_floor_continue=False,
        # third_floor_continue=True,
    ),
    "large_room": RoomConfig(
        size_tiles=(15, 10),
        open_edges={"S"},
        decoration_spots={
            "bed":[(6, 9)],
            "furniture1":[(8, 9)],
            "furniture2":[(2, 9)],
            "poster1":[(7, 7)],
            "poster2":[(5, 7)],
            "poster3":[(3, 7)],
            "pet_house":[(4,8)],
            "pet":[(4,9)]
        },
        light_spots={
            "bg_torch": [(4, 2)],
            "window": [(2,2)]
        },
        seed=None,
        second_floor_height=4,
        third_floor_height=7,
        second_floor_stairs=(1, "r"),
        third_floor_stairs=(12, "l"),
        second_floor_continue=False,
        third_floor_continue=False,
    ),
}

# -------- Path helpers --------
def _with_png(name: str) -> str:
    return name if name.lower().endswith((".png",".webp")) else f"{name}.png"

def _floor_path(name: str) -> Path:
    return ASSETS_BASE / "floors" / _with_png(name)

def _wall_path(name: str) -> Path:
    return ASSETS_BASE / "walls" / _with_png(name)

def _load_image_square(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    if img.size != (TILE, TILE):
        raise ValueError(f"Tile at '{path}' must be {TILE}x{TILE}, got {img.size}")
    return img

def _gather_images_in_dir(dir_path: Path) -> List[Path]:
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    exts = {".png", ".webp"}
    out: List[Path] = []
    for root, _, files in os.walk(dir_path):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in exts:
                out.append(p)
    return out

def _first_existing_file(base: Path, rel_parts: Iterable[str], exts: Iterable[str] = (".png",".webp")) -> Optional[Path]:
    stem = base.joinpath(*rel_parts)
    if stem.suffix:
        return stem if stem.exists() else None
    for ext in exts:
        p = stem.with_suffix(ext)
        if p.exists():
            return p
    return None

def _pick_random_deco(room_type: str, deco_type: str, variation: str) -> Image.Image:
    # Try direct files first (deterministic)
    file_roots = [
        (ASSETS_BASE, (room_type, "decorations", deco_type, variation)),
        (ASSETS_BASE, ("decorations", deco_type, variation)),
        (ASSETS_BASE, (deco_type, variation)),
    ]
    for base, parts in file_roots:
        p = _first_existing_file(base, parts)
        if p:
            return Image.open(p).convert("RGBA")

    # Then folders (deterministic: pick first in lexicographic order)
    dir_roots = [
        ASSETS_BASE / room_type / "decorations" / deco_type / variation,
        ASSETS_BASE / "decorations" / deco_type / variation,
        ASSETS_BASE / deco_type / variation,
    ]
    for root in dir_roots:
        cands = _gather_images_in_dir(root)
        if cands:
            p = sorted(cands)[0]  # NO RANDOMNESS
            return Image.open(p).convert("RGBA")

    tried = []
    for base, parts in file_roots:
        stem = Path(base).joinpath(*parts)
        if stem.suffix:
            tried.append(str(stem))
        else:
            tried.append(str(stem.with_suffix(".png")))
            tried.append(str(stem.with_suffix(".webp")))
    tried += [str(d) for d in dir_roots]
    raise FileNotFoundError(f"No decoration images found for '{deco_type}:{variation}'. Tried:\n  - " + "\n  - ".join(tried))

# -------- Normalization helpers --------
def _normalize_spots(positions: Union[List[TileXY], TileXY, List[int]]) -> List[TileXY]:
    if isinstance(positions, tuple) and len(positions) == 2 and all(isinstance(v,int) for v in positions):
        return [positions]
    if isinstance(positions, list):
        if positions and all(isinstance(p, tuple) and len(p)==2 for p in positions):
            return [(int(x),int(y)) for x,y in positions]
        if len(positions) == 2 and all(isinstance(v,int) for v in positions):
            return [(int(positions[0]), int(positions[1]))]
        if len(positions) % 2 == 0 and all(isinstance(v,int) for v in positions):
            it = iter(positions)
            return [(int(x), int(y)) for x,y in zip(it,it)]
    raise TypeError(f"Invalid spots: {positions!r}")

def _parse_color(c: Optional[Union[str, Tuple[int,int,int]]]) -> Optional[Tuple[int,int,int]]:
    if c is None:
        return None
    if isinstance(c, tuple) and len(c)==3:
        return tuple(int(max(0,min(255,v))) for v in c)  # clamp
    s = str(c).strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s)==6:
        r = int(s[0:2],16); g = int(s[2:4],16); b = int(s[4:6],16)
        return (r,g,b)
    raise ValueError(f"Bad color: {c!r}. Use '#rrggbb' or (r,g,b) or None.")

# -------- Drawing helpers --------
def _tile_area(base: Image.Image, tile_img: Image.Image, x0: int, y0: int, w_tiles: int, h_tiles: int):
    for ty in range(h_tiles):
        for tx in range(w_tiles):
            base.alpha_composite(tile_img, ((x0+tx)*TILE, (y0+ty)*TILE))

def _door_gap_rows(h: int) -> List[int]:
    # With half-tile floor (canvas is h_tiles + 0.5 tall), gap is the last two full rows.
    if h < 2: return []
    return [h-2, h-1]

def _draw_outline(base: Image.Image, outline_tile: Image.Image, size: Tuple[int,int], open_edges: set[Edge], *, left_door=False, right_door=False):
    w,h = size
    if "N" not in open_edges:
        for x in range(w):
            base.alpha_composite(outline_tile, (x*TILE, 0))
    if "S" not in open_edges:
        for x in range(w):
            base.alpha_composite(outline_tile, (x*TILE, (h-1)*TILE))
    door_rows = set(_door_gap_rows(h))
    if "W" not in open_edges:
        for y in range(h):
            if left_door and y in door_rows: continue
            base.alpha_composite(outline_tile, (0, y*TILE))
    if "E" not in open_edges:
        for y in range(h):
            if right_door and y in door_rows: continue
            base.alpha_composite(outline_tile, ((w-1)*TILE, y*TILE))

def _platform_y_top(H: int, h_tiles: int) -> int:
    """Y pixel to paste the TOP of a half-floor at 'h_tiles' above ground."""
    return H - TILE//2 - h_tiles*TILE

def _draw_half_floor_strip(canvas: Image.Image, half_tile: Image.Image, y_top: int, omit_columns: Optional[set[int]] = None):
    """Draw a horizontal strip of half-tiles across full room width, optionally omitting some columns."""
    W, H = canvas.size
    w_tiles = W // TILE
    omit = omit_columns or set()
    for tx in range(w_tiles):
        if tx in omit: 
            continue
        canvas.alpha_composite(half_tile, (tx*TILE, y_top))

def _stair_run_columns(x_start: int, rise_tiles: int, dir_lr: str, w_tiles: int) -> List[int]:
    """Columns touched if using 1 tile per vertical tile; still useful as an approximation for gap logic."""
    cols = []
    if dir_lr == "r":
        for i in range(rise_tiles):
            x = x_start + i
            if 0 <= x < w_tiles:
                cols.append(x)
    else:  # "l"
        for i in range(rise_tiles):
            x = x_start - i
            if 0 <= x < w_tiles:
                cols.append(x)
    return cols

# -------- New: half-step stairs (half across, half up per step) --------
def _draw_stairs_halfsteps(canvas: Image.Image, floor_half: Image.Image, base_height: int, top_height: int, x_start: int, dir_lr: str):
    """
    Stairs made of TOP-HALF floor tiles (TILE x TILE//2).
    Each step moves half a tile across and half a tile up (Δx = TILE//2, Δy = TILE//2).
    """
    if top_height is None or base_height is None:
        return
    rise = top_height - base_height
    if rise <= 0:
        return

    W, H = canvas.size
    w_tiles = W // TILE
    step_w = TILE // 2
    step_h = TILE // 2

    # Starting pixel positions
    x0 = x_start * TILE
    y0 = _platform_y_top(H, base_height)  # top of the ground/second platform row

    # Number of half-steps to climb the vertical rise
    steps = 2 * rise

    for i in range(steps):
        # horizontal position
        if dir_lr == "r":
            x = x0 + i * step_w
        else:
            x = x0 - i * step_w

        # vertical position (moving up reduces y)
        y = y0 - i * step_h

        # bounds: allow slightly off-left but skip draws outside canvas
        if x < -TILE or x > W:
            continue

        canvas.alpha_composite(floor_half, (int(x), int(y)))

# ------------- Main generator -------------
def generate_base(
    room_type: str,
    flooring: str,                 # "dirt" -> assets/house/floors/dirt.png
    walls: Dict[str, str],         # {"inside": "brick", "outline": "brick"} (names under walls/)
    decorations: Dict[str, str],   # {"bed": "red"}
    *,
    lights: Dict[str, Tuple[str, int, Optional[Union[str,Tuple[int,int,int]]]]] = None,
    left_door: bool = False,
    right_door: bool = False,
) -> io.BytesIO:
    """
    lights: mapping type -> (variation, level{1..3}, color or None)
      e.g., {"lamp": ("var1", 2, "#ffc080")}
            {"torch": ("default", 3, None)}  # removes tint in that area
    """
    if room_type not in ROOM_TYPES:
        raise KeyError(f"Unknown room_type '{room_type}'. Available: {list(ROOM_TYPES)}")
    cfg = ROOM_TYPES[room_type]
    if cfg.seed is not None:
        random.seed(cfg.seed)

    w_tiles, h_tiles = cfg.size_tiles
    W = w_tiles * TILE
    H = h_tiles * TILE + TILE//2  # extra half-tile for the ground

    canvas = Image.new("RGBA", (W, H), (0,0,0,0))

    # --- Inside walls (untinted; we add a separate tint overlay later)
    if cfg.fill_inside_walls_first:
        inside_name = walls.get("inside") or walls.get("outline") or next(iter(walls.values()))
        inside_tile = _load_image_square(_wall_path(inside_name))
        _tile_area(canvas, inside_tile, 0, 0, w_tiles, h_tiles)

    # --- Floor tiles (assets)
    floor_tile_full = _load_image_square(_floor_path(flooring))
    floor_tile_half = floor_tile_full.crop((0, 0, TILE, TILE//2))  # top half of tile

    # --- Ground half-floor at bottom (y from bottom-left origin)
    ground_y = H - TILE//2
    for tx in range(w_tiles):
        canvas.alpha_composite(floor_tile_half, (tx*TILE, ground_y))

    # --- Build the inside shading layer (black tint to be modified by lights)
    tint_layer = Image.new("RGBA", (W, H), (0,0,0,0))
    base_tint = Image.new("RGBA", (TILE, TILE), (0,0,0,INSIDE_TINT_A))
    for ty in range(h_tiles):
        for tx in range(w_tiles):
            tint_layer.alpha_composite(base_tint, (tx*TILE, ty*TILE))

    # (Option to apply _apply_lights_to_tint later)
    canvas = Image.alpha_composite(canvas, tint_layer)

    # ---------------- Platforms & Stairs ----------------
    # Compute omit columns per floor if "continue" is False (leave a gap along stair run)
    omit_cols_2 = set()
    omit_cols_3 = set()

    # Second floor omit
    if cfg.second_floor_height is not None and cfg.second_floor_height > 0 and cfg.second_floor_stairs and not cfg.second_floor_continue:
        sx, sdir = cfg.second_floor_stairs
        rise2 = cfg.second_floor_height  # from ground
        omit_cols_2 = set(_stair_run_columns(sx, rise2, sdir, w_tiles))

    # Third floor omit
    if (cfg.third_floor_height is not None and cfg.third_floor_height > 0 and
        cfg.second_floor_height is not None and cfg.third_floor_stairs and not cfg.third_floor_continue):
        sx3, sdir3 = cfg.third_floor_stairs
        rise3 = cfg.third_floor_height - cfg.second_floor_height
        if rise3 > 0:
            omit_cols_3 = set(_stair_run_columns(sx3, rise3, sdir3, w_tiles))

    # Draw second floor platform (half tiles)
    if cfg.second_floor_height is not None and cfg.second_floor_height > 0:
        y2 = _platform_y_top(H, cfg.second_floor_height)
        _draw_half_floor_strip(canvas, floor_tile_half, y2, omit_columns=omit_cols_2)

    # Draw third floor platform (half tiles)
    if cfg.third_floor_height is not None and cfg.third_floor_height > 0:
        y3 = _platform_y_top(H, cfg.third_floor_height)
        _draw_half_floor_strip(canvas, floor_tile_half, y3, omit_columns=omit_cols_3)

    # Stairs (half-step) drawn ON TOP of platforms
    if cfg.second_floor_height is not None and cfg.second_floor_height > 0 and cfg.second_floor_stairs:
        sx, sdir = cfg.second_floor_stairs
        _draw_stairs_halfsteps(canvas, floor_tile_half, 0, cfg.second_floor_height, sx, sdir)

    if (cfg.second_floor_height is not None and cfg.third_floor_height is not None and
        cfg.third_floor_height > cfg.second_floor_height and cfg.third_floor_stairs):
        sx3, sdir3 = cfg.third_floor_stairs
        _draw_stairs_halfsteps(canvas, floor_tile_half, cfg.second_floor_height, cfg.third_floor_height, sx3, sdir3)

    # ---------------- Lights ----------------
    lights = lights or {}
    lights_effects: List[Tuple[int,int,int,int,float,Optional[Tuple[int,int,int]]]] = []
    for light_type, raw_positions in cfg.light_spots.items():
        spec = lights.get(light_type)
        if not spec:
            continue
        # spec: (variation, level, color)
        try:
            variation, level, color_raw = spec
        except Exception:
            raise ValueError(f"Light spec for '{light_type}' must be (variation, level, color_or_None)")
        if level not in LIGHT_LEVELS:
            raise ValueError(f"Light level for '{light_type}' must be 1,2,or 3")
        color = _parse_color(color_raw)
        radius_tiles, strength = LIGHT_LEVELS[level]

        positions = _normalize_spots(raw_positions)
        for (tx, ty) in positions:
            if not (0 <= tx < w_tiles and 0 <= ty < h_tiles): continue
            # 1) draw the light sprite (deterministic loader)
            sprite = _pick_random_deco(room_type, light_type, variation)
            canvas.alpha_composite(sprite, (tx*TILE, ty*TILE))
            # 2) schedule tint modification
            cx = tx*TILE + TILE//2
            cy = ty*TILE + TILE//2
            lights_effects.append((
                cx, cy,
                int(radius_tiles * TILE),
                INSIDE_TINT_A,
                strength,
                color
            ))

    # --- Decorations (pure sprites)
    for deco_type, raw_positions in cfg.decoration_spots.items():
        variation = decorations.get(deco_type)
        if not variation:
            continue
        positions = _normalize_spots(raw_positions)
        base_type = DECORATION_TYPE_MAP.get(deco_type, deco_type)
        for (tx, ty) in positions:
            if not (0 <= tx < w_tiles and 0 <= ty < h_tiles): continue
            deco_img = _pick_random_deco(room_type, base_type, variation)
            canvas.alpha_composite(deco_img, (tx*TILE, ty*TILE))

    # --- Outline walls
    outline_name = walls.get("outline") or walls.get("inside") or next(iter(walls.values()))
    outline_tile = _load_image_square(_wall_path(outline_name))
    _draw_outline(canvas, outline_tile, (w_tiles, h_tiles), cfg.open_edges, left_door=left_door, right_door=right_door)

    # --- Output
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)
    return out
