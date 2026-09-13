"""
accounts.py — Multiples cuentas de Google para repartir los creditos de Flow.

Cada cuenta vive en session/accounts/<nombre>/ con su propio perfil de Chrome
(chrome-profile/) y, opcionalmente, sus credenciales encriptadas (credentials.enc).

La rotacion recuerda la ultima cuenta que genero con exito y parte cada
ejecucion por la siguiente, asi el consumo queda parejo entre cuentas.
"""

import json
import shutil
from pathlib import Path

from core.config import settings
from core.logger import get_logger

log = get_logger("accounts")

DEFAULT_ACCOUNT = "principal"
ROTATION_FILE = "_rotation.json"
META_FILE = "account.json"


def accounts_dir() -> Path:
    return Path(settings.session_dir) / "accounts"


def profile_dir(account: str) -> Path:
    return accounts_dir() / account / "chrome-profile"


def credentials_path(account: str) -> Path:
    return accounts_dir() / account / "credentials.enc"


def load_meta(account: str) -> dict:
    path = accounts_dir() / account / META_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(account: str, **fields) -> None:
    path = accounts_dir() / account / META_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**load_meta(account), **fields}, indent=2), encoding="utf-8")


def flow_url(account: str) -> str:
    """URL de Flow de la cuenta: con varias cuentas en un mismo navegador cada una vive en /u/<n>/."""
    return load_meta(account).get("flow_url") or settings.base_url


def has_profile(account: str) -> bool:
    return (profile_dir(account) / "Default" / "Cookies").exists()


def has_credentials(account: str) -> bool:
    return settings.credentials_key is not None and credentials_path(account).exists()


def _migrate_legacy() -> None:
    """Mueve el perfil de cuenta unica (session/chrome-profile) a accounts/principal."""
    root = Path(settings.session_dir)
    legacy_profile = root / "chrome-profile"
    legacy_creds = root / "credentials.enc"
    if not legacy_profile.exists() and not legacy_creds.exists():
        return

    target = accounts_dir() / DEFAULT_ACCOUNT
    if target.exists():
        log.warning("Hay un perfil antiguo en %s pero la cuenta '%s' ya existe — no se migra", root, DEFAULT_ACCOUNT)
        return

    target.mkdir(parents=True)
    if legacy_profile.exists():
        shutil.move(str(legacy_profile), str(target / "chrome-profile"))
    if legacy_creds.exists():
        shutil.move(str(legacy_creds), str(target / "credentials.enc"))
    log.info("Perfil anterior migrado a la cuenta '%s'", DEFAULT_ACCOUNT)


def list_accounts() -> list[str]:
    """Cuentas utilizables (con perfil o credenciales), en orden alfabetico."""
    _migrate_legacy()
    root = accounts_dir()
    if not root.exists():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (has_profile(d.name) or has_credentials(d.name))
    )


def resolve_account(account: str | None) -> str:
    """Cuenta para operaciones de una sola cuenta (login, grabar, exportar)."""
    if account:
        return account
    accounts = list_accounts()
    if not accounts:
        return DEFAULT_ACCOUNT
    if len(accounts) == 1:
        return accounts[0]
    raise ValueError(f"Hay varias cuentas {accounts} — elige una con ACCOUNT=<nombre> (o --account).")


def _last_used() -> str | None:
    path = accounts_dir() / ROTATION_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("last")
    except (json.JSONDecodeError, OSError):
        return None


def rotation_order(forced: str | None = None) -> list[str]:
    """Orden en que se prueban las cuentas: parte por la siguiente a la ultima usada.

    Si se fuerza una cuenta, solo se usa esa (sin saltar a otras).
    """
    accounts = list_accounts()
    if not accounts:
        raise FileNotFoundError("No hay cuentas. Crea una con: make login ACCOUNT=<nombre>")

    if forced:
        if forced not in accounts:
            raise ValueError(f"La cuenta '{forced}' no existe. Disponibles: {accounts}")
        return [forced]

    last = _last_used()
    start = (accounts.index(last) + 1) % len(accounts) if last in accounts else 0
    return accounts[start:] + accounts[:start]


def mark_used(account: str) -> None:
    root = accounts_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / ROTATION_FILE).write_text(json.dumps({"last": account}), encoding="utf-8")
