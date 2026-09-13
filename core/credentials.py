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

from core.accounts import credentials_path, profile_dir
from core.config import settings
from core.logger import get_logger

log = get_logger("credentials")


def generate_key() -> str:
    """Genera una clave Fernet nueva."""
    return Fernet.generate_key().decode()


def _get_key() -> bytes:
    """Obtiene la clave de FLOW_CREDENTIALS_KEY (settings o env)."""
    key = settings.credentials_key
    if not key:
        raise ValueError(
            "FLOW_CREDENTIALS_KEY no definida.\n"
            "Genera una con: make key\n"
            "Luego guardala en .env: FLOW_CREDENTIALS_KEY=<tu-clave>"
        )
    return key.encode()


def filter_google_state(state: dict) -> dict:
    """Deja solo cookies y origins de Google relevantes para Flow."""
    allowed_domains = [".google.com", "labs.google", ".google.cl", "accounts.google.com"]
    return {
        "cookies": [
            c for c in state.get("cookies", [])
            if any(d in c.get("domain", "") for d in allowed_domains)
        ],
        "origins": [
            o for o in state.get("origins", [])
            if "google" in o.get("origin", "").lower()
        ],
    }


async def export_credentials(account: str, output_path: Path | None = None) -> Path:
    """Extrae cookies del perfil Chrome de la cuenta y las guarda encriptadas."""
    profile = profile_dir(account)
    if not profile.exists():
        raise FileNotFoundError(f"No hay perfil en {profile}. Ejecuta: make login ACCOUNT={account}")

    key = _get_key()
    out = output_path or credentials_path(account)

    # Extraer solo cookies y origins de Google/Labs
    log.info("Extrayendo cookies del perfil...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=True,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        state = await context.storage_state()
        await context.close()

    filtered = filter_google_state(state)

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


def load_credentials(path: Path) -> dict:
    """Carga y desencripta credenciales. Retorna storage_state dict."""
    if not path.exists():
        raise FileNotFoundError(f"No hay credenciales en {path}. Exporta con --export-creds.")

    key = _get_key()
    encrypted = path.read_bytes()
    payload = Fernet(key).decrypt(encrypted)

    log.info("Credenciales cargadas desde %s", path)
    return json.loads(payload)
