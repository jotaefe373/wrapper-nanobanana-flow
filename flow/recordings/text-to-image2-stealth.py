"""
Macro para Google Flow — text-to-image con Nano Banana 2 (variante stealth).
Igual que text-to-image2 pero con clicks tipo humano (bezier) y delays gaussianos.

    make t2ish PROMPT="mi prompt"
    make t2ish PROMPT_FILE=prompts/producto.json
"""

import json
from pathlib import Path

from core.config import settings
from core.stealth import human_delay
from flow import generate

FLOW_URL = settings.base_url  # el replayer lo reemplaza por la URL de la cuenta


def _load_prompt(prompt: str) -> str:
    if prompt.startswith("@"):
        path = Path(prompt[1:])
        content = path.read_text(encoding="utf-8").strip()
        if path.suffix == ".json":
            return json.loads(content)["prompt"]
        return content
    return prompt


async def recorded_flow(page, image_path: str, prompt: str):
    await page.goto(FLOW_URL)
    await human_delay(2500)
    return await generate.generate_and_save(page, _load_prompt(prompt), stealth=True)
