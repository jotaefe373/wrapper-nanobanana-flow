"""
Macro grabado para Google Labs Flow.
Generado: 2026-04-06T06:22:57.507463
Nombre: text-to-image2

Ejecutar via replay:
    make replay MACRO=text-to-image2 PROMPT="mi prompt"
    make replay MACRO=text-to-image2 PROMPT_FILE=prompts/producto.json
"""

import base64
import json
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("output")

EXTRACT_CANVAS_JS = """
(canvas) => canvas.toDataURL('image/png')
"""


def _load_prompt(prompt: str) -> str:
    """Si prompt empieza con @ lo lee como archivo (.txt o .json), si no lo usa tal cual."""
    if prompt.startswith("@"):
        path = Path(prompt[1:])
        content = path.read_text(encoding="utf-8").strip()
        if path.suffix == ".json":
            data = json.loads(content)
            return data["prompt"]
        return content
    return prompt


async def recorded_flow(page, image_path: str, prompt: str):
    """Flujo grabado — text-to-image con Nano Banana 2."""
    prompt_text = _load_prompt(prompt)

    await page.goto("https://labs.google/fx/es/tools/flow")
    await page.wait_for_timeout(2000)
    await page.get_by_role("button", name="add_2 Nuevo proyecto").click()

    # 1. Escribir prompt
    await page.get_by_role("paragraph").filter(has_text="¿Qué quieres crear?").click()
    await page.keyboard.insert_text(prompt_text)

    # Cerrar modal de aviso/términos si aparece (5s max, si no sigue)
    try:
        acepto_btn = page.get_by_role("button", name="Acepto")
        await acepto_btn.wait_for(timeout=5_000)
        await acepto_btn.click()
        await page.wait_for_timeout(1000)
    except Exception:
        pass

    # 2. Seleccionar modelo y aspect ratio (opcionales, no bloqueantes)
    try:
        model_btn = page.get_by_role("button", name="🍌 Nano Banana 2 crop_16_9 x2")
        await model_btn.wait_for(timeout=3_000)
        await model_btn.click()
    except Exception:
        pass

    try:
        tab_x1 = page.get_by_role("tab", name="x1")
        await tab_x1.wait_for(timeout=3_000)
        await tab_x1.click()
    except Exception:
        pass

    # 3. Crear
    await page.get_by_role("button", name="arrow_forward Crear").click()

    # 4. Esperar resultado y click en la imagen generada
    img_link = page.get_by_role("link", name="Imagen generada")
    await img_link.wait_for(timeout=120_000)
    await page.wait_for_timeout(3000)
    await img_link.click()

    # 5. Descargar — intentar via boton nativo, fallback a canvas
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = OUTPUT_DIR / f"flow_{ts}_1.png"

    try:
        download_btn = page.get_by_role("button", name="download Descargar")
        await download_btn.wait_for(timeout=30_000)
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
