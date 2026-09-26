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
    image_aspect: str = "1:1"       # 16:9 | 4:3 | 1:1 | 3:4 | 9:16 -> FLOW_IMAGE_ASPECT
    multi: bool = False             # bajar todas las imagenes que devuelva el agente -> FLOW_MULTI
    multi_settle_s: int = 30        # multi: segundos sin imagenes nuevas para dar por terminado
    strategy: str = "auto"          # auto | hybrid | classic (como se obtiene el resultado) -> FLOW_STRATEGY
    auto_snapshot: bool = True      # auto-capturar un snapshot si cambia un selector critico
    video_model: str = "Veo 3.1 - Fast"  # modelo de video -> FLOW_VIDEO_MODEL
    video_timeout: int = 480        # segundos de espera del video (tarda minutos)
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
