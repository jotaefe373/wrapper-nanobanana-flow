"""
chrome_import.py — Clona la sesion de Google de tu Chrome a una cuenta del programa.

Un mismo Chrome puede tener varias cuentas de Google logueadas: todas comparten
las cookies de sesion y Flow las distingue por /u/<n>/. Por eso se copian solo
las cookies de autenticacion y despues se elige la cuenta por correo.

En macOS Chrome encripta las cookies con la clave "Chrome Safe Storage" del llavero,
mientras que Playwright usa un llavero falso. Por eso se abre una copia temporal
de las cookies con el Chrome real y el llavero real, se leen ya desencriptadas,
y se inyectan en el perfil de la cuenta.
"""

import json
import shutil
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright

from core.accounts import profile_dir, save_meta
from core.config import settings
from core.logger import get_logger

log = get_logger("chrome_import")

CHROME_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"

# Cookies que sostienen la sesion de Google, minimo confirmado por ablacion (ver README).
# Estas 6 bastan para autenticar; quitar cualquiera tira la sesion. Sin margen de redundancia:
# si Google endurece requisitos o una rotacion desincroniza, hay que reimportar (make importar).
# Conjunto mas robusto (con respaldo) = estas 6 + HSID, SSID, __Secure-1PAPISID,
# __Host-1PLSID, __Host-3PLSID (11 en total).
AUTH_COOKIES = {
    "SID", "APISID", "SAPISID",
    "LSID", "__Secure-1PSIDTS", "__Secure-1PSID",
}
AUTH_DOMAINS = {".google.com", "accounts.google.com"}


def filter_auth_cookies(cookies: list[dict]) -> list[dict]:
    return [c for c in cookies if c["name"] in AUTH_COOKIES and c["domain"] in AUTH_DOMAINS]


def list_chrome_profiles() -> list[dict]:
    """Perfiles del Chrome del usuario con sus cuentas de Google, el mas usado recientemente primero."""
    local_state = CHROME_DIR / "Local State"
    if not local_state.exists():
        return []
    cache = json.loads(local_state.read_text(encoding="utf-8")).get("profile", {}).get("info_cache", {})

    profiles = []
    for folder, info in cache.items():
        prefs_path = CHROME_DIR / folder / "Preferences"
        emails = []
        if prefs_path.exists():
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
            emails = [a["email"] for a in prefs.get("account_info", []) if a.get("email")]
        profiles.append({
            "dir": folder,
            "name": info.get("name", ""),
            "emails": emails or [info.get("user_name", "")],
            "active_time": info.get("active_time", 0),
        })
    return sorted(profiles, key=lambda p: p["active_time"], reverse=True)


def find_chrome_profile(email: str) -> str:
    """Perfil de Chrome usado mas recientemente que tenga la cuenta logueada."""
    profiles = list_chrome_profiles()
    for prof in profiles:
        if email in prof["emails"]:
            return prof["dir"]
    known = sorted({e for p in profiles for e in p["emails"]})
    raise ValueError(f"Ningun perfil de Chrome tiene la cuenta '{email}'. Cuentas encontradas: {known}")


async def _read_chrome_cookies(chrome_profile: str) -> list[dict]:
    src = CHROME_DIR / chrome_profile
    if not (src / "Cookies").exists():
        raise FileNotFoundError(f"El perfil de Chrome {src} no tiene cookies")

    tmp = Path(settings.session_dir) / "_chrome_import"
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "Default").mkdir(parents=True)
    try:
        for name in ("Cookies", "Cookies-journal"):
            if (src / name).exists():
                shutil.copy2(src / name, tmp / "Default" / name)

        async with async_playwright() as p:
            # Chrome real + llavero real para poder desencriptar
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(tmp),
                channel="chrome",
                headless=True,
                ignore_default_args=["--use-mock-keychain"],
                args=["--no-first-run", "--no-default-browser-check"],
            )
            state = await context.storage_state()
            await context.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return filter_auth_cookies(state["cookies"])


async def import_from_chrome(email: str, account: str) -> str:
    """Clona la sesion de `email` a la cuenta. Retorna la URL de Flow de esa cuenta."""
    chrome_profile = find_chrome_profile(email)
    cookies = await _read_chrome_cookies(chrome_profile)
    if not cookies:
        raise RuntimeError(f"El perfil de Chrome {chrome_profile} no tiene sesion de Google")
    log.info("Perfil de Chrome %s: %d cookies de autenticacion", chrome_profile, len(cookies))

    profile = profile_dir(account)
    profile.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=True,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        previous = (await context.storage_state())["cookies"]
        await context.clear_cookies()
        await context.add_cookies(cookies)

        # Elegir la cuenta por correo; Google redirige a Flow con /u/<n>/ de esa cuenta
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(
            f"https://accounts.google.com/AccountChooser?Email={quote(email)}&continue={quote(settings.base_url)}"
        )
        account_btn = page.locator("[aria-label^='Cuenta de Google'], [aria-label^='Google Account']").first
        signed_in_as = None
        try:
            await account_btn.wait_for(timeout=20_000)
            signed_in_as = await account_btn.get_attribute("aria-label")
        except Exception:
            pass

        if not signed_in_as or email not in signed_in_as:
            landed = page.url.split("?")[0]
            await context.clear_cookies()
            if previous:
                await context.add_cookies(previous)
            await context.close()
            raise RuntimeError(
                f"Google no acepto la sesion de {email} copiada desde Chrome ({chrome_profile}); "
                f"Flow quedo en {landed}. La cuenta quedo como estaba."
            )

        flow_url = page.url.split("?")[0]
        await context.close()

    save_meta(account, email=email, flow_url=flow_url)
    log.info("Cuenta '%s' = %s (%s)", account, email, flow_url)
    return flow_url
