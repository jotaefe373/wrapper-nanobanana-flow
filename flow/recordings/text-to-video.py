"""
Macro para Google Flow — text-to-video (Veo 3.1).
Reutiliza la estrategia hibrida: dispara por la UI y lee la URL del video de la red.

El agente de Flow decide video segun el prompt: escribi un prompt que pida
explicitamente un video (movimiento de camara, accion, "video de...").

    make t2vh PROMPT="a short cinematic video: ..."
    make t2vh PROMPT_FILE=prompts/clip.json
"""

import json
from pathlib import Path

from core.config import settings
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
    await page.wait_for_timeout(3000)
    return await generate.generate_video(page, _load_prompt(prompt))
