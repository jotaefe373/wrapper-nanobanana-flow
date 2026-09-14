"""
results.py — Extrae URLs de media (imagen/video) de las respuestas RPC de Flow.

Cuando Flow termina una generacion, la respuesta del RPC (as29s/csbIsb) trae la
URL firmada del archivo en flow-content.google. La estrategia hibrida lee esa URL
directo de la red, en vez de scrapear el DOM. Esta funcion es pura para poder
testearla sin navegador.
"""

import re

# URLs firmadas de Flow; los '=' y '&' vienen escapados como = / & en el JSON
_MEDIA_RE = re.compile(r'https://flow-content\.google/(?:image|video)/[^\s"\\]+')


def _unescape(text: str) -> str:
    # El payload va JSON-dentro-de-JSON: los escapes pueden venir con 1 o mas backslashes
    text = re.sub(r"\\+u003d", "=", text)
    text = re.sub(r"\\+u0026", "&", text)
    text = re.sub(r"\\+/", "/", text)
    return text


def extract_media_urls(text: str) -> list[str]:
    """URLs de media (imagen/video) presentes en el texto, en orden de aparicion, sin duplicar."""
    if not text:
        return []
    # Desescapar primero: las URLs traen \u003d / \u0026 y el backslash cortaria el match
    clean = _unescape(text)
    seen, out = set(), []
    for url in _MEDIA_RE.findall(clean):
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def media_kind(url: str) -> str:
    """'video' o 'image' segun la URL."""
    return "video" if "/video/" in url else "image"
