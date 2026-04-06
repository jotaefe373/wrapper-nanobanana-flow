"""
replayer.py — Ejecuta macros grabados con parametros inyectados.

Carga un script de recordings/, inyecta image_path y prompt,
y lo ejecuta con el perfil persistente autenticado.
"""

import importlib.util
import time
from pathlib import Path

from playwright.async_api import async_playwright

from core.config import settings
from core.logger import get_logger
from flow.auth import launch_authenticated
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


async def replay(
    macro_name: str,
    image_path: Path | None = None,
    prompt: str | None = None,
    output_path: Path | None = None,
    headless: bool | None = None,
) -> Path | None:
    """Ejecuta un macro grabado con parametros inyectados."""
    _headless = headless if headless is not None else settings.headless

    log.info("Cargando macro: %s", macro_name)
    module = _load_macro(macro_name)

    if not hasattr(module, "recorded_flow"):
        raise AttributeError(
            f"El macro '{macro_name}' no tiene funcion 'recorded_flow'. "
            "Puede estar corrupto — regrabalo con --record."
        )

    log.info("Ejecutando macro '%s' (headless=%s)", macro_name, _headless)
    if image_path:
        log.info("  Imagen: %s", image_path)
    if prompt:
        log.info("  Prompt: %s", prompt[:80])

    t_start = time.perf_counter()

    async with async_playwright() as p:
        context = await launch_authenticated(p, headless=_headless)
        page = context.pages[0] if context.pages else await context.new_page()

        t_browser = time.perf_counter()
        log.info("Browser listo (%.1fs)", t_browser - t_start)

        # Ejecutar el flujo grabado
        img_str = str(image_path.resolve()) if image_path else ""
        prompt_str = prompt or ""

        await module.recorded_flow(page, img_str, prompt_str)

        t_flow = time.perf_counter()
        log.info("Flujo completado (%.1fs)", t_flow - t_browser)

        # Intentar descargar resultado si se especifica output
        result_path = None
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(output_path))
            result_path = output_path
            log.info("Screenshot guardado: %s", result_path)

        await context.close()

    t_total = time.perf_counter() - t_start
    minutes, seconds = divmod(t_total, 60)
    log.info("Replay completado — tiempo total: %dm %.1fs", minutes, seconds)
    return result_path


async def replay_latest(
    image_path: Path | None = None,
    prompt: str | None = None,
    output_path: Path | None = None,
    headless: bool | None = None,
) -> Path | None:
    """Ejecuta el macro mas reciente."""
    recordings = list_recordings()
    if not recordings:
        raise FileNotFoundError("No hay macros grabados. Usa --record primero.")

    latest = recordings[-1]["name"]
    log.info("Usando macro mas reciente: %s", latest)
    return await replay(latest, image_path, prompt, output_path, headless)
