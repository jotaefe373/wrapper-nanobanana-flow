"""
auth.py — Manejo de autenticacion Google para Flow.

Cada cuenta tiene su propio perfil persistente de Chrome (user_data_dir),
ver core/accounts.py.

Visible: Chrome real (channel="chrome") — para login y debug.
Headless: Chromium de Playwright + stealth — para automatizacion.
"""

from playwright.async_api import BrowserContext, Playwright, async_playwright

from core.accounts import credentials_path, has_credentials, has_profile, profile_dir
from core.config import settings
from core.logger import get_logger
from core.stealth import apply_stealth

log = get_logger("auth")

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]

CONTEXT_PARAMS = {
    "viewport": {"width": 1280, "height": 720},
    "locale": "es-CL",
    "timezone_id": "America/Santiago",
    "color_scheme": "light",
}


async def _launch_persistent(p: Playwright, account: str, headless: bool = False) -> BrowserContext:
    """Lanza browser con el perfil persistente de la cuenta."""
    profile = profile_dir(account)
    profile.mkdir(parents=True, exist_ok=True)

    params = {"user_data_dir": str(profile), "headless": headless, "args": BROWSER_ARGS, **CONTEXT_PARAMS}
    if not headless:
        params["channel"] = "chrome"

    context = await p.chromium.launch_persistent_context(**params)
    await apply_stealth(context)
    return context


async def login(account: str) -> None:
    """Abre Chrome con el perfil de la cuenta para iniciar sesion a mano.

    Sirve tanto para crear una cuenta nueva como para renovar una sesion vencida.
    Termina cuando el usuario cierra la ventana del browser.
    """
    async with async_playwright() as p:
        context = await _launch_persistent(p, account, headless=False)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(settings.base_url, wait_until="domcontentloaded")

        log.info("=" * 60)
        log.info("Cuenta '%s': inicia sesion con Google en el browser.", account)
        log.info("Cuando veas tus proyectos de Flow, CIERRA la ventana para guardar.")
        log.info("=" * 60)

        await page.wait_for_event("close", timeout=0)
        log.info("Sesion guardada en perfil: %s", profile_dir(account))
        try:
            await context.close()
        except Exception:
            pass


async def _launch_from_credentials(p: Playwright, account: str, headless: bool = False) -> BrowserContext:
    """Lanza browser usando las credenciales encriptadas (.enc) de la cuenta en vez del perfil."""
    from core.credentials import load_credentials

    state = load_credentials(credentials_path(account))

    launch_args = {"headless": headless, "args": BROWSER_ARGS}
    if not headless:
        launch_args["channel"] = "chrome"

    browser = await p.chromium.launch(**launch_args)
    context = await browser.new_context(storage_state=state, **CONTEXT_PARAMS)
    await apply_stealth(context)
    return context


async def launch_authenticated(p: Playwright, account: str, headless: bool | None = None) -> BrowserContext:
    """Lanza browser autenticado con la cuenta indicada.

    Prioridad: perfil persistente > credenciales encriptadas (.enc).
    Con FLOW_USE_CREDENTIALS=true se salta el perfil.
    """
    _headless = headless if headless is not None else settings.headless

    if has_profile(account) and not settings.use_credentials:
        context = await _launch_persistent(p, account, headless=_headless)
        log.info("Cuenta '%s' con perfil persistente (headless=%s)", account, _headless)
        return context

    if has_credentials(account):
        context = await _launch_from_credentials(p, account, headless=_headless)
        log.info("Cuenta '%s' con credenciales .enc (headless=%s)", account, _headless)
        return context

    raise FileNotFoundError(
        f"La cuenta '{account}' no tiene perfil ni credenciales.\n"
        "Opciones:\n"
        f"  make login ACCOUNT={account}   — crear perfil con login manual\n"
        f"  make creds ACCOUNT={account}   — exportar credenciales desde el perfil"
    )
