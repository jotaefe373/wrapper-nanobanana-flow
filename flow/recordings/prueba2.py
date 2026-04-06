"""
Macro grabado para Google Labs Flow.
Generado: 2026-04-06T04:31:41.774833
Nombre: prueba2

Ejecutar via replay:
    make replay MACRO=prueba2 IMAGE=foto.jpg PROMPT="mi prompt"
"""

import base64
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("output")

EXTRACT_CANVAS_JS = """
(canvas) => canvas.toDataURL('image/png')
"""


async def recorded_flow(page, image_path: str, prompt: str):
    """Flujo grabado — los selectores fueron capturados del DOM real."""
    await page.goto("https://labs.google/fx/es/tools/flow")
    await page.wait_for_timeout(2000)
    await page.get_by_role("button", name="add_2 Nuevo proyecto").click()

    # Cerrar modal de aviso/términos si aparece
    try:
        acepto_btn = page.get_by_role("button", name="Acepto")
        await acepto_btn.wait_for(timeout=5_000)
        await acepto_btn.click()
        await page.wait_for_timeout(1000)
    except Exception:
        pass

    # 1. Subir imagen
    file_input = page.locator('input[type="file"]').first
    await file_input.set_input_files(image_path)
    await page.wait_for_timeout(2000)

    # 2. Click en la imagen subida
    await page.get_by_role("link", name="Imagen generada").click()

    # 3. Escribir prompt
    await page.get_by_role("paragraph").filter(has_text="¿Qué quieres cambiar?").click()
    await page.keyboard.insert_text(prompt)

    # 4. Crear
    await page.get_by_role("button", name="arrow_forward Crear").click()

    # 5. Esperar resultado
    await page.locator("canvas").first.wait_for(timeout=120_000)
    await page.wait_for_timeout(3000)

    # 6. Descargar — intentar via boton nativo de Flow, fallback a canvas
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = OUTPUT_DIR / f"flow_{ts}_1.png"

    try:
        download_btn = page.get_by_role("button", name="download Descargar")
        await download_btn.wait_for(timeout=120_000)
        await page.wait_for_timeout(4000)
        await download_btn.click()
        async with page.expect_download(timeout=10_000) as download_info:
            await page.get_by_role("menuitem", name="1K Tamaño original").click()
        download = await download_info.value
        await download.save_as(str(save_path))
        print(f"Descarga via boton: {save_path}")
    except Exception:
        # Fallback: extraer del canvas
        canvas = page.locator("canvas").first
        try:
            data_url = await canvas.evaluate(EXTRACT_CANVAS_JS)
            _, b64data = data_url.split(",", 1)
            save_path.write_bytes(base64.b64decode(b64data))
            print(f"Imagen extraida del canvas: {save_path}")
        except Exception:
            await canvas.screenshot(path=str(save_path))
            print(f"Imagen capturada via screenshot: {save_path}")
