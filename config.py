# config.py
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    DISCORD_BOT_TOKEN: str = os.environ["DISCORD_BOT_TOKEN"]
    DATABASE_URL: str = os.environ["DATABASE_URL"]
    ADMIN_TOKEN: str | None = os.environ.get("ADMIN_TOKEN")
    PORT: int = int(os.environ.get("PORT", "8080"))
    DEFAULT_PREFIX: str = "bc!"

settings = Settings()
