"""
Macro grabado para Google Labs Flow.
Generado: 2026-04-06T06:22:57.507463
Nombre: macro_20260406_062139

Ejecutar via replay:
    make replay MACRO=macro_20260406_062139 IMAGE=foto.jpg PROMPT="mi prompt"
"""

from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("output")


async def recorded_flow(page, image_path: str, prompt: str):
    """Flujo grabado — los selectores fueron capturados del DOM real."""
    await page.goto("https://labs.google/fx/es/tools/flow")
    await page.get_by_role("button", name="add_2 Nuevo proyecto").click()
    await page.get_by_role("paragraph").filter(has_text="¿Qué quieres crear?").click()
    await page.get_by_role("button", name="🍌 Nano Banana 2 crop_16_9 x2").click()
    await page.get_by_role("tab", name="x1").click()
    await page.get_by_role("button", name="arrow_forward Crear").click()
    await page.get_by_role("link", name="Imagen generada").click()
    await page.get_by_role("button", name="download Descargar").click()
    async with page.expect_download() as download_info:
        await page.get_by_role("menuitem", name="1K Tamaño original").click()
    download = await download_info.value
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = OUTPUT_DIR / f"flow_{ts}_1.png"
    await download.save_as(str(save_path))
    print(f"Descarga 1 guardada en: {save_path}")
    
    # ---------------------
    
    
