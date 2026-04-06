"""Configuracion centralizada — lee .env con prefijo FLOW_."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Browser
    headless: bool = True
    delay_ms: int = 1500

    # Paths
    output_dir: str = "output"
    session_dir: str = "session"

    # Flow
    base_url: str = "https://labs.google/fx/es/tools/flow"

    # Credentials
    credentials_key: str | None = None
    credentials_file: str | None = None

    # Timeouts (ms)
    navigation_timeout: int = 60_000
    generation_timeout: int = 120_000

    model_config = {"env_prefix": "FLOW_", "env_file": ".env"}

    @property
    def profile_dir(self) -> Path:
        return Path(self.session_dir) / "chrome-profile"

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)


settings = Settings()
