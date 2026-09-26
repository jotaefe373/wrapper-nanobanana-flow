"""
credits.py — Detecta cuando una cuenta no puede generar: sin creditos o sesion vencida.

El replayer usa estas excepciones para saltar a la siguiente cuenta.
"""

import re

from playwright.async_api import Locator, Page

# Textos que Flow podria mostrar al quedarse sin creditos (es/en).
NO_CREDITS_RE = re.compile(
    r"(sin|no (te )?quedan|no tienes( suficientes)?|insuficientes|agotaste( tus| los)?)\s+cr[eé]ditos"
    r"|cr[eé]ditos\s+(insuficientes|agotados)"
    r"|(not enough|out of|insufficient|no more)\s+(ai\s+)?credits"
    r"|l[ií]mite\s+(diario|mensual|de\s+generaci[oó]n)",
    re.IGNORECASE,
)


# Flow rechazo el prompt (filtro de seguridad o error de generacion). Cambiar de
# cuenta no sirve: hay que reescribir el prompt, asi que se falla rapido.
REJECTED_RE = re.compile(
    r"safety filter|filtro de seguridad"
    r"|Se ha producido un error\. Int[eé]ntalo de nuevo"
    r"|wasn't able to generate|no (he )?pude generar",
    re.IGNORECASE,
)


class GenerationRejectedError(RuntimeError):
    """Flow rechazo la generacion (tipicamente por el filtro de seguridad)."""


class NoCreditsError(RuntimeError):
    """La cuenta no tiene creditos suficientes para generar."""


class SessionExpiredError(RuntimeError):
    """La sesion de Google de la cuenta ya no es valida."""


async def wait_for_result(page: Page, result: Locator, timeout: int = 120_000) -> None:
    """Espera el resultado de la generacion, o falla rapido si aparece un aviso de creditos."""
    no_credits = page.get_by_text(NO_CREDITS_RE)
    await result.or_(no_credits).first.wait_for(timeout=timeout)
    if not await result.count() and await no_credits.count():
        raise NoCreditsError(f"Flow indica que no quedan creditos: {await no_credits.first.inner_text()!r}")


async def diagnose(page: Page) -> Exception | None:
    """Explica un fallo del macro si se debe a la cuenta. None si es otro problema."""
    url = page.url
    if "accounts.google.com" in url or url.rstrip("/").endswith("/about"):
        return SessionExpiredError(f"Sesion vencida (Flow redirigio a {url.split('?')[0]})")
    try:
        if await page.get_by_text(NO_CREDITS_RE).count():
            return NoCreditsError("Flow indica que no quedan creditos")
    except Exception:
        pass
    return None
