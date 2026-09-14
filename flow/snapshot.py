"""
snapshot.py — Historial trazable de la interfaz y la API de Flow.

Captura el estado del sitio (screenshots, HTML sanitizado, superficie de
elementos, salud de los selectores criticos) y, opcional, el catalogo de RPCs
de una generacion. Todo redactado (sin cookies, tokens, firmas ni PII) y
guardado con fecha en history/<ts>/ para versionar en git: los diffs muestran
que cambio y cuando.

El health-check compara los selectores de los que dependen los macros: si Flow
renombra o mueve algo, avisa antes de gastar un credito.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from core.accounts import flow_url, rotation_order
from core.logger import get_logger

log = get_logger("snapshot")

HISTORY_DIR = Path("history")
DATA_ENDPOINT = "flow.google.com/_/AiSandboxAngularFrontend/data/"

# Selectores de los que dependen los macros. Fuente unica para health-check y snapshot.
# kind: "role" (rol+nombre), "css" (selector), "text" (texto visible).
CRITICAL_SELECTORS = [
    {"key": "proyecto_nuevo", "kind": "text", "value": "Proyecto nuevo", "screen": "home",
     "why": "abrir un proyecto para generar"},
    {"key": "configuracion", "kind": "role", "role": "button", "name": "Configuración", "screen": "project",
     "why": "abrir aspecto/modelo"},
    {"key": "editor_prompt", "kind": "css", "value": "[contenteditable=true]", "screen": "project",
     "why": "escribir el prompt"},
    {"key": "iniciar_generacion", "kind": "role", "role": "button", "name": "Iniciar generación", "screen": "project",
     "why": "disparar la generacion (paso que gasta el credito)"},
    {"key": "descargar_media", "kind": "role", "role": "button", "name": "Descargar contenido multimedia",
     "screen": "editor", "why": "descarga classic (respaldo); no pre-chequeable sin imagen"},
]

# ── Redaccion ─────────────────────────────────────────────────────

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_TOKEN = re.compile(r'"(SNlM0e|at|FdrFJe)":"[^"]+"')            # tokens WIZ (at, f.sid)
_SIG = re.compile(r"(Signature|KeyName|at)=[A-Za-z0-9_\-%.:]+")  # firmas de URLs / at
_LONGBLOB = re.compile(r'"[A-Za-z0-9_\-]{60,}"')                 # blobs largos (turn-token, etc.)


def redact(text: str) -> str:
    if not text:
        return text
    text = _TOKEN.sub(r'"\1":"<redacted>"', text)
    text = _SIG.sub(r"\1=<redacted>", text)
    text = _EMAIL.sub("<email>", text)
    text = _LONGBLOB.sub('"<redacted-blob>"', text)
    return text


_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
_STYLE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)


async def _sanitized_html(page: Page) -> str:
    """HTML del DOM con <script>/<style> vaciados (ahi viven los tokens) y luego redactado."""
    html = await page.content()
    html = _SCRIPT.sub("<script></script>", html)
    html = _STYLE.sub("<style></style>", html)
    return redact(html)


async def _surface(page: Page) -> list[dict]:
    """Elementos interactivos visibles: rol + nombre accesible (redactado)."""
    items = await page.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('button,[role=button],[role=radio],[role=tab],a,textbox,[contenteditable=true]')) {
            const r = el.getAttribute('role') || el.tagName.toLowerCase();
            const n = (el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 60);
            if (n) out.push({role: r, name: n});
        }
        return out;
    }""")
    IDENTIDAD = ("Cuenta de Google", "Google Account", "Detalles de la cuenta", "Account details")
    seen, uniq = set(), []
    for it in items:
        if any(it["name"].startswith(pfx) for pfx in IDENTIDAD):
            continue  # chip de identidad: no es superficie del sitio
        it["name"] = redact(it["name"])
        k = (it["role"], it["name"])
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    return uniq


# ── Health-check ──────────────────────────────────────────────────

async def _present(page: Page, sel: dict) -> bool:
    try:
        if sel["kind"] == "css":
            return await page.locator(sel["value"]).count() > 0
        if sel["kind"] == "text":
            return await page.get_by_text(sel["value"], exact=False).count() > 0
        return await page.get_by_role(sel["role"], name=sel["name"], exact=True).count() > 0
    except Exception:
        return False


async def health_check(page: Page, screens: tuple[str, ...] = ("home", "project")) -> dict:
    """Verifica los selectores criticos de las pantallas dadas. Devuelve {key: present}.

    Navega home -> proyecto. No chequea 'editor' (necesita imagen generada).
    """
    report: dict[str, bool] = {}

    async def check(screen: str):
        for sel in CRITICAL_SELECTORS:
            if sel["screen"] == screen:
                report[sel["key"]] = await _present(page, sel)

    if "home" in screens:
        await page.wait_for_timeout(1500)
        await check("home")
        try:
            await page.get_by_text("Proyecto nuevo").first.click()
            await page.wait_for_timeout(6000)
        except Exception:
            log.warning("No se pudo abrir 'Proyecto nuevo' — la UI pudo cambiar")
    if "project" in screens:
        await check("project")
    return report


def health_summary(report: dict) -> tuple[bool, list[str]]:
    """(todo_ok, faltantes)."""
    missing = [k for k, ok in report.items() if not ok]
    return (not missing, missing)


# ── Captura completa ──────────────────────────────────────────────

