import re
import shlex

_ITEM_ALIASES = {
    "exp": "exp bottle",
    "experience": "exp bottle",
    "pack": "mystery mob pack",
    "mob pack": "mystery mob pack",
    "mystery animal": "mystery mob pack",
    "boss ticket": "boss mob ticket",
    "ticket": "boss mob ticket",
    "mob ticket": "boss mob ticket",
    "boss mob": "boss mob ticket",
}

_NUM_RE = re.compile(r"^x?(\d+)$")
_NUM_SUFFIX_RE = re.compile(r"^(.+?)\s+x?(\d+)$")

def _normalize_item(name: str) -> str:
    n = name.strip().lower()
    return _ITEM_ALIASES.get(n, n)

def parse_item_and_qty(arg_str: str) -> tuple[str, int]:
    """Parse an item name and quantity from a string."""
    s = arg_str.strip()
    if not s:
        raise ValueError("no args")

    m = _NUM_SUFFIX_RE.match(s)
    if m:
        name = _normalize_item(m.group(1))
        qty = int(m.group(2))
        return name, qty

    parts = shlex.split(s)
    if not parts:
        raise ValueError("no args")

    m_first = _NUM_RE.match(parts[0].lower())
    if m_first and len(parts) > 1:
        qty = int(m_first.group(1))
        name = _normalize_item(" ".join(parts[1:]))
        return name, qty

    m_last = _NUM_RE.match(parts[-1].lower())
    if m_last and len(parts) > 1:
        qty = int(m_last.group(1))
        name = _normalize_item(" ".join(parts[:-1]))
        return name, qty

    name = _normalize_item(" ".join(parts))
    return name, 1

def _norm_item_from_args(args: tuple[str, ...]) -> str:
    # join non-quantity tokens; works for "buy exp bottle 5" and "buy 5 exp bottle"
    tokens = [a for a in args if not a.isdigit()]
    return " ".join(tokens).strip().lower()