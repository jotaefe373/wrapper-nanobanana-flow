"""
Macro para Google Flow — text-to-image con Nano Banana 2.
Interfaz nueva (flow.google.com, 2026), estrategia segun FLOW_STRATEGY.

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
    await page.goto(FLOW_URL)
    await page.wait_for_timeout(3000)
    return await generate.generate_and_save(page, _load_prompt(prompt))
