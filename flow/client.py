"""
client.py — FlowClient: orquestador principal.

Maneja el ciclo completo: browser -> login -> upload -> prompt -> download.
Usa async context manager para cleanup seguro.
"""

from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from core.config import settings
from core.logger import get_logger
from flow.auth import launch_authenticated
from flow import actions

log = get_logger("client")


class FlowClient:
    """Cliente para interactuar con Google Labs Flow."""

    def __init__(self, account: str, headless: bool | None = None):
        self.account = account
        self.headless = headless if headless is not None else settings.headless
        self._pw = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def start(self) -> None:
        """Inicia Chrome con perfil persistente y navega a Flow."""
        self._pw = await async_playwright().start()
        self._context = await launch_authenticated(self._pw, self.account, headless=self.headless)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

        log.info("Navegando a %s", settings.base_url)
        await self._page.goto(settings.base_url, wait_until="domcontentloaded")
        await actions.wait_for_page_ready(self._page)

    async def close(self) -> None:
        """Limpia recursos."""
        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()
        log.info("Browser cerrado")

    async def generate(self, image_path: Path, prompt: str, output_path: Path | None = None) -> Path:
        """Flujo completo: sube imagen + prompt -> genera -> descarga resultado."""
        if not self._page:
            raise RuntimeError("Client no iniciado. Usa 'async with FlowClient()' o llama start()")

        page = self._page

        # 1. Subir imagen
        try:
            await actions.upload_image(page, image_path)
        except Exception:
            log.info("Upload directo fallo, intentando via file chooser...")
            await actions.upload_image_via_chooser(page, image_path)

        # 2. Escribir prompt
        await actions.enter_prompt(page, prompt)

        # 3. Generar
        await actions.click_generate(page)

        # 4. Esperar resultado
        await actions.wait_for_result(page)

        # 5. Descargar
        if output_path is None:
            output_path = settings.output_path / f"flow_result_{_timestamp()}.png"

        result = await actions.download_result(page, output_path)
        log.info("Imagen generada guardada en: %s", result)
        return result


def _timestamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S")
