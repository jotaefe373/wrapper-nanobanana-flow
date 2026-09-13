"""
generate.py — Pasos de la interfaz nueva de Flow (flow.google.com, 2026).

Flow paso de labs.google/fx a un editor con panel de chat: el prompt va en un
editor contenteditable, el aspecto/cantidad/modelo viven en "Configuracion", y
la imagen se descarga desde el editor con calidad elegible (1K original, 2K/4K
reescalado). Estos helpers encapsulan ese flujo para que los macros queden cortos.
"""

from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from core.config import settings
from core.logger import get_logger
from flow.credits import NoCreditsError, NO_CREDITS_RE

log = get_logger("generate")

OUTPUT_DIR = Path("output")

# Imagen generada: grande, no el avatar de la cuenta (/ogw/), servida por Flow o googleusercontent
_PICK_IMAGES_JS = """() => [...document.querySelectorAll('img')]
    .map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight, rw: i.width, rh: i.height}))
    .filter(o => o.src && !o.src.includes('/ogw/') && o.rw > 150 && o.rh > 150
                 && (o.src.includes('flow-content') || o.src.includes('googleusercontent') || o.src.startsWith('blob:')))"""

_BLOB_TO_DATAURL_JS = """async (u) => {
    const r = await fetch(u); const b = await r.blob();
    return await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
}"""


async def new_project(page: Page) -> None:
    await page.get_by_text("Proyecto nuevo").first.click()
    await page.wait_for_timeout(6000)


async def set_image_defaults(page: Page, aspect: str = "1:1", count: str = "x1") -> None:
    """Fija en Configuracion: sin confirmacion, aspecto y cantidad. No bloqueante."""
    try:
        await page.get_by_role("button", name="Configuración", exact=True).click()
        await page.wait_for_timeout(2000)
        for name in ("Nunca", aspect, count):
            try:
                await page.get_by_role("radio", name=name, exact=True).first.click(timeout=5000)
            except Exception:
                log.info("Opcion '%s' no encontrada en Configuracion (se ignora)", name)
        await page.get_by_role("button", name="Guardar").click()
        await page.wait_for_timeout(2500)
    except Exception as e:
        log.warning("No se pudo abrir Configuracion (%s) — se usa lo que este por defecto", str(e)[:60])


async def enter_prompt(page: Page, prompt: str) -> None:
    editor = page.locator("[contenteditable=true]").first
    await editor.click()
    await page.keyboard.type(prompt)
    await page.wait_for_timeout(1000)


async def start_and_wait(page: Page, timeout_s: int = 180) -> list[dict]:
    """Dispara la generacion y espera la imagen. Lanza NoCreditsError si no hay creditos."""
    await page.get_by_role("button", name="Iniciar generación").click()
    log.info("Generando...")
    for _ in range(timeout_s // 4):
        await page.wait_for_timeout(4000)
        imgs = await page.evaluate(_PICK_IMAGES_JS)
        if imgs:
            return imgs
        try:
            if await page.get_by_text(NO_CREDITS_RE).count():
                raise NoCreditsError("Flow indica que no quedan creditos")
        except NoCreditsError:
            raise
        except Exception:
            pass
    raise TimeoutError(f"La imagen no aparecio en {timeout_s}s")


async def _download_native(page: Page, out_dir: Path, quality: str) -> Path | None:
    """Descarga desde el editor con el boton nativo (1K original, 2K/4K reescalado)."""
    try:
        await page.get_by_role("button", name="Abrir imagen en el editor").first.click()
        await page.wait_for_timeout(3500)
        await page.get_by_role("button", name="Descargar contenido multimedia").click()
        await page.wait_for_timeout(1200)
        async with page.expect_download(timeout=30_000) as info:
            await page.get_by_role("menuitem", name=quality).first.click()
        download = await info.value
        ext = Path(download.suggested_filename).suffix or ".png"
        save_path = out_dir / f"flow_{datetime.now():%Y%m%d_%H%M%S}_1{ext}"
        await download.save_as(str(save_path))
        log.info("Imagen descargada (%s nativo): %s", quality, save_path)
        return save_path
    except Exception as e:
        log.info("Descarga nativa fallo (%s), uso el src", str(e)[:60])
        return None


async def _download_src(page: Page, images: list[dict], out_dir: Path) -> Path:
    """Respaldo: baja la imagen mas grande por su URL, con la sesion autenticada."""
    save_path = out_dir / f"flow_{datetime.now():%Y%m%d_%H%M%S}_1.png"
    for o in sorted(images, key=lambda x: x["w"] * x["h"], reverse=True):
        src = o["src"]
        try:
            if src.startswith("blob:"):
                import base64
                data_url = await page.evaluate(_BLOB_TO_DATAURL_JS, src)
                save_path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
                log.info("Imagen guardada (blob): %s", save_path)
                return save_path
            variants = [src.split("=")[0] + "=s0", src] if "googleusercontent" in src else [src]
            for v in variants:
                r = await page.context.request.get(v)
                if r.ok:
                    body = await r.body()
                    if len(body) > 15000:
                        save_path.write_bytes(body)
                        log.info("Imagen guardada (src): %s (%d bytes)", save_path, len(body))
                        return save_path
        except Exception as e:
            log.info("Fallo al bajar %s (%s)", src[:50], str(e)[:40])
    await page.locator("img").first.screenshot(path=str(save_path))
    log.info("Imagen capturada via screenshot: %s", save_path)
    return save_path


async def save_generated(page: Page, images: list[dict], out_dir: Path | None = None, quality: str | None = None) -> Path:
    """Guarda la imagen: descarga nativa con calidad; si falla, baja por URL."""
    out_dir = out_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    quality = quality or settings.image_quality
    return await _download_native(page, out_dir, quality) or await _download_src(page, images, out_dir)
