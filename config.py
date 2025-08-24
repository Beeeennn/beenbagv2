# config.py
import os
from dataclasses import dataclass
from typing import Set

# Optional: load .env files when running locally
# try:
#     from dotenv import load_dotenv
#     load_dotenv()
# except Exception:
#     pass

def _parse_id_set(val: str | None) -> Set[int]:
    if not val:
        return set()
    out: Set[int] = set()
    for part in val.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out

@dataclass(frozen=True)
class Settings:
    # Environment
    ENV: str                 # "dev" or "prod"
    IS_DEV: bool

    # Discord
    DISCORD_BOT_TOKEN: str
    DEFAULT_PREFIX: str

    # Database
    DATABASE_URL: str

    # HTTP / media
    PUBLIC_BASE_URL: str
    PORT: int

    # Misc
    ADMIN_TOKEN: str | None
    LOG_LEVEL: str
    TEST_GUILDS: Set[int]

    def require_prod(self) -> None:
        """In production, ensure critical settings exist."""
        if not self.IS_DEV:
            missing = [k for k in ("DISCORD_BOT_TOKEN", "DATABASE_URL", "PUBLIC_BASE_URL")
                       if not getattr(self, k)]
            if missing:
                raise RuntimeError(f"Missing required settings in production: {', '.join(missing)}")

def _build() -> Settings:
    env = os.getenv("ENV", "prod").lower()
    is_dev = env == "dev"

    return Settings(
        ENV=env,
        IS_DEV=is_dev,

        DISCORD_BOT_TOKEN=os.getenv("DISCORD_BOT_TOKEN", ""),
        DEFAULT_PREFIX=os.getenv("COMMAND_PREFIX", "bc!"),

        DATABASE_URL=os.getenv("DATABASE_URL", ""),

        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", "http://localhost:10000" if is_dev else ""),
        PORT=int(os.getenv("PORT", "10000" if is_dev else "8080")),

        ADMIN_TOKEN=os.getenv("ADMIN_TOKEN"),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        TEST_GUILDS=_parse_id_set(os.getenv("TEST_GUILDS")),
    )

settings = _build()
settings.require_prod()
