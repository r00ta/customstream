from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment."""

    app_name: str = "Simplestream Manager"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    storage_root: Path = Path("data/simplestreams")
    frontend_root: Path = Path("frontend")
    allow_origins: list[AnyHttpUrl | str] = ["*"]
    upstream_request_timeout: int = 900
    user_agent: str = "Simplestream-Manager/1.0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @property
    def storage_path(self) -> Path:
        return self.storage_root if self.storage_root.is_absolute() else Path.cwd() / self.storage_root

    @property
    def frontend_path(self) -> Path:
        return self.frontend_root if self.frontend_root.is_absolute() else Path.cwd() / self.frontend_root


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return application settings instance."""

    settings = Settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    (settings.storage_path / "streams" / "v1").mkdir(parents=True, exist_ok=True)
    settings.frontend_path.mkdir(parents=True, exist_ok=True)
    return settings
