"""
auth.py — Manejo de autenticacion Google para Flow.

Usa un perfil persistente de Chrome (user_data_dir).

Visible: Chrome real (channel="chrome") — para login y debug.
Headless: Chromium de Playwright + stealth — para automatizacion.
"""

import asyncio
from pathlib import Path

from playwright.async_api import BrowserContext, Playwright, async_playwright

from core.config import settings
from core.logger import get_logger
from core.stealth import apply_stealth

log = get_logger("auth")

PROFILE_DIR = Path(settings.session_dir) / "chrome-profile"


async def _launch_persistent(p: Playwright, headless: bool = False) -> BrowserContext:
    """Lanza browser con perfil persistente."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    params = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        "viewport": {"width": 1280, "height": 720},
        "locale": "es-CL",
        "timezone_id": "America/Santiago",
        "color_scheme": "light",
    }

    if not headless:
        params["channel"] = "chrome"

    context = await p.chromium.launch_persistent_context(**params)
    await apply_stealth(context)
    return context


async def ensure_session() -> None:
    """Garantiza que exista un perfil con sesion. Si no, abre Chrome para login."""
    if (PROFILE_DIR / "Default" / "Cookies").exists():
        log.info("Perfil existente encontrado en %s", PROFILE_DIR)
        return

    log.info("No hay perfil guardado — abriendo Chrome para login manual...")

    async with async_playwright() as p:
        context = await _launch_persistent(p, headless=False)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(settings.base_url, wait_until="domcontentloaded")

        log.info("=" * 60)
        log.info("Inicia sesion con tu cuenta de Google en el browser.")
        log.info("Una vez dentro de Flow, presiona ENTER aqui para continuar...")
        log.info("=" * 60)

        await asyncio.get_event_loop().run_in_executor(None, input)

        log.info("Sesion guardada en perfil: %s", PROFILE_DIR)
        await context.close()


async def _launch_from_credentials(p: Playwright, headless: bool = False) -> BrowserContext:
    """Lanza browser usando credenciales encriptadas (.enc) en vez de perfil."""
    from core.credentials import load_credentials

    state = load_credentials()

    params = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        "viewport": {"width": 1280, "height": 720},
        "locale": "es-CL",
        "timezone_id": "America/Santiago",
        "color_scheme": "light",
    }

    if not headless:
        params["channel"] = "chrome"

    launch_args = {"headless": headless, "args": params["args"]}
    if not headless:
        launch_args["channel"] = "chrome"

    browser = await p.chromium.launch(**launch_args)
    context = await browser.new_context(
        storage_state=state,
        viewport=params["viewport"],
        locale=params["locale"],
        timezone_id=params["timezone_id"],
        color_scheme=params["color_scheme"],
    )
    await apply_stealth(context)
    return context


def _has_profile() -> bool:
    return (PROFILE_DIR / "Default" / "Cookies").exists()


def _has_credentials() -> bool:
    from core.credentials import _get_creds_path
    return settings.credentials_key is not None and _get_creds_path().exists()


async def launch_authenticated(p: Playwright, headless: bool | None = None) -> BrowserContext:
    """Lanza browser autenticado.

    Prioridad: perfil persistente > credenciales encriptadas (.enc).
    """
    _headless = headless if headless is not None else settings.headless

    if _has_profile():
        context = await _launch_persistent(p, headless=_headless)
        log.info("Chrome lanzado con perfil persistente (headless=%s)", _headless)
        return context

    if _has_credentials():
        context = await _launch_from_credentials(p, headless=_headless)
        log.info("Browser lanzado con credenciales .enc (headless=%s)", _headless)
        return context

    raise FileNotFoundError(
        "No hay perfil ni credenciales.\n"
        "Opciones:\n"
        "  make login          — crear perfil con login manual\n"
        "  make export-creds   — exportar credenciales desde perfil existente"
    )
