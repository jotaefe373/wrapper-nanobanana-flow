"""
actions.py — Acciones DOM sobre la interfaz de Google Flow.

Cada funcion encapsula una interaccion atomica con la UI:
subir imagen, escribir prompt, esperar generacion, descargar resultado.

NOTA: Los selectores CSS/XPath pueden cambiar si Google actualiza la UI.
      Si algo falla, revisar los selectores con el inspector del browser.
"""

import asyncio
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from core.config import settings
from core.logger import get_logger
from core.stealth import human_click, human_delay

log = get_logger("actions")

# ──────────────────────────────────────────────────────────────────
# Selectores — centralizar para facil mantenimiento
# ──────────────────────────────────────────────────────────────────

SELECTORS = {
    # Input de archivo (hidden file input para upload)
    "file_input": 'input[type="file"]',
    # Area de prompt / textarea
    "prompt_input": 'textarea, [contenteditable="true"], input[type="text"]',
    # Boton de generar / enviar
    "generate_btn": 'button[aria-label*="Generar"], button[aria-label*="Generate"], button[aria-label*="Enviar"], button[aria-label*="Send"], button[aria-label*="Submit"]',
    # Imagen generada en el canvas/resultado
    "result_image": 'img[class*="result"], img[class*="generated"], img[class*="output"], canvas',
    # Boton de descarga
    "download_btn": 'button[aria-label*="Descargar"], button[aria-label*="Download"], a[download]',
}


async def wait_for_page_ready(page: Page) -> None:
    """Espera a que la pagina de Flow cargue completamente."""
    log.info("Esperando que Flow cargue...")
    await page.wait_for_load_state("networkidle", timeout=settings.navigation_timeout)
    await human_delay(2000)
    log.info("Flow cargado")


async def upload_image(page: Page, image_path: Path) -> None:
    """Sube una imagen a Flow via el input de archivo."""
    if not image_path.exists():
        raise FileNotFoundError(f"Imagen no encontrada: {image_path}")

    log.info("Subiendo imagen: %s", image_path.name)

    # Buscar input[type=file] — puede estar oculto
    file_input = page.locator(SELECTORS["file_input"]).first
    await file_input.set_input_files(str(image_path.resolve()))

    await human_delay(2000)
    log.info("Imagen subida exitosamente")


async def upload_image_via_chooser(page: Page, image_path: Path) -> None:
    """Sube imagen usando file chooser (para cuando el input no es directo)."""
    if not image_path.exists():
        raise FileNotFoundError(f"Imagen no encontrada: {image_path}")

    log.info("Subiendo imagen via file chooser: %s", image_path.name)

    async with page.expect_file_chooser() as fc_info:
        # Hacer click en el area de upload
        upload_area = page.locator(
            'button:has-text("Upload"), button:has-text("Subir"), '
            '[class*="upload"], [class*="drop"]'
        ).first
        await upload_area.click()

    file_chooser = await fc_info.value
    await file_chooser.set_files(str(image_path.resolve()))

    await human_delay(2000)
    log.info("Imagen subida via file chooser")


async def enter_prompt(page: Page, prompt: str) -> None:
    """Escribe el prompt en el campo de texto."""
    log.info("Escribiendo prompt: '%s'", prompt[:50] + "..." if len(prompt) > 50 else prompt)

    prompt_el = page.locator(SELECTORS["prompt_input"]).first
    await prompt_el.click()
    await human_delay(500)

    # Limpiar campo y escribir con delay humano
    await prompt_el.fill("")
    await prompt_el.type(prompt, delay=random_typing_delay())

    await human_delay(800)
    log.info("Prompt ingresado")


async def click_generate(page: Page) -> None:
    """Presiona el boton de generar."""
    log.info("Presionando boton de generar...")

    try:
        await human_click(page, SELECTORS["generate_btn"])
    except Exception:
        # Fallback: buscar cualquier boton que parezca de submit
        buttons = page.locator("button")
        count = await buttons.count()
        for i in range(count):
            btn = buttons.nth(i)
            text = (await btn.text_content() or "").lower()
            if any(kw in text for kw in ["genera", "generate", "crear", "create", "enviar", "send"]):
                await btn.click()
                log.info("Boton encontrado por texto: '%s'", text.strip())
                break
        else:
            raise RuntimeError("No se encontro boton de generar")

    log.info("Generacion iniciada")


async def wait_for_result(page: Page, timeout_ms: int | None = None) -> None:
    """Espera a que la generacion termine."""
    timeout = timeout_ms or settings.generation_timeout
    log.info("Esperando resultado (timeout: %ds)...", timeout // 1000)

    # Esperar a que desaparezca el indicador de loading/progress
    try:
        # Primero esperar que aparezca algun indicador de progreso
        await page.wait_for_selector(
            '[class*="progress"], [class*="loading"], [class*="spinner"], [role="progressbar"]',
            timeout=10_000,
            state="visible",
        )
        log.info("Generacion en progreso...")
    except PlaywrightTimeout:
        log.info("No se detecto indicador de progreso, continuando...")

    # Luego esperar que desaparezca
    try:
        await page.wait_for_selector(
            '[class*="progress"], [class*="loading"], [class*="spinner"], [role="progressbar"]',
            timeout=timeout,
            state="hidden",
        )
    except PlaywrightTimeout:
        log.warning("Timeout esperando resultado — puede que haya terminado de todas formas")

    await human_delay(2000)
    log.info("Generacion aparentemente completada")


async def download_result(page: Page, output_path: Path) -> Path:
    """Descarga la imagen generada."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Descargando resultado...")

    # Estrategia 1: boton de descarga nativo
    try:
        async with page.expect_download(timeout=10_000) as download_info:
            download_btn = page.locator(SELECTORS["download_btn"]).first
            await download_btn.click()

        download = await download_info.value
        await download.save_as(str(output_path))
        log.info("Descargado via boton: %s", output_path)
        return output_path
    except (PlaywrightTimeout, Exception) as e:
        log.info("Descarga por boton no disponible (%s), intentando screenshot...", type(e).__name__)

    # Estrategia 2: capturar imagen del resultado via screenshot
    result_el = page.locator(SELECTORS["result_image"]).first
    try:
        await result_el.wait_for(timeout=5_000)
        screenshot_path = output_path.with_suffix(".png")
        await result_el.screenshot(path=str(screenshot_path))
        log.info("Capturado via screenshot: %s", screenshot_path)
        return screenshot_path
    except PlaywrightTimeout:
        pass

    # Estrategia 3: screenshot de toda la pagina
    screenshot_path = output_path.with_suffix(".png")
    await page.screenshot(path=str(screenshot_path), full_page=False)
    log.info("Fallback: screenshot completo guardado en %s", screenshot_path)
    return screenshot_path


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def random_typing_delay() -> int:
    """Delay entre teclas en ms — simula tipeo humano."""
    import random

    return random.randint(30, 90)
