"""
stealth.py — Tecnicas anti-deteccion para Playwright.
Adaptado de gmaps-data-scrapper/scraping/clients/stealth.py
"""

import asyncio
import random

from playwright.async_api import BrowserContext, Page

# ──────────────────────────────────────────────────────────────────
# 1. PATCHEO DE PROPIEDADES JS
# ──────────────────────────────────────────────────────────────────

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ],
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['es-CL', 'es', 'en-US', 'en'],
});

const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
);

if (!window.chrome) {
    window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
}

const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""


async def apply_stealth(context: BrowserContext):
    """Inyecta patches anti-deteccion en cada nueva pagina."""
    await context.add_init_script(STEALTH_JS)


# ──────────────────────────────────────────────────────────────────
# 2. MOUSE & CLICK HUMANO
# ──────────────────────────────────────────────────────────────────


async def human_move(page: Page, x: int, y: int, steps: int = 12):
    """Mueve el mouse con curva Bezier."""
    cx = random.randint(min(0, x) - 80, max(0, x) + 80)
    cy = random.randint(min(0, y) - 80, max(0, y) + 80)

    current = await page.evaluate("() => ({ x: window._mouseX || 0, y: window._mouseY || 0 })")
    x0, y0 = current.get("x", 0), current.get("y", 0)

    for i in range(steps + 1):
        t = i / steps
        bx = int((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x)
        by = int((1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y)
        bx += random.randint(-2, 2)
        by += random.randint(-2, 2)
        await page.mouse.move(bx, by)
        await asyncio.sleep(random.uniform(0.01, 0.04))

    await page.evaluate(f"() => {{ window._mouseX = {x}; window._mouseY = {y}; }}")


async def human_click(page: Page, target):
    """Click humano con movimiento de curva. Acepta selector CSS (str) o Locator."""
    from playwright.async_api import Locator

    if isinstance(target, str):
        el = page.locator(target).first
    elif isinstance(target, Locator):
        el = target
    else:
        raise TypeError(f"target debe ser str o Locator, no {type(target)}")

    box = await el.bounding_box()
    if not box:
        await el.click()
        return

    tx = int(box["x"] + box["width"] * random.uniform(0.3, 0.7))
    ty = int(box["y"] + box["height"] * random.uniform(0.3, 0.7))

    await human_move(page, tx, ty)
    await asyncio.sleep(random.uniform(0.08, 0.25))
    await page.mouse.click(tx, ty)


# ──────────────────────────────────────────────────────────────────
# 3. DELAYS
# ──────────────────────────────────────────────────────────────────


async def human_delay(base_ms: int = 1500, variance: float = 0.4):
    """Espera con distribucion gaussiana. 5% chance de pausa larga."""
    if random.random() < 0.05:
        await asyncio.sleep(random.uniform(3.0, 8.0))
        return

    sigma = base_ms * variance
    ms = random.gauss(base_ms, sigma)
    ms = max(base_ms * 0.4, min(ms, base_ms * 2.5))
    await asyncio.sleep(ms / 1000)


# ──────────────────────────────────────────────────────────────────
# 4. CONTEXTO ALEATORIO
# ──────────────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]


def random_context_params() -> dict:
    """Parametros aleatorios para browser context."""
    return {
        "user_agent": random.choice(USER_AGENTS),
        "viewport": random.choice(VIEWPORTS),
        "locale": "es-CL",
        "timezone_id": "America/Santiago",
        "color_scheme": "light",
        "extra_http_headers": {
            "Accept-Language": "es-CL,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        },
    }
