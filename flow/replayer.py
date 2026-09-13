"""
replayer.py — Ejecuta macros grabados con parametros inyectados.

Carga un script de recordings/, inyecta image_path y prompt,
y lo ejecuta con una cuenta autenticada. Las cuentas rotan entre ejecuciones;
si una no tiene creditos o su sesion vencio, se prueba con la siguiente.
"""

import importlib.util
import time
from pathlib import Path

from playwright.async_api import async_playwright

from core.accounts import flow_url, mark_used, rotation_order
from core.config import settings
from core.housekeeping import prune
from core.logger import get_logger
from flow.auth import launch_authenticated
from flow.credits import NoCreditsError, SessionExpiredError, diagnose
from flow.recorder import RECORDINGS_DIR, list_recordings

log = get_logger("replayer")


def _load_macro(name: str):
    """Carga dinamicamente un modulo de recording por nombre."""
    macro_path = RECORDINGS_DIR / f"{name}.py"
    if not macro_path.exists():
        available = [r["name"] for r in list_recordings()]
        raise FileNotFoundError(
            f"Macro '{name}' no encontrado en {RECORDINGS_DIR}\n"
            f"Disponibles: {available or '(ninguno — graba uno con --record)'}"
        )

    spec = importlib.util.spec_from_file_location(f"recordings.{name}", macro_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _run_with_account(
    module,
    account: str,
    image_path: Path | None,
    prompt: str | None,
    output_path: Path | None,
    headless: bool,
) -> Path | None:
    """Corre el macro con una cuenta. Lanza NoCreditsError/SessionExpiredError si la cuenta no sirve."""
    t_start = time.perf_counter()

    async with async_playwright() as p:
        context = await launch_authenticated(p, account, headless=headless)
        try:
            page = context.pages[0] if context.pages else await context.new_page()

            t_browser = time.perf_counter()
            log.info("Browser listo (%.1fs)", t_browser - t_start)

            # Ejecutar el flujo grabado
            img_str = str(image_path.resolve()) if image_path else ""
            prompt_str = prompt or ""

            # Los macros navegan a FLOW_URL: cada cuenta puede estar en /u/<n>/
            module.FLOW_URL = flow_url(account)

            try:
                saved = await module.recorded_flow(page, img_str, prompt_str)
            except (NoCreditsError, SessionExpiredError):
                raise
            except Exception as e:
                cause = await diagnose(page)
                if cause:
                    raise cause from e
                raise

            log.info("Flujo completado (%.1fs)", time.perf_counter() - t_browser)

            # El macro guarda la imagen y devuelve su ruta; si no, capturamos la pagina
            if saved:
                return Path(saved)
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(output_path))
                log.info("Screenshot guardado: %s", output_path)
                return output_path
            return None
        finally:
            await context.close()


async def replay(
    macro_name: str,
    image_path: Path | None = None,
    prompt: str | None = None,
    output_path: Path | None = None,
    headless: bool | None = None,
    account: str | None = None,
) -> Path | None:
    """Ejecuta un macro grabado con parametros inyectados, rotando cuentas."""
    _headless = headless if headless is not None else settings.headless

    prune()
    log.info("Cargando macro: %s", macro_name)
    module = _load_macro(macro_name)

    if not hasattr(module, "recorded_flow"):
        raise AttributeError(
            f"El macro '{macro_name}' no tiene funcion 'recorded_flow'. "
            "Puede estar corrupto — regrabalo con --record."
        )

    order = rotation_order(account or settings.account)

    log.info("Ejecutando macro '%s' (headless=%s)", macro_name, _headless)
    if image_path:
        log.info("  Imagen: %s", image_path)
    if prompt:
        log.info("  Prompt: %s", prompt[:80])
    log.info("  Cuentas: %s", " -> ".join(order))

    t_start = time.perf_counter()
    failures: dict[str, Exception] = {}

    for i, name in enumerate(order):
        log.info("Usando cuenta '%s'", name)
        try:
            result_path = await _run_with_account(module, name, image_path, prompt, output_path, _headless)
        except (NoCreditsError, SessionExpiredError) as e:
            failures[name] = e
            log.warning("Cuenta '%s' no disponible: %s", name, e)
            if i + 1 < len(order):
                log.info("Saltando a la cuenta '%s'...", order[i + 1])
            continue

        mark_used(name)
        minutes, seconds = divmod(time.perf_counter() - t_start, 60)
        log.info("Replay completado con cuenta '%s' — tiempo total: %dm %.1fs", name, minutes, seconds)
        return result_path

    detail = "\n".join(f"  {name}: {e}" for name, e in failures.items())
    hints = "\n".join(
        f"  make login ACCOUNT={name}" for name, e in failures.items() if isinstance(e, SessionExpiredError)
    )
    raise RuntimeError(
        f"Ninguna cuenta pudo generar:\n{detail}" + (f"\nRenueva las sesiones vencidas con:\n{hints}" if hints else "")
    )


async def replay_latest(
    image_path: Path | None = None,
    prompt: str | None = None,
    output_path: Path | None = None,
    headless: bool | None = None,
    account: str | None = None,
) -> Path | None:
    """Ejecuta el macro mas reciente."""
    recordings = list_recordings()
    if not recordings:
        raise FileNotFoundError("No hay macros grabados. Usa --record primero.")

    latest = recordings[-1]["name"]
    log.info("Usando macro mas reciente: %s", latest)
    return await replay(latest, image_path, prompt, output_path, headless, account)
