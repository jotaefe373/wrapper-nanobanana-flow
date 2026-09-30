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
from flow.generate import SETTINGS_RE, open_new_project

log = get_logger("snapshot")

HISTORY_DIR = Path("history")
DATA_ENDPOINT = "flow.google.com/_/AiSandboxAngularFrontend/data/"

# Selectores de los que dependen los macros. Fuente unica para health-check y snapshot.
# kind: "role" (rol+nombre exacto; admite alternativas "A|B"), "css" (selector), "text" (texto visible).
CRITICAL_SELECTORS = [
    {"key": "proyecto_nuevo", "kind": "role", "role": "button", "name": ".*(?:Proyecto nuevo|Nuevo proyecto|New project).*", "screen": "home",
     "why": "abrir un proyecto para generar"},
    {"key": "configuracion", "kind": "role", "role": "button", "name": "Configuración|Ajustes", "screen": "project",
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
            return await page.get_by_text(re.compile(sel["value"])).count() > 0
        return await page.get_by_role(sel["role"], name=re.compile(f"^(?:{sel['name']})$", re.S)).count() > 0
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
            await open_new_project(page)
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
        await open_new_project(page)
        await page.wait_for_timeout(6000)
        await snap("project")
        for sel in CRITICAL_SELECTORS:
            if sel["screen"] == "project":
                report[sel["key"]] = await _present(page, sel)
        try:
            await page.get_by_role("button", name=SETTINGS_RE).click()
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


# ── Dashboard HTML local (solo datos, sin capturas) ───────────────

def _load_history() -> list[dict]:
    """Lee todos los snapshots de history/ ordenados de viejo a nuevo."""
    if not HISTORY_DIR.exists():
        return []
    snaps = []
    for d in sorted(x for x in HISTORY_DIR.iterdir() if x.is_dir()):
        hp = d / "health.json"
        if not hp.exists():
            continue
        health = json.loads(hp.read_text())
        surfaces = {}
        for sf in d.glob("*.surface.json"):
            surfaces[sf.name.split(".")[0]] = json.loads(sf.read_text())
        api = None
        ap = d / "api.json"
        if ap.exists():
            api = json.loads(ap.read_text()).get("rpcs")
        snaps.append({"ts": d.name, "when": health.get("when", ""),
                      "account": health.get("account", ""), "health": health.get("selectors", {}),
                      "surfaces": surfaces, "api": api})
    return snaps


def _diffs(snaps: list[dict]) -> list[dict]:
    out = []
    for prev, cur in zip(snaps, snaps[1:]):
        hchanges = [{"key": k, "from": prev["health"].get(k), "to": cur["health"].get(k)}
                    for k in sorted(set(prev["health"]) | set(cur["health"]))
                    if prev["health"].get(k) != cur["health"].get(k)]
        sdiff = {}
        for screen in sorted(set(prev["surfaces"]) | set(cur["surfaces"])):
            a = {(x["role"], x["name"]) for x in prev["surfaces"].get(screen, [])}
            b = {(x["role"], x["name"]) for x in cur["surfaces"].get(screen, [])}
            added, removed = sorted(b - a), sorted(a - b)
            if added or removed:
                sdiff[screen] = {"added": added, "removed": removed}
        if hchanges or sdiff:
            out.append({"from": prev["ts"], "to": cur["ts"], "health": hchanges, "surface": sdiff})
    return out


def build_history_ui(out_path: Path | None = None) -> Path:
    """Genera un dashboard HTML autocontenido del historial (solo datos)."""
    from html import escape as e

    out_path = out_path or (HISTORY_DIR / "dashboard.html")
    snaps = _load_history()
    keys = [s["key"] for s in CRITICAL_SELECTORS]
    why = {s["key"]: s["why"] for s in CRITICAL_SELECTORS}

    # Matriz de salud: filas = snapshot (nuevo arriba), columnas = selector
    rows = []
    for s in reversed(snaps):
        cells = ""
        for k in keys:
            v = s["health"].get(k)
            cls = "ok" if v is True else ("bad" if v is False else "na")
            sym = "✓" if v is True else ("✕" if v is False else "–")
            cells += f'<td class="{cls}" title="{e(why.get(k,""))}">{sym}</td>'
        when = e(s["when"][:19].replace("T", " "))
        rows.append(f'<tr><td class="ts">{e(s["ts"])}</td><td class="acc">{e(s["account"])}</td>'
                    f'<td class="when">{when}</td>{cells}</tr>')
    header_cells = "".join(f'<th title="{e(why.get(k,""))}"><span>{e(k)}</span></th>' for k in keys)
    matrix = (f'<table class="matrix"><thead><tr><th>snapshot</th><th>cuenta</th><th>fecha</th>'
              f'{header_cells}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
              if snaps else '<p class="empty">No hay snapshots todavia. Corre <code>make snapshot</code>.</p>')

    # Diffs
    diff_html = ""
    for d in reversed(_diffs(snaps)):
        parts = [f'<h3>{e(d["from"])} → {e(d["to"])}</h3>']
        if d["health"]:
            parts.append('<div class="hchg">')
            for c in d["health"]:
                parts.append(f'<div>selector <code>{e(c["key"])}</code>: {c["from"]} → <b>{c["to"]}</b></div>')
            parts.append("</div>")
        for screen, sd in d["surface"].items():
            parts.append(f'<div class="scr"><span class="scrname">{e(screen)}</span>')
            for r, n in sd["added"]:
                parts.append(f'<div class="add">+ {e(r)}: {e(n)}</div>')
            for r, n in sd["removed"]:
                parts.append(f'<div class="rem">− {e(r)}: {e(n)}</div>')
            parts.append("</div>")
        diff_html += f'<div class="diff">{"".join(parts)}</div>'
    if not diff_html:
        diff_html = '<p class="empty">Sin cambios entre snapshots (o hace falta un segundo snapshot).</p>'

    # Superficie del ultimo snapshot
    surf_html = ""
    if snaps:
        last = snaps[-1]
        for screen, items in last["surfaces"].items():
            lis = "".join(f'<li><span class="role">{e(i["role"])}</span> {e(i["name"])}</li>' for i in items)
            surf_html += f'<details><summary>{e(screen)} ({len(items)})</summary><ul class="surf">{lis}</ul></details>'

    api_html = ""
    if snaps and snaps[-1]["api"]:
        for rid, info in snaps[-1]["api"].items():
            api_html += (f'<details><summary><code>{e(rid)}</code> <span class="dim">{e(info.get("endpoint",""))}</span></summary>'
                         f'<pre>{e(json.dumps(info, ensure_ascii=False, indent=1))}</pre></details>')
    api_section = f'<section><h2>Catalogo de API (RPCs)</h2>{api_html}</section>' if api_html else ""

    n = len(snaps)
    rng = f'{snaps[0]["ts"]} … {snaps[-1]["ts"]}' if snaps else "—"
    html = (_DASHBOARD_TMPL
            .replace("__N__", str(n)).replace("__RNG__", e(rng))
            .replace("__MATRIX__", matrix).replace("__DIFFS__", diff_html)
            .replace("__SURFACE__", surf_html or '<p class="empty">—</p>')
            .replace("__API__", api_section)
            .replace("__GENERATED__", datetime.now().strftime("%Y-%m-%d %H:%M")))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    log.info("Dashboard generado: %s (%d snapshots)", out_path, n)
    return out_path


_DASHBOARD_TMPL = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Historial de Flow</title>
<style>
:root{--bg:#eef1f4;--card:#fff;--ink:#15181e;--dim:#5a626e;--line:#d8dde3;
--ok:#3c7a52;--okbg:#e4eee7;--bad:#b0384a;--badbg:#f3e1e4;--na:#a2abb6;--acc:#2f6884;--mono:"SFMono-Regular",Consolas,monospace}
@media(prefers-color-scheme:dark){:root{--bg:#0c0f13;--card:#14181e;--ink:#e7eaee;--dim:#9ba4b0;--line:#28303a;
--ok:#5ca379;--okbg:#152318;--bad:#d9748a;--badbg:#2a171c;--na:#5a636e;--acc:#63a8c6}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 18px 60px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--dim);font-size:13px;margin-bottom:24px}
h2{font-size:16px;margin:30px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:18px}
.matrix{border-collapse:collapse;width:100%;font-size:13px}
.matrix th,.matrix td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:center}
.matrix thead th{color:var(--dim);font-weight:600;font-size:11px;text-transform:uppercase;vertical-align:bottom}
.matrix thead th span{writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap;font-family:var(--mono);text-transform:none;letter-spacing:.02em}
.matrix td.ts{font-family:var(--mono);text-align:left;color:var(--acc)}
.matrix td.acc,.matrix td.when{text-align:left;color:var(--dim);font-size:12px;font-variant-numeric:tabular-nums}
.matrix td.ok{color:var(--ok);background:var(--okbg);font-weight:700}
.matrix td.bad{color:var(--bad);background:var(--badbg);font-weight:700}
.matrix td.na{color:var(--na)}
.diff{border-left:3px solid var(--acc);padding:2px 14px;margin:14px 0}
.diff h3{font-family:var(--mono);font-size:13px;margin:6px 0}
.add{color:var(--ok)}.rem{color:var(--bad)}
.scr{margin:8px 0}.scrname{font-family:var(--mono);color:var(--dim);font-size:12px}
.hchg code,.diff code{font-family:var(--mono);background:var(--bg);padding:1px 5px;border-radius:4px}
details{margin:6px 0}summary{cursor:pointer;font-weight:600}
ul.surf{list-style:none;padding-left:10px;margin:8px 0;columns:2;font-size:13px}
ul.surf li{break-inside:avoid;padding:2px 0}
.surf .role{font-family:var(--mono);color:var(--acc);font-size:11px}
.dim{color:var(--dim);font-weight:400;font-family:var(--mono);font-size:11px}
pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px;overflow:auto;font-size:12px}
.empty{color:var(--dim)}
@media(max-width:560px){ul.surf{columns:1}}
</style></head><body><div class="wrap">
<h1>Historial de Flow</h1>
<div class="sub">__N__ snapshot(s) · __RNG__ · generado __GENERATED__</div>
<section><h2>Salud de selectores en el tiempo</h2>
<div style="overflow-x:auto">__MATRIX__</div>
<p class="sub" style="margin-top:10px">✓ presente · ✕ falta · – sin dato. Si una columna pasa a ✕, ese paso del flujo se rompio.</p></section>
<section><h2>Cambios entre snapshots</h2>__DIFFS__</section>
<section><h2>Superficie (ultimo snapshot)</h2>__SURFACE__</section>
__API__
</div></body></html>"""


# ── Auto-snapshot al detectar cambios ─────────────────────────────

def last_health() -> dict:
    """Selectores del snapshot mas reciente (o {} si no hay)."""
    if not HISTORY_DIR.exists():
        return {}
    for d in sorted((x for x in HISTORY_DIR.iterdir() if x.is_dir()), reverse=True):
        hp = d / "health.json"
        if hp.exists():
            return json.loads(hp.read_text()).get("selectors", {})
    return {}


def changed_keys(current: dict, prior: dict) -> list[str]:
    """Selectores cuyo estado difiere respecto del snapshot previo (pura, testeable).

    Solo compara claves presentes en ambos: si no hay baseline (prior vacio), no
    reporta cambios (no hay con que comparar).
    """
    return sorted(k for k, v in current.items() if k in prior and prior[k] != v)


async def capture_current(page: Page, account: str = "?", note: str = "") -> Path:
    """Snapshot liviano de la pantalla ACTUAL (sin navegar), con fecha. Para auto-captura."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = HISTORY_DIR / ts
    out.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=str(out / "project.png"))
        (out / "project.html").write_text(await _sanitized_html(page), encoding="utf-8")
        (out / "project.surface.json").write_text(
            json.dumps(await _surface(page), ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        log.warning("Auto-snapshot: no se pudo capturar la pantalla (%s)", str(e)[:60])
    report = {s["key"]: await _present(page, s) for s in CRITICAL_SELECTORS if s["screen"] == "project"}
    (out / "health.json").write_text(
        json.dumps({"account": account, "when": datetime.now().isoformat(), "trigger": note or "auto",
                    "selectors": report}, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Auto-snapshot guardado: %s (%s)", out, note)
    return out
