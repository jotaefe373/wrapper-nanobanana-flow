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
    base_url: str = "https://flow.google.com/"

    # Imagen
    image_quality: str = "1K"       # 1K original, 2K/4K reescalado
    strategy: str = "auto"          # auto | hybrid | classic (como se obtiene el resultado) -> FLOW_STRATEGY
    output_retention_days: int = 0  # 0 = conservar siempre; >0 = borrar imagenes mas viejas

    # Cuentas: forzar una (sin rotar) y/o usar credentials.enc aunque haya perfil
    account: str | None = None
    use_credentials: bool = False

    # Credentials
    credentials_key: str | None = None

    # Timeouts (ms)
    navigation_timeout: int = 60_000
    generation_timeout: int = 120_000

    model_config = {"env_prefix": "FLOW_", "env_file": ".env"}

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)


settings = Settings()
