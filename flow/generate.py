"""
generate.py — Flujo de generacion en Flow, con dos estrategias.

- hybrid: dispara la generacion por la UI (paso blindado por anti-abuso) y lee la
  URL del resultado directo de la respuesta de red de la app, descargando por
  request autenticada. Menos dependencia del DOM -> mas robusto.
- classic: la via anterior (editor -> menu Descargar -> 1K/2K/4K). Respaldo.
- auto (default): intenta hybrid; si no capta la URL, cae a classic sin re-disparar.

El paso de *generar* es identico para ambas; solo cambia como se obtiene el archivo.
"""

from datetime import datetime
from pathlib import Path

from playwright.async_api import Page, Response

from core.config import settings
from core.logger import get_logger
from flow.credits import NoCreditsError, NO_CREDITS_RE
from flow.results import extract_media_urls, media_kind

log = get_logger("generate")

OUTPUT_DIR = Path("output")
DATA_ENDPOINT = "flow.google.com/_/AiSandboxAngularFrontend/data/"

_PICK_IMAGES_JS = """() => [...document.querySelectorAll('img')]
    .map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight, rw: i.width, rh: i.height}))
    .filter(o => o.src && !o.src.includes('/ogw/') && o.rw > 150 && o.rh > 150
                 && (o.src.includes('flow-content') || o.src.includes('googleusercontent') || o.src.startsWith('blob:')))"""


# ── Pasos de UI (compartidos) ─────────────────────────────────────

async def _click(page: Page, target, stealth: bool) -> None:
    if stealth:
        from core.stealth import human_click
        await human_click(page, target)
    else:
        await target.click()


async def _pause(page: Page, ms: int, stealth: bool) -> None:
    if stealth:
        from core.stealth import human_delay
        await human_delay(ms)
    else:
        await page.wait_for_timeout(ms)


async def new_project(page: Page, stealth: bool = False) -> None:
    await _click(page, page.get_by_text("Proyecto nuevo").first, stealth)
    await _pause(page, 6000, stealth)


async def set_image_defaults(page: Page, aspect: str = "1:1", count: str = "x1", stealth: bool = False) -> None:
    """Fija en Configuracion: sin confirmacion, aspecto y cantidad. No bloqueante."""
    try:
        await _click(page, page.get_by_role("button", name="Configuración", exact=True), stealth)
        await _pause(page, 2000, stealth)
        for name in (aspect, count):
            try:
                await page.get_by_role("radio", name=name, exact=True).first.click(timeout=5000)
            except Exception:
                log.info("Opcion '%s' no encontrada en Configuracion (se ignora)", name)
        await _click(page, page.get_by_role("button", name="Guardar"), stealth)
        await _pause(page, 2500, stealth)
    except Exception as e:
        log.warning("No se pudo abrir Configuracion (%s) — se usa lo que este por defecto", str(e)[:60])


async def enter_prompt(page: Page, prompt: str, stealth: bool = False) -> None:
    editor = page.locator("[contenteditable=true]").first
    await _click(page, editor, stealth)
    await page.keyboard.type(prompt)
    await _pause(page, 1000, stealth)


async def click_generate(page: Page, stealth: bool = False) -> None:
    await _click(page, page.get_by_role("button", name="Iniciar generación"), stealth)
    log.info("Generando...")


# ── Estrategia hybrid: leer el resultado de la red ────────────────

