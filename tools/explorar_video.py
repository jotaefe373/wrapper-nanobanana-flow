"""
explorar_video.py — Mapa de la UI de video de Flow SIN gastar creditos.

Es exploracion, no el feature: abre la cuenta, recorre las pantallas donde vive el
video y deja un informe (superficie accesible, textos con "credito", menus, RPCs)
para completar docs/VIDEO.md y elegir selectores estables.

Seguridad (por diseno):
- Aborta toda request a StreamChat (la que dispara la generacion y gasta creditos)
  con context.route -> abort. Aunque algo apriete "Iniciar generacion", no sale.
- No aprieta "Iniciar generacion", "Guardar", ni items de descarga/upscale: los
  menus se abren, se leen y se cierran con Escape.
- No sube archivos: solo reporta si hay <input type=file> y que acepta.
- Redacta firmas, tokens y correos (flow.snapshot.redact) antes de escribir.

Uso:
    .venv/bin/python tools/explorar_video.py --account smithmonsterr --out /tmp/explorar-video
    [--visible] [--proyecto URL_DE_PROYECTO_CON_VIDEOS]

Salida en --out: informe.json + capturas PNG por paso (fuera del repo por defecto).
"""

import argparse
import asyncio
import json
import re
import sys
import urllib.parse as up
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import Page, async_playwright  # noqa: E402

from core.accounts import flow_url  # noqa: E402
from flow.auth import launch_authenticated  # noqa: E402
from flow.generate import NEW_PROJECT_RE, SETTINGS_RE  # noqa: E402
from flow.results import extract_media_urls, media_kind  # noqa: E402
from flow.snapshot import _surface, redact  # noqa: E402

VIDEO_MODEL_RE = re.compile(r"Modelo predeterminado de (la )?generación de v[ií]deo")
CREDIT_RE = re.compile(r"cr[eé]dito|credit", re.I)
VIDEO_WORDS_RE = re.compile(
    r"v[ií]deo|veo|omni|fotograma|frame|ingrediente|extend|escena|duraci|segundo|\b\d+ ?s\b|720p|1080p|4k|audio|gif",
    re.I)


def _rpc(url: str) -> str:
    if "StreamChat" in url:
        return "StreamChat"
    return up.parse_qs(up.urlparse(url).query).get("rpcids", ["?"])[0]


class Explorer:
    def __init__(self, page: Page, out: Path):
        self.page, self.out = page, out
        self.report: dict = {"when": datetime.now().isoformat(), "steps": {}, "rpcs": {}, "bloqueados": 0}

    # ── red ──
    async def on_response(self, resp) -> None:
        if "flow.google.com/_/" not in resp.url or resp.request.method != "POST":
            return
        try:
            body = (await resp.body()).decode("utf-8", "replace")
        except Exception:
            return
        rpc = _rpc(resp.url)
        urls = extract_media_urls(body)
        entry = self.report["rpcs"].setdefault(rpc, {"n": 0, "video_urls": 0, "image_urls": 0, "muestra": ""})
        entry["n"] += 1
        entry["video_urls"] += sum(media_kind(u) == "video" for u in urls)
        entry["image_urls"] += sum(media_kind(u) == "image" for u in urls)
        if not entry["muestra"] and (urls or VIDEO_WORDS_RE.search(body)):
            entry["muestra"] = redact(body[:3000])

    # ── pantalla ──
    async def step(self, name: str, note: str = "") -> dict:
        page = self.page
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(self.out / f"{len(self.report['steps']) + 1:02d}-{name}.png"))
        text = await page.evaluate("() => document.body.innerText") or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        data = {
            "url": redact(page.url),
            "nota": note,
            "superficie": await _surface(page),
            "menuitems": await page.get_by_role("menuitem").all_inner_texts(),
            "opciones": await page.get_by_role("option").all_inner_texts(),
            "radios": [redact(t) for t in await page.get_by_role("radio").evaluate_all(
                "els => els.map(e => (e.getAttribute('aria-label') || e.innerText || '').trim())")],
            "con_credito": [redact(ln) for ln in lines if CREDIT_RE.search(ln)][:40],
            "con_video": [redact(ln) for ln in lines if VIDEO_WORDS_RE.search(ln) and len(ln) < 160][:80],
            "inputs_file": await page.locator("input[type=file]").evaluate_all(
                "els => els.map(e => ({accept: e.accept, multiple: e.multiple}))"),
            "videos_dom": await page.locator("video").count(),
        }
        self.report["steps"][name] = data
        return data

    async def try_click(self, locator, name: str) -> bool:
        try:
            await locator.first.click(timeout=5000)
            await self.page.wait_for_timeout(1500)
            return True
        except Exception as e:
            self.report["steps"].setdefault("_fallos", {})[name] = str(e)[:120]
            return False

    async def escape(self) -> None:
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(600)


