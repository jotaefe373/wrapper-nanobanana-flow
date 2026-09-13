"""
Macro para Google Flow — text-to-image con Nano Banana 2.
Reescrito para la interfaz nueva (flow.google.com, 2026).

Ejecutar via replay:
    make t2ih PROMPT="mi prompt"
    make t2ih PROMPT_FILE=prompts/producto.json
"""

import json
from pathlib import Path

from core.config import settings
from flow import generate

FLOW_URL = settings.base_url  # el replayer lo reemplaza por la URL de la cuenta


def _load_prompt(prompt: str) -> str:
    """Si prompt empieza con @ lo lee como archivo (.txt o .json), si no lo usa tal cual."""
    if prompt.startswith("@"):
        path = Path(prompt[1:])
        content = path.read_text(encoding="utf-8").strip()
        if path.suffix == ".json":
            return json.loads(content)["prompt"]
        return content
    return prompt


async def recorded_flow(page, image_path: str, prompt: str):
    """text-to-image con Nano Banana 2 en la interfaz nueva de Flow."""
    prompt_text = _load_prompt(prompt)

    await page.goto(FLOW_URL)
    await page.wait_for_timeout(3000)

    await generate.new_project(page)
    await generate.set_image_defaults(page, aspect="1:1", count="x1")
    await generate.enter_prompt(page, prompt_text)

    images = await generate.start_and_wait(page, timeout_s=180)
    return await generate.save_generated(page, images)