class ResultCapture:
    """Escucha las respuestas RPC de Flow y junta las URLs de media que aparecen."""

    def __init__(self, page: Page):
        self.media: list[str] = []
        self._baseline = 0
        page.on("response", self._on_response)

    async def _on_response(self, resp: Response) -> None:
        if DATA_ENDPOINT not in resp.url or resp.request.method != "POST":
            return
        try:
            body = (await resp.body()).decode("utf-8", "replace")
        except Exception:
            return
        for url in extract_media_urls(body):
            if url not in self.media:
                self.media.append(url)

    def mark(self) -> None:
        """Marca el punto antes de generar; wait_new solo cuenta lo posterior."""
        self._baseline = len(self.media)

    async def wait_new(self, page: Page, timeout_s: int, kind: str | None = None) -> str | None:
        """Espera una URL de media nueva (opcionalmente de un tipo: image/video).

        Lanza NoCreditsError si Flow avisa que no quedan creditos.
        """
        for _ in range(timeout_s // 2):
            await page.wait_for_timeout(2000)
            for url in self.media[self._baseline:]:
                if kind is None or media_kind(url) == kind:
                    return url
            try:
                if await page.get_by_text(NO_CREDITS_RE).count():
                    raise NoCreditsError("Flow indica que no quedan creditos")
            except NoCreditsError:
                raise
            except Exception:
                pass
        return None


async def download_url(page: Page, url: str, out_dir: Path) -> Path:
    """Descarga la URL firmada con la sesion autenticada."""
    out_dir.mkdir(parents=True, exist_ok=True)
    r = await page.context.request.get(url)
    if not r.ok:
        raise RuntimeError(f"Descarga fallo ({r.status}) para {url[:60]}")
    body = await r.body()
    ct = r.headers.get("content-type", "")
    ext = ".mp4" if media_kind(url) == "video" else (".jpeg" if "jpeg" in ct else ".png")
    save_path = out_dir / f"flow_{datetime.now():%Y%m%d_%H%M%S}_1{ext}"
    save_path.write_bytes(body)
    log.info("Resultado descargado (hibrido, %s): %s (%d bytes)", media_kind(url), save_path, len(body))
    return save_path


# ── Estrategia classic: esperar el DOM y bajar por el editor ──────

async def wait_images_dom(page: Page, timeout_s: int = 180) -> list[dict]:
    """Espera a que la imagen aparezca en el DOM. Lanza NoCreditsError si no hay creditos."""
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
        log.info("Resultado descargado (classic %s): %s", quality, save_path)
        return save_path
    except Exception as e:
        log.info("Descarga nativa fallo (%s), uso el src del DOM", str(e)[:60])
        return None


async def _download_src(page: Page, images: list[dict], out_dir: Path) -> Path:
    """Ultimo respaldo: baja la imagen por su src del DOM."""
    save_path = out_dir / f"flow_{datetime.now():%Y%m%d_%H%M%S}_1.png"
    for o in sorted(images, key=lambda x: x["w"] * x["h"], reverse=True):
        src = o["src"]
        try:
            variants = [src.split("=")[0] + "=s0", src] if "googleusercontent" in src else [src]
            for v in variants:
                r = await page.context.request.get(v)
                if r.ok:
                    body = await r.body()
                    if len(body) > 15000:
                        save_path.write_bytes(body)
                        log.info("Resultado guardado (src DOM): %s (%d bytes)", save_path, len(body))
                        return save_path
        except Exception as e:
            log.info("Fallo al bajar %s (%s)", src[:50], str(e)[:40])
    await page.locator("img").first.screenshot(path=str(save_path))
    log.info("Resultado capturado via screenshot: %s", save_path)
    return save_path


async def save_classic(page: Page, out_dir: Path, quality: str) -> Path:
    """Espera el DOM y descarga por el editor (con respaldos)."""
    images = await wait_images_dom(page)
    return await _download_native(page, out_dir, quality) or await _download_src(page, images, out_dir)


# ── Video ─────────────────────────────────────────────────────────

async def set_video_defaults(page: Page, model: str | None = None, stealth: bool = False) -> None:
    """Fija el modelo de generacion de video en Configuracion. No bloqueante."""
    model = model or settings.video_model
    try:
        await _click(page, page.get_by_role("button", name="Configuración", exact=True), stealth)
        await _pause(page, 2000, stealth)
        try:
            await page.get_by_role("button", name="Modelo predeterminado de generación de video").click(timeout=5000)
            await page.wait_for_timeout(1200)
            await page.get_by_role("menuitem", name=model).first.click(timeout=5000)
            await page.wait_for_timeout(800)
            log.info("Modelo de video: %s", model)
        except Exception:
            log.info("No pude fijar el modelo de video '%s' (se usa el actual)", model)
        await _click(page, page.get_by_role("button", name="Guardar"), stealth)
        await _pause(page, 2500, stealth)
    except Exception as e:
        log.warning("No se pudo abrir Configuracion de video (%s)", str(e)[:60])


async def _agent_asked(page: Page) -> bool:
    """Heuristica: el agente respondio con una pregunta (duracion/modelo) en vez de generar."""
    try:
        txt = (await page.evaluate("() => document.body.innerText") or "")[-1000:].lower()
    except Exception:
        return False
    return "?" in txt and any(k in txt for k in ("prefer", "which", "opci", "second", "segundo", "model", "modelo"))


async def generate_video(
    page: Page,
    prompt: str,
    *,
    model: str | None = None,
    out_dir: Path | None = None,
    timeout_s: int | None = None,
    stealth: bool = False,
) -> Path:
    """Genera un video: setup -> generar por la UI -> leer la URL del video de la red.

    El video se obtiene siempre por la estrategia hibrida (la descarga por editor es
    especifica de imagen). El agente de Flow decide video segun el prompt, asi que
    conviene un prompt que pida explicitamente un video.
    """
    out_dir = out_dir or OUTPUT_DIR
    timeout_s = timeout_s or settings.video_timeout

    capture = ResultCapture(page)
    await new_project(page, stealth)
    await set_video_defaults(page, model=model, stealth=stealth)
    await enter_prompt(page, prompt, stealth)
    await verify_ready_to_generate(page)

    capture.mark()
    await click_generate(page, stealth)

    # El agente puede negociar (duracion/modelo) antes de generar: espera corta y, si
    # respondio con una pregunta y todavia no hay video, confirma para continuar.
    url = await capture.wait_new(page, 60, kind="video")
    if not url and await _agent_asked(page):
        log.info("El agente pidio confirmacion; respondo para continuar")
        await enter_prompt(page, "Si, procede y genera el video con la duracion por defecto.", stealth)
        await click_generate(page, stealth)
    if not url:
        url = await capture.wait_new(page, timeout_s, kind="video")
    if not url:
        raise RuntimeError(f"Video: no llego la URL del resultado en {timeout_s}s (¿el prompt no era de video?)")
    return await download_url(page, url, out_dir)


# ── Orquestador ───────────────────────────────────────────────────

def resolve_strategy(requested: str | None, quality: str) -> str:
    """hybrid/classic/auto. 2K/4K solo existen por el editor -> fuerzan classic."""
    strat = (requested or settings.strategy).lower()
    if quality.upper() != "1K" and strat != "classic":
        log.info("Calidad %s solo por editor -> estrategia classic", quality)
        return "classic"
    return strat if strat in ("hybrid", "classic", "auto") else "auto"


async def verify_ready_to_generate(page: Page) -> None:
    """Chequea los selectores criticos del proyecto antes de generar (pre-credito).

    Si algun selector cambio respecto del ultimo snapshot, auto-captura uno (con
    fecha) para dejar registro del momento del cambio. Si falta alguno, aborta con
    un mensaje claro sin gastar credito.
    """
    from flow.snapshot import CRITICAL_SELECTORS, _present, capture_current, changed_keys, last_health

    current = {sel["key"]: await _present(page, sel)
               for sel in CRITICAL_SELECTORS if sel["screen"] == "project"}

    if settings.auto_snapshot:
        changed = changed_keys(current, last_health())
        if changed:
            log.warning("Cambio detectado en selectores %s — auto-snapshot", changed)
            try:
                await capture_current(page, note=f"cambio: {','.join(changed)}")
            except Exception as e:
                log.warning("Auto-snapshot fallo (%s)", str(e)[:60])

    missing = [k for k, present in current.items() if not present]
    if missing:
        raise RuntimeError(
            f"La UI de Flow cambio: faltan selectores {missing} antes de generar "
            "(no se gasto credito). Corre 'make snapshot' para ver que cambio."
        )
    log.info("Health-check UI: OK")


async def generate_and_save(
    page: Page,
    prompt: str,
    *,
    strategy: str | None = None,
    quality: str | None = None,
    out_dir: Path | None = None,
    aspect: str = "1:1",
    count: str = "x1",
    timeout_s: int = 180,
    stealth: bool = False,
) -> Path:
    """Flujo completo de imagen: setup -> generar -> guardar segun estrategia."""
    out_dir = out_dir or OUTPUT_DIR
    quality = (quality or settings.image_quality).upper()
    strat = resolve_strategy(strategy, quality)

    capture = ResultCapture(page)
    await new_project(page, stealth)
    await set_image_defaults(page, aspect=aspect, count=count, stealth=stealth)
    await enter_prompt(page, prompt, stealth)
    await verify_ready_to_generate(page)

    capture.mark()
    await click_generate(page, stealth)

    if strat in ("hybrid", "auto"):
        url = await capture.wait_new(page, timeout_s if strat == "hybrid" else 90)
        if url:
            return await download_url(page, url, out_dir)
        if strat == "hybrid":
            raise RuntimeError("Estrategia hybrid: no llego la URL del resultado por red")
        log.info("Hybrid no capto la URL; caigo a classic")

    return await save_classic(page, out_dir, quality)