async def capture(page: Page, out: Path, account: str) -> dict:
    """Captura UI (screenshots + html + surface) y health. Devuelve el health report."""
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, bool] = {}

    async def snap(screen: str):
        try:
            await page.screenshot(path=str(out / f"{screen}.png"))
            (out / f"{screen}.html").write_text(await _sanitized_html(page), encoding="utf-8")
            (out / f"{screen}.surface.json").write_text(
                json.dumps(await _surface(page), ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            log.warning("No se pudo capturar la pantalla '%s' (%s)", screen, str(e)[:60])

    await page.goto(flow_url(account))
    await page.wait_for_timeout(4000)
    await snap("home")
    for sel in CRITICAL_SELECTORS:
        if sel["screen"] == "home":
            report[sel["key"]] = await _present(page, sel)

    try:
        await page.get_by_text("Proyecto nuevo").first.click()
        await page.wait_for_timeout(6000)
        await snap("project")
        for sel in CRITICAL_SELECTORS:
            if sel["screen"] == "project":
                report[sel["key"]] = await _present(page, sel)
        try:
            await page.get_by_role("button", name="Configuración", exact=True).click()
            await page.wait_for_timeout(2000)
            await snap("config")
        except Exception:
            log.warning("No se pudo abrir Configuración para el snapshot")
    except Exception:
        log.warning("No se pudo abrir un proyecto para el snapshot")

    (out / "health.json").write_text(
        json.dumps({"account": account, "when": datetime.now().isoformat(), "selectors": report},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return report


# ── Captura de API (opcional, gasta 1 credito) ────────────────────

async def capture_api(page: Page, out: Path, prompt: str = "a plain grey sphere on white, product shot") -> None:
    """Cataloga los RPCs de una generacion real. Escribe api.json (redactado)."""
    import urllib.parse as up
    from flow import generate

    catalog: dict[str, dict] = {}

    def rpcids(url: str) -> str:
        if "StreamChat" in url:
            return "StreamChat"
        q = up.parse_qs(up.urlparse(url).query)
        return q.get("rpcids", ["?"])[0]

    async def on_req(req):
        if DATA_ENDPOINT not in req.url or req.method != "POST":
            return
        rid = rpcids(req.url)
        entry = catalog.setdefault(rid, {"endpoint": up.urlparse(req.url).path[:120], "method": req.method})
        try:
            body = req.post_data
            if body and "request_sample" not in entry:
                entry["request_sample"] = redact(body)[:400]
        except Exception:
            pass

    async def on_resp(resp):
        if DATA_ENDPOINT not in resp.url or resp.request.method != "POST":
            return
        rid = rpcids(resp.url)
        entry = catalog.setdefault(rid, {"endpoint": up.urlparse(resp.url).path[:120]})
        entry["status"] = resp.status
        try:
            body = (await resp.body()).decode("utf-8", "replace")
            if "response_sample" not in entry:
                entry["response_sample"] = redact(body)[:400]
        except Exception:
            pass

    page.on("request", on_req)
    page.on("response", on_resp)
    try:
        await generate.generate_and_save(page, prompt)
    except Exception as e:
        log.warning("La generacion para el catalogo API fallo (%s); guardo lo capturado", str(e)[:60])

    (out / "api.json").write_text(
        json.dumps({"rpcs": catalog, "when": datetime.now().isoformat()}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    log.info("Catalogo API: %d RPCs distintos", len(catalog))


# ── Orquestacion ──────────────────────────────────────────────────

async def run_snapshot(account: str | None = None, with_api: bool = False) -> Path:
    """Captura un snapshot completo del sitio en history/<ts>/."""
    from playwright.async_api import async_playwright
    from flow.auth import launch_authenticated

    acc = (account or rotation_order()[0])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = HISTORY_DIR / ts
    log.info("Snapshot de '%s' -> %s (api=%s)", acc, out, with_api)

    async with async_playwright() as p:
        ctx = await launch_authenticated(p, acc, headless=True)
        try:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            report = await capture(page, out, acc)
            ok, missing = health_summary(report)
            if ok:
                log.info("Salud de selectores: OK (%d/%d)", len(report), len(report))
            else:
                log.warning("Salud de selectores: FALTAN %s", missing)
            if with_api:
                await capture_api(page, out)
        finally:
            await ctx.close()

    log.info("Snapshot guardado en %s", out)
    return out


def latest_two() -> tuple[Path | None, Path | None]:
    if not HISTORY_DIR.exists():
        return None, None
    snaps = sorted(d for d in HISTORY_DIR.iterdir() if d.is_dir())
    if len(snaps) < 2:
        return (snaps[-1] if snaps else None), None
    return snaps[-1], snaps[-2]


def diff_latest() -> str:
    """Diff legible (salud + superficie) entre los dos ultimos snapshots."""
    latest, prev = latest_two()
    if not latest:
        return "No hay snapshots todavia. Corre 'make snapshot'."
    if not prev:
        return f"Solo hay un snapshot ({latest.name}); nada que comparar."

    lines = [f"Comparando {prev.name} -> {latest.name}", ""]

    lh = json.loads((latest / "health.json").read_text())["selectors"]
    ph = json.loads((prev / "health.json").read_text())["selectors"]
    changed = [f"  {k}: {ph.get(k)} -> {lh.get(k)}" for k in sorted(set(lh) | set(ph)) if ph.get(k) != lh.get(k)]
    lines.append("Selectores criticos: " + ("sin cambios" if not changed else ""))
    lines += changed

    for screen in ("home", "project", "config"):
        fa, fb = prev / f"{screen}.surface.json", latest / f"{screen}.surface.json"
        if not (fa.exists() and fb.exists()):
            continue
        a = {(x["role"], x["name"]) for x in json.loads(fa.read_text())}
        b = {(x["role"], x["name"]) for x in json.loads(fb.read_text())}
        added, removed = b - a, a - b
        if added or removed:
            lines.append(f"\n[{screen}]")
            lines += [f"  + {r}:{n}" for r, n in sorted(added)]
            lines += [f"  - {r}:{n}" for r, n in sorted(removed)]
    return "\n".join(lines)
