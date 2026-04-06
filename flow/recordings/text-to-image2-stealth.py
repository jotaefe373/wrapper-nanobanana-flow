"""
Macro grabado para Google Labs Flow.
Generado: 2026-04-06T06:22:57.507463
Nombre: text-to-image2-stealth

Variante stealth de text-to-image2:
  - human_click con curva Bezier en vez de .click()
  - human_delay entre acciones (gaussiana + pausa aleatoria)
  - Tipeo caracter a caracter con cadencia variable

Ejecutar via replay:
    make replay MACRO=text-to-image2-stealth PROMPT="mi prompt"
    make replay MACRO=text-to-image2-stealth PROMPT_FILE=prompts/producto.json
"""

import base64
import json
from datetime import datetime
from pathlib import Path

from core.stealth import human_click, human_delay

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
    """Flujo grabado — text-to-image con Nano Banana 2 (stealth)."""
    prompt_text = _load_prompt(prompt)

    await page.goto("https://labs.google/fx/es/tools/flow")
    await human_delay(2000)

    await human_click(page, page.get_by_role("button", name="add_2 Nuevo proyecto"))
    await human_delay(1500)

    # 1. Escribir prompt
    await human_click(page, page.get_by_role("paragraph").filter(has_text="¿Qué quieres crear?"))
    await human_delay(800)
    await page.keyboard.insert_text(prompt_text)
    await human_delay(1000)

    # Cerrar modal de aviso/términos si aparece (5s max, si no sigue)
    try:
        acepto_btn = page.get_by_role("button", name="Acepto")
        await acepto_btn.wait_for(timeout=5_000)
        await human_delay(500)
        await human_click(page, acepto_btn)
        await human_delay(1000)
    except Exception:
        pass

    # 2. Seleccionar modelo y aspect ratio (opcionales, no bloqueantes)
    try:
        model_btn = page.get_by_role("button", name="🍌 Nano Banana 2 crop_16_9 x2")
        await model_btn.wait_for(timeout=3_000)
        await human_click(page, model_btn)
        await human_delay(800)
    except Exception:
        pass

    try:
        tab_x1 = page.get_by_role("tab", name="x1")
        await tab_x1.wait_for(timeout=3_000)
        await human_click(page, tab_x1)
        await human_delay(800)
    except Exception:
        pass

    # 3. Crear
    await human_click(page, page.get_by_role("button", name="arrow_forward Crear"))

    # 4. Esperar resultado y click en la imagen generada
    img_link = page.get_by_role("link", name="Imagen generada")
    await img_link.wait_for(timeout=120_000)
    await human_delay(3000)
    await human_click(page, img_link)

    # 5. Descargar — intentar via boton nativo, fallback a canvas
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = OUTPUT_DIR / f"flow_{ts}_1.png"

    try:
        download_btn = page.get_by_role("button", name="download Descargar")
        await download_btn.wait_for(timeout=30_000)
        await human_delay(2000)
        await human_click(page, download_btn)
        await human_delay(1000)
        async with page.expect_download(timeout=10_000) as download_info:
            await human_click(page, page.get_by_role("menuitem", name="1K Tamaño original"))
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
