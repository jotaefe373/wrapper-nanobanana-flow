"""
video.py — Video (Veo / Omni) en Flow, dentro de UN proyecto y con tope de puntos.

Flujo objetivo (docs/VIDEO.md): en un mismo proyecto se crean primero personajes,
lugares y objetos (imagenes) y despues se generan los clips citandolos con `@`
(la UI los pega como "ingredientes"). Un video = 2-3 clips de 8 s.

Cuidado con los creditos ("puntos de Google Flow"):
- Ajustes queda con "Confirmar antes de generar: Siempre". El agente de Flow,
  antes de gastar, pregunta "¿Quieres que empiece a generar 1 vídeo, que cuesta
  12 puntos?". Ese numero es el costo REAL: se parsea y, si supera el tope, se
  aprieta "Rechazar" y no se gasta nada. Nunca se aprieta "Aprobar siempre".
- Ademas hay una estimacion previa (tabla de la ayuda de Flow) que aborta antes de
  enviar el mensaje si ya se sabe que no entra en el tope.
- Una generacion disparada nunca se reintenta.

CLI (JSON a stdout, logs a stderr):
    python -m flow.video creditos --account X
    python -m flow.video imagenes --account X --prompt "..." [--proyecto URL] --max-credits N
    python -m flow.video clip --account X --prompt "@{mujer} entra a @{cafeteria}..." \
        [--proyecto URL] [--model lite] [--aspect 9:16] [--count 1] --max-credits N
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from core.config import settings
from core.logger import get_logger
from flow.credits import GenerationRejectedError, NoCreditsError
from flow.generate import SETTINGS_RE, ResultCapture, check_blockers, open_new_project
from flow.results import media_kind

log = get_logger("video")

# ── Puro (testeable sin navegador) ────────────────────────────────

VIDEO_MODELS = {
    "lite": "Veo 3.1 - Lite",
    "fast": "Veo 3.1 - Fast",
    "quality": "Veo 3.1 - Quality",
    "omni": "Omni 1.1 Flash",
}

# Puntos por clip segun la ayuda de Flow ("Manage your Google Flow credits").
# (no Ultra, Ultra). Omni: 720p a 8 s. Es solo la estimacion previa: manda el
# numero que pregunta el agente.
_COSTS = {
    "Veo 3.1 - Lite": (10, 5),
    "Veo 3.1 - Fast": (20, 10),
    "Veo 3.1 - Quality": (100, 100),
    "Omni 1.1 Flash": (12, 12),
}


class CreditCapError(RuntimeError):
    """La generacion costaria mas que el tope: no se disparo (o se rechazo la confirmacion)."""


def resolve_model(name: str | None) -> str:
    """'lite'/'fast'/... o el nombre tal cual aparece en el menu."""
    name = (name or settings.video_model).strip()
    return VIDEO_MODELS.get(name.lower(), name)


def estimate_video_cost(model: str, count: int = 1, ultra: bool = False) -> int | None:
    """Puntos estimados de `count` clips. None si el modelo no esta en la tabla."""
    costs = _COSTS.get(resolve_model(model))
    return None if costs is None else costs[1 if ultra else 0] * count


def check_cap(cost: int | None, cap: int | None, what: str = "generacion") -> None:
    """Lanza CreditCapError si el costo (conocido) supera el tope. Sin tope no limita."""
    if cap is not None and cost is not None and cost > cap:
        raise CreditCapError(f"La {what} cuesta {cost} puntos y el tope es {cap}: no se genera")


_CONFIRM_RE = re.compile(
    r"generar\s+(\d+)\s+(v[ií]deos?|im[aá]gen(?:es)?|videos?|images?)\b.*?cuesta(?:n)?\s+(\d+)\s*(puntos|cr[eé]ditos|credits|points)",
    re.IGNORECASE | re.DOTALL,
)


def parse_confirmation(text: str) -> dict | None:
    """'¿Quieres que empiece a generar 1 vídeo, que cuesta 12 puntos?' -> {n:1, kind:'video', cost:12}."""
    m = _CONFIRM_RE.search(text or "")
    if not m:
        return None
    kind = "video" if m.group(2).lower().startswith("v") else "image"
    return {"n": int(m.group(1)), "kind": kind, "cost": int(m.group(3))}


_BALANCE_RE = re.compile(r"([\d.,]+)\s+(?:puntos|cr[eé]ditos)\s+de\s+Google\s+Flow|([\d.,]+)\s+Google\s+Flow\s+(?:credits|points)", re.I)


def parse_balance(text: str) -> int | None:
    """'93 puntos de Google Flow' -> 93 (acepta separador de miles)."""
    m = _BALANCE_RE.search(text or "")
    if not m:
        return None
    return int(re.sub(r"[.,]", "", m.group(1) or m.group(2)))


_MENTION_RE = re.compile(r"@\{([^}]+)\}")


def split_mentions(prompt: str) -> list[tuple[str, str]]:
    """'@{mujer} entra a @{cafeteria}' -> [('ref','mujer'),('text',' entra a '),('ref','cafeteria')]."""
    parts, pos = [], 0
    for m in _MENTION_RE.finditer(prompt):
        if m.start() > pos:
            parts.append(("text", prompt[pos:m.start()]))
        parts.append(("ref", m.group(1).strip()))
        pos = m.end()
    if pos < len(prompt):
        parts.append(("text", prompt[pos:]))
    return parts


def _norm(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def pick_option(names: list[str], query: str, kinds: list[str] | None = None) -> int | None:
    """Indice del recurso cuyo nombre contiene todas las palabras de la consulta.

    Prefiere imagenes: los clips ya generados tambien son recursos del proyecto y
    '@coffee shop' matcheaba el video anterior ("Woman entering coffee shop sitting")
    en vez de la imagen del lugar. Un video solo se elige si no hay imagen que coincida.
    """
    words = _norm(query).split()
    kinds = kinds or [""] * len(names)
    hits = [i for i, name in enumerate(names) if all(w in _norm(name) for w in words)]
    images = [i for i in hits if _norm(kinds[i]).startswith("imagen") or _norm(kinds[i]).startswith("image")]
    return (images or hits or [None])[0]


# ── UI ────────────────────────────────────────────────────────────

# Contenedores de los grupos de Ajustes (aria-label de <flow-toggles>)
_GROUPS = {
    "image_aspect": "Relación de aspecto predeterminada de generación de imágenes",
    "image_count": "Número de resultados predeterminado de generación de imágenes",
    "video_aspect": "Relación de aspecto predeterminada de generación de vídeo",
    "video_count": "Número de salidas predeterminado de generación de vídeo",
}
VIDEO_MODEL_BTN = re.compile(r"Modelo predeterminado de (la )?generación de v[ií]deo")
OPEN_VIDEO = "Abrir vídeo en el editor"
OPEN_IMAGE = "Abrir imagen en el editor"


async def _close_overlay(page: Page) -> None:
    """Los menus de Flow (cdk-overlay) no cierran con Escape: clic en el backdrop."""
    backdrop = page.locator(".cdk-overlay-backdrop")
    if await backdrop.count():
        await backdrop.first.click(position={"x": 5, "y": 5})
        await page.wait_for_timeout(600)


async def read_balance(page: Page) -> int | None:
    """Saldo de puntos desde el menu de la cuenta (no gasta nada)."""
    try:
        await page.get_by_role("button", name="Información de la cuenta").click(timeout=8000)
        await page.wait_for_timeout(2000)
        balance = parse_balance(await page.evaluate("() => document.body.innerText"))
    except Exception as e:
        log.info("No pude leer el saldo (%s)", str(e)[:60])
        balance = None
    await _close_overlay(page)
    return balance


async def open_project(page: Page, url: str | None) -> str:
    """Abre el proyecto dado o crea uno nuevo. Devuelve su URL (para seguir en el mismo)."""
    if url:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
    else:
        await open_new_project(page)
        await page.wait_for_timeout(6000)
    if "/project/" not in page.url:
        raise RuntimeError(f"No quedo abierto un proyecto (url: {page.url.split('?')[0]})")
    return page.url.split("?")[0].split("/edit/")[0]


async def set_defaults(
    page: Page,
    *,
    video_model: str | None = None,
    video_aspect: str | None = None,
    video_count: int | None = None,
    image_aspect: str | None = None,
    image_count: int | None = None,
) -> None:
    """Fija Ajustes (acotado a cada grupo) + 'Confirmar antes de generar: Siempre' y guarda.

    Falla (sin gastar) si no puede fijar lo pedido: con video no se adivina.
    """
    await page.get_by_role("button", name=SETTINGS_RE).click()
    await page.wait_for_timeout(2000)
    # El gate de costo depende de que el agente pregunte
    await page.get_by_text("Siempre", exact=True).first.click(timeout=5000)
    wanted = {"image_aspect": image_aspect, "video_aspect": video_aspect,
              "image_count": f"x{image_count}" if image_count else None,
              "video_count": f"x{video_count}" if video_count else None}
    for key, value in wanted.items():
        if not value:
            continue
        group = page.locator(f'[aria-label="{_GROUPS[key]}"]')
        radio = group.get_by_role("radio", name=re.compile(rf"(^|\s){re.escape(value)}$"))
        await radio.first.click(timeout=5000)
        for _ in range(10):  # aria-checked se actualiza un instante despues del clic
            await page.wait_for_timeout(300)
            if await radio.first.get_attribute("aria-checked") == "true":
                break
        else:
            raise RuntimeError(f"Ajustes: no quedo marcado {key}={value}")
    if video_model:
        await page.get_by_role("button", name=VIDEO_MODEL_BTN).click(timeout=5000)
        await page.wait_for_timeout(1000)
        await page.get_by_role("menuitem", name=video_model, exact=True).first.click(timeout=5000)
        await page.wait_for_timeout(800)
        shown = await page.get_by_role("button", name=VIDEO_MODEL_BTN).inner_text()
        if video_model not in shown:
            raise RuntimeError(f"Ajustes: el modelo de video quedo en {shown!r}, no {video_model!r}")
    await page.get_by_role("button", name="Guardar").click()
    await page.wait_for_timeout(2500)
    log.info("Ajustes: modelo=%s video=%s x%s imagen=%s x%s (confirmar: Siempre)",
             video_model, video_aspect, video_count, image_aspect, image_count)


async def add_reference(page: Page, query: str) -> str:
    """Escribe '@palabra' en el editor y elige el recurso del proyecto que coincide con la consulta.

    Flow lo pega como chip (span.mention-chip) y lo adjunta como ingrediente. El buscador
    del '@' deja de filtrar con el espacio, por eso se escribe solo la primera palabra y
    se elige con pick_option (todas las palabras). Si no hay coincidencia, falla ANTES
    de enviar (no gasta): nunca se acepta "el primero de la lista".
    """
    first = query.split()[0]
    await page.keyboard.type("@" + first)
    await page.wait_for_timeout(2000)
    options = page.get_by_role("option")
    texts = await options.all_inner_texts()
    names = [t.split("\n")[0] for t in texts]
    kinds = [(t.split("\n") + [""])[1] for t in texts]  # "Imagen" / "Vídeo"
    idx = pick_option(names, query, kinds)
    if idx is None:
        raise RuntimeError(f"Referencia '@{{{query}}}': ningun recurso coincide (hay: {names})")
    await options.nth(idx).click()
    await page.wait_for_timeout(1200)
    log.info("Referencia @%s -> %s", query, names[idx])
    return names[idx]


async def type_prompt(page: Page, prompt: str) -> list[str]:
    """Escribe el prompt; cada @{consulta} se vuelve una referencia a un recurso del proyecto."""
    editor = page.locator("[contenteditable=true]").first
    await editor.click()
    refs = []
    for kind, value in split_mentions(prompt):
        if kind == "ref":
            refs.append(await add_reference(page, value))
        else:
            # Enter envia el mensaje: los saltos de linea van con Shift+Enter
            for j, line in enumerate(value.split("\n")):
                if j:
                    await page.keyboard.press("Shift+Enter")
                if line:
                    await page.keyboard.type(line)
    await page.wait_for_timeout(800)
    return refs


def _count(page: Page, name: str):
    return page.get_by_role("button", name=name, exact=True).count()


async def _latest_question(page: Page, before: int) -> dict | None:
    """Pregunta de confirmacion nueva (hay mas radios 'Aprobar' que antes)."""
    approve = page.get_by_role("radio", name="Aprobar", exact=True)
    if await approve.count() <= before:
        return None
    q = page.get_by_text(re.compile(r"cuesta\s+\d+\s+(puntos|cr[eé]ditos)", re.I))
    if not await q.count():
        return None
    text = await q.last.inner_text()
    parsed = parse_confirmation(text)
    return {**parsed, "texto": text.strip()} if parsed else {"texto": text.strip()}


async def _started(page: Page, kind: str, before: int) -> bool:
    """La generacion arranco sin preguntar: hay tarjetas con progreso (NN %) o resultados nuevos."""
    name = OPEN_VIDEO if kind == "video" else OPEN_IMAGE
    if await page.get_by_text(re.compile(r"^\d{1,3} ?%$")).count():
        return True
    return await _count(page, name) > before


async def send_and_confirm(page: Page, prompt: str, *, kind: str, expected_n: int,
                           max_credits: int | None, before: int, ask_timeout_s: int = 180) -> dict:
    """Escribe, envia y resuelve la confirmacion del agente con el tope.

    Con 'Confirmar antes de generar: Siempre' el agente pregunta el costo antes de
    gastar; si supera el tope (o quiere generar otra cosa u otra cantidad) se aprieta
    'Rechazar' y se lanza CreditCapError. Lo que cuesta 0 (imagenes Nano Banana en
    Plus) el agente lo genera sin preguntar: se acepta y queda confirmacion=None.
    """
    approvals_before = await page.get_by_role("radio", name="Aprobar", exact=True).count()
    refs = await type_prompt(page, prompt)
    await page.get_by_role("button", name="Iniciar generación").click()
    log.info("Mensaje enviado; espero la confirmacion del agente (costo)")

    question = None
    for _ in range(ask_timeout_s // 2):
        await page.wait_for_timeout(2000)
        await check_blockers(page)
        question = await _latest_question(page, approvals_before)
        if question:
            break
        if await _started(page, kind, before):
            if kind == "video":
                log.warning("El video arranco SIN confirmacion (¿'Aprobar siempre' en la sesion?)")
            else:
                log.info("La imagen arranco sin confirmacion (costo 0)")
            return {"refs": refs, "confirmacion": None}
    if not question:
        raise RuntimeError("El agente no pidio confirmacion ni empezo a generar. "
                           "No se aprobo nada; revisa el proyecto antes de seguir.")
    log.info("El agente pregunta: %s", question["texto"][:160])
    problem = None
    if "cost" not in question:
        problem = "no pude leer el costo de la confirmacion"
    elif question["kind"] != kind or question["n"] != expected_n:
        problem = f"el agente quiere generar {question['n']} {question['kind']}, se pidio {expected_n} {kind}"
    else:
        try:
            check_cap(question["cost"], max_credits)
        except CreditCapError as e:
            problem = str(e)
    if problem:
        await page.get_by_role("radio", name="Rechazar", exact=True).last.click()
        raise CreditCapError(f"Rechazado sin gastar: {problem}")
    await page.get_by_role("radio", name="Aprobar", exact=True).last.click()
    log.info("Aprobado: %d %s por %d puntos", question["n"], question["kind"], question["cost"])
    return {"refs": refs, "confirmacion": question}


async def wait_results(page: Page, *, kind: str, before: int, n: int, timeout_s: int) -> int:
    """Espera `n` resultados nuevos del tipo (botones 'Abrir ... en el editor' en el chat)."""
    name = OPEN_VIDEO if kind == "video" else OPEN_IMAGE
    t = 0
    while t < timeout_s:
        await page.wait_for_timeout(5000)
        t += 5
        now = await _count(page, name)
        if now - before >= n:
            log.info("%d %s nuevo(s) en %ds", now - before, kind, t)
            return now
        if t % 30 == 0:
            log.info("Esperando %s... %ds", kind, t)
        await check_blockers(page)
    raise TimeoutError(f"No aparecieron {n} {kind}(s) nuevos en {timeout_s}s (no se reintenta)")


async def download_result(page: Page, *, kind: str, index: int, out_dir: Path, stem: str) -> Path:
    """Abre el resultado `index` (orden del chat) en el editor y lo baja por el menu nativo.

    Video: '720p Tamaño original' (1080p es upscale gratis en Plus, 4K solo Ultra).
    Imagen: '1K' (original).
    """
    name = OPEN_VIDEO if kind == "video" else OPEN_IMAGE
    project_url = page.url
    await page.get_by_role("button", name=name, exact=True).nth(index).click()
    await page.wait_for_timeout(5000)
    await page.get_by_role("button", name="Descargar contenido multimedia").click()
    await page.wait_for_timeout(1500)
    item = re.compile(r"^720p" if kind == "video" else r"^1K")
    out_dir.mkdir(parents=True, exist_ok=True)
    async with page.expect_download(timeout=120_000) as info:
        await page.get_by_role("menuitem", name=item).first.click()
    dl = await info.value
    ext = Path(dl.suggested_filename).suffix or (".mp4" if kind == "video" else ".png")
    path = out_dir / f"{stem}{ext}"
    await dl.save_as(str(path))
    log.info("Descargado %s: %s", kind, path)
    await page.goto(project_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)
    return path


async def generate(page: Page, prompt: str, *, kind: str, n: int = 1, max_credits: int | None,
                   out_dir: Path, timeout_s: int) -> dict:
    """Un mensaje al agente del proyecto abierto -> n resultados de `kind`, descargados."""
    name = OPEN_VIDEO if kind == "video" else OPEN_IMAGE
    before = await _count(page, name)
    capture = ResultCapture(page)  # por si la red vuelve a traer la URL (hoy no)
    capture.mark()
    sent = await send_and_confirm(page, prompt, kind=kind, expected_n=n, max_credits=max_credits, before=before)
    await wait_results(page, kind=kind, before=before, n=n, timeout_s=timeout_s)
    await page.wait_for_timeout(3000)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    files = [str(await download_result(page, kind=kind, index=before + i, out_dir=out_dir,
                                       stem=f"flow_{kind}_{stamp}_{i + 1}")) for i in range(n)]
    red = [u for u in capture.media[capture._baseline:] if media_kind(u) == kind]
    return {**sent, "archivos": files, "urls_red": len(red)}


# ── CLI ───────────────────────────────────────────────────────────

async def _run(a: argparse.Namespace) -> dict:
    from playwright.async_api import async_playwright

    from core.accounts import flow_url
    from flow.auth import launch_authenticated

    out: dict = {"cmd": a.cmd, "account": a.account}
    async with async_playwright() as p:
        ctx = await launch_authenticated(p, a.account, headless=not a.visible)
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.set_viewport_size({"width": 1440, "height": 900})
            await page.goto(flow_url(a.account), wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            if "accounts.google.com" in page.url or page.url.rstrip("/").endswith("/about"):
                raise RuntimeError("Sesion vencida: renovala con make importar")
            out["saldo_antes"] = await read_balance(page)
            if a.cmd == "creditos":
                return out
            cap = a.max_credits if a.max_credits is not None else settings.video_max_credits
            if a.cmd == "clip":
                model = resolve_model(a.model)
                out.update(modelo=model, estimado=estimate_video_cost(model, a.count))
            out["proyecto"] = await open_project(page, a.proyecto)
            if a.cmd == "clip":
                await set_defaults(page, video_model=model, video_aspect=a.aspect, video_count=a.count)
                res = await generate(page, a.prompt, kind="video", n=a.count, max_credits=cap,
                                     out_dir=a.out, timeout_s=settings.video_timeout)
            else:
                await set_defaults(page, image_aspect=a.aspect, image_count=1)
                res = await generate(page, a.prompt, kind="image", n=a.n, max_credits=cap,
                                     out_dir=a.out, timeout_s=300)
            out.update(res)
            out["saldo_despues"] = await read_balance(page)
            return out
        finally:
            await ctx.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flow.video", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["creditos", "imagenes", "clip"])
    ap.add_argument("--account", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--proyecto", help="URL del proyecto donde seguir (sin esto crea uno nuevo)")
    ap.add_argument("--model", default=None, help="lite | fast | quality | omni (default FLOW_VIDEO_MODEL)")
    ap.add_argument("--aspect", default=None, help="video: 16:9 | 9:16 ; imagen: 16:9 4:3 1:1 3:4 9:16")
    ap.add_argument("--count", type=int, default=1, help="clips por mensaje (x1..x4)")
    ap.add_argument("--n", type=int, default=1, help="imagenes que se piden en el mensaje")
    ap.add_argument("--max-credits", type=int, default=None, help="tope de puntos (default FLOW_VIDEO_MAX_CREDITS)")
    ap.add_argument("--out", type=Path, default=Path(settings.output_dir) / "video")
    ap.add_argument("--visible", action="store_true")
    a = ap.parse_args(argv)
    # Contrato de CLI: stdout es solo el JSON final; los logs van a stderr
    import logging
    for lg in [logging.getLogger(n) for n in list(logging.root.manager.loggerDict)]:
        for h in getattr(lg, "handlers", []):
            if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout:
                h.setStream(sys.stderr)
    if a.prompt_file:
        a.prompt = a.prompt_file.read_text(encoding="utf-8").strip()
    if a.cmd != "creditos" and not a.prompt:
        ap.error("falta --prompt o --prompt-file")
    a.aspect = a.aspect or (settings.video_aspect if a.cmd == "clip" else settings.image_aspect)
    try:
        if a.cmd == "clip":  # antes de abrir el navegador: si ya se sabe que no entra, ni se intenta
            cap = a.max_credits if a.max_credits is not None else settings.video_max_credits
            check_cap(estimate_video_cost(a.model or settings.video_model, a.count), cap, "estimacion del clip")
        out = asyncio.run(_run(a))
        code = 0
    except CreditCapError as e:
        out, code = {"cmd": a.cmd, "error": str(e), "tipo": "tope"}, 3
    except (NoCreditsError, GenerationRejectedError) as e:
        out, code = {"cmd": a.cmd, "error": str(e), "tipo": type(e).__name__}, 4
    except Exception as e:
        out, code = {"cmd": a.cmd, "error": str(e)[:500], "tipo": type(e).__name__}, 1
    print(json.dumps(out, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
