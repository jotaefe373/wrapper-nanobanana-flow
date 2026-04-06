"""
credentials.py — Exporta/importa cookies de sesion encriptadas.

Permite llevar credenciales del perfil local a otro entorno (servidor, API)
sin exponer cookies en texto plano.

Usa Fernet (AES-128-CBC) de cryptography — simple y suficiente.
"""

import json
from pathlib import Path

from cryptography.fernet import Fernet
from playwright.async_api import async_playwright

from core.config import settings
from core.logger import get_logger

log = get_logger("credentials")

PROFILE_DIR = Path(settings.session_dir) / "chrome-profile"
DEFAULT_CREDS_FILE = Path(settings.session_dir) / "credentials.enc"


def generate_key() -> str:
    """Genera una clave Fernet nueva."""
    return Fernet.generate_key().decode()


def _get_key() -> bytes:
    """Obtiene la clave de FLOW_CREDENTIALS_KEY (settings o env)."""
    key = settings.credentials_key
    if not key:
        raise ValueError(
            "FLOW_CREDENTIALS_KEY no definida.\n"
            "Genera una con: make gen-key\n"
            "Luego guardala en .env: FLOW_CREDENTIALS_KEY=<tu-clave>"
        )
    return key.encode()


def _get_creds_path() -> Path:
    """Obtiene la ruta del archivo de credenciales."""
    path = settings.credentials_file
    return Path(path) if path else DEFAULT_CREDS_FILE


async def export_credentials(output_path: Path | None = None) -> Path:
    """Extrae cookies del perfil Chrome y las guarda encriptadas."""
    if not PROFILE_DIR.exists():
        raise FileNotFoundError(f"No hay perfil en {PROFILE_DIR}. Ejecuta --login primero.")

    key = _get_key()
    out = output_path or _get_creds_path()

    # Extraer solo cookies y origins de Google/Labs
    log.info("Extrayendo cookies del perfil...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        state = await context.storage_state()
        await context.close()

    # Filtrar solo cookies de Google relevantes para Flow
    allowed_domains = [".google.com", "labs.google", ".google.cl", "accounts.google.com"]
    filtered = {
        "cookies": [
            c for c in state.get("cookies", [])
            if any(d in c.get("domain", "") for d in allowed_domains)
        ],
        "origins": [
            o for o in state.get("origins", [])
            if "google" in o.get("origin", "").lower() or "labs.google" in o.get("origin", "").lower()
        ],
    }

    total = len(state.get("cookies", []))
    kept = len(filtered["cookies"])
    log.info("Filtrado: %d/%d cookies (solo Google/Labs)", kept, total)

    # Encriptar y guardar
    payload = json.dumps(filtered).encode()
    encrypted = Fernet(key).encrypt(payload)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(encrypted)

    log.info("Credenciales exportadas a %s (%d bytes)", out, len(encrypted))
    return out


def load_credentials(creds_path: Path | None = None) -> dict:
    """Carga y desencripta credenciales. Retorna storage_state dict."""
    path = creds_path or _get_creds_path()
    if not path.exists():
        raise FileNotFoundError(f"No hay credenciales en {path}. Exporta con --export-creds.")

    key = _get_key()
    encrypted = path.read_bytes()
    payload = Fernet(key).decrypt(encrypted)

    log.info("Credenciales cargadas desde %s", path)
    return json.loads(payload)
