import pytest

from core.config import settings
from flow.results import extract_media_urls, media_kind
from flow.generate import resolve_strategy

# Muestra realista: URL firmada doble-escapada (JSON dentro de JSON), como llega en as29s
SAMPLE = (
    r'[["wrb.fr","as29s","[\"id\",null,1,\"'
    r'https://flow-content.google/image/39119eb0-7b0d-4650-b6f3-8bf049eb85f3?'
    r'Expires\\u003d1789367534\\u0026KeyName\\u003dlabs-flow-prod-cdn-key\\u0026Signature\\u003dzGH-abc\"]"]]'
)
VIDEO_SAMPLE = r'foo \"https://flow-content.google/video/aaaa1111-2222-3333-4444-555566667777?Expires\\u003d1\\u0026Signature\\u003dx\" bar'


def test_extrae_url_de_imagen_desescapada():
    urls = extract_media_urls(SAMPLE)
    assert len(urls) == 1
    u = urls[0]
    assert u.startswith("https://flow-content.google/image/39119eb0-")
    assert "\\" not in u and "u003d" not in u
    assert "Signature=zGH-abc" in u and "KeyName=labs-flow-prod-cdn-key" in u
    assert media_kind(u) == "image"


def test_extrae_video():
    urls = extract_media_urls(VIDEO_SAMPLE)
    assert len(urls) == 1 and media_kind(urls[0]) == "video"
    assert urls[0].endswith("Signature=x")


def test_sin_urls_y_dedup():
    assert extract_media_urls("") == []
    assert extract_media_urls("nada de media aca") == []
    assert len(extract_media_urls(SAMPLE + SAMPLE)) == 1  # no duplica


@pytest.fixture(autouse=True)
def default_strategy(monkeypatch):
    monkeypatch.setattr(settings, "strategy", "auto")


@pytest.mark.parametrize("req,quality,expected", [
    (None, "1K", "auto"),
    ("hybrid", "1K", "hybrid"),
    ("classic", "1K", "classic"),
    ("raro", "1K", "auto"),          # valor invalido -> auto
    ("hybrid", "2K", "classic"),     # 2K/4K solo por editor -> classic
    ("auto", "4K", "classic"),
    ("classic", "2K", "classic"),
])
def test_resolucion_de_estrategia(req, quality, expected):
    assert resolve_strategy(req, quality) == expected


# --- Redacción del snapshot (crítico: nada de secretos al historial) ---
from flow.snapshot import redact, diff_latest  # noqa: E402


def test_redaccion_saca_secretos():
    muestra = (
        'url=https://flow-content.google/image/x?Signature=abc123&KeyName=labs-key '
        '"SNlM0e":"AQXbc12345token" contacto mr@gmail.com '
        '"blob":"0cAFcWeA5gFcckASwXjEngZkmQrxLQ5XDKmln12zSoU3UVHAyaLPXCR6vosMjZr12345"'
    )
    out = redact(muestra)
    assert "abc123" not in out and "Signature=<redacted>" in out
    assert "labs-key" not in out and "KeyName=<redacted>" in out
    assert "AQXbc12345token" not in out and '"SNlM0e":"<redacted>"' in out
    assert "mr@gmail.com" not in out and "<email>" in out
    assert "0cAFcWeA5gFcckAS" not in out and "<redacted-blob>" in out


def test_redaccion_no_rompe_texto_normal():
    assert redact("Proyecto nuevo") == "Proyecto nuevo"
    assert redact("") == ""