async def explorar(account: str, out: Path, visible: bool, proyecto: str | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        ctx = await launch_authenticated(p, account, headless=not visible)
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.set_viewport_size({"width": 1440, "height": 900})
            ex = Explorer(page, out)

            async def block(route):
                ex.report["bloqueados"] += 1
                await route.abort()
            await ctx.route("**/*StreamChat*", block)
            page.on("response", ex.on_response)

            await page.goto(flow_url(account), wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            if "accounts.google.com" in page.url or page.url.rstrip("/").endswith("/about"):
                ex.report["error"] = f"Sesion vencida: Flow redirigio a {page.url.split('?')[0]}"
                return ex.report
            await ex.step("home")

            # 1) Proyecto con videos (si se pasa) — ver como se muestra un video y su menu
            if proyecto:
                await page.goto(proyecto, wait_until="domcontentloaded")
                await page.wait_for_timeout(6000)
                await ex.step("proyecto-existente")
                vid = page.locator("video")
                if await vid.count():
                    await vid.first.hover()
                    await page.wait_for_timeout(800)
                    await ex.step("video-hover")
                    if await ex.try_click(vid.first, "abrir-video"):
                        await ex.step("video-abierto")
                        # Menu de descarga: solo abrir y leer los items (720p/1080p/4K/GIF)
                        if await ex.try_click(page.get_by_role("button", name=re.compile(r"Descargar", re.I)), "menu-descarga"):
                            await ex.step("menu-descarga", "items de descarga (NO se hace clic)")
                            await ex.escape()
                        await ex.escape()

            # 2) Proyecto nuevo — barra de prompt
            await page.goto(flow_url(account), wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            if not await ex.try_click(page.get_by_text(NEW_PROJECT_RE), "proyecto-nuevo"):
                return ex.report
            await page.wait_for_timeout(5000)
            await ex.step("proyecto-nuevo")

            # 3) Ajustes: defaults de video + menu de modelos (con costos)
            if await ex.try_click(page.get_by_role("button", name=SETTINGS_RE), "ajustes"):
                await ex.step("ajustes")
                if await ex.try_click(page.get_by_role("button", name=VIDEO_MODEL_RE), "modelo-video"):
                    await ex.step("modelos-video", "menu de modelos de video: nombres y costos")
                    await ex.escape()
                await ex.escape()  # sin Guardar: no cambia nada

            # 4) "+" / ingredientes: como se agrega una imagen de entrada
            for label in (r"Añadir archivo multimedia|Agregar contenido multimedia",
                          r"Añadir ingredientes|Agregar ingredientes"):
                if await ex.try_click(page.get_by_role("button", name=re.compile(label)), label[:20]):
                    await ex.step("menu-" + re.sub(r"\W+", "-", label.split("|")[0].lower()).strip("-"))
                    await ex.escape()

            # 5) Activador de ajustes de la barra (modo manual: Video / Frames / Ingredients)
            if await ex.try_click(page.get_by_role("button", name=re.compile(r"Activador de ajustes|Ver ajustes")), "activador"):
                await ex.step("activador-ajustes")
                for modo in ("Vídeo", "Video"):
                    if await ex.try_click(page.get_by_text(modo, exact=True), f"modo-{modo}"):
                        await ex.step("modo-video")
                        break
                await ex.escape()

            # 6) Creditos: menu de la cuenta
            if await ex.try_click(page.get_by_role("button", name=re.compile(r"Información de la cuenta|Cuenta de Google")), "cuenta"):
                await ex.step("cuenta", "creditos disponibles (se redacta el correo)")
                await ex.escape()

            return ex.report
        finally:
            await ctx.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", required=True)
    ap.add_argument("--out", type=Path, required=True, help="carpeta de salida (idealmente fuera del repo)")
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--proyecto", help="URL de un proyecto con videos ya generados (para ver descarga/RPC)")
    a = ap.parse_args()
    report = asyncio.run(explorar(a.account, a.out, a.visible, a.proyecto))
    (a.out / "informe.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": str(a.out), "error": report.get("error"), "pasos": list(report["steps"]),
                      "rpcs": {k: v["n"] for k, v in report["rpcs"].items()}, "bloqueados": report["bloqueados"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
