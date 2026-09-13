import pytest

from core import accounts
from core.config import settings
from flow.credits import NO_CREDITS_RE


@pytest.fixture(autouse=True)
def session_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "session_dir", str(tmp_path))
    monkeypatch.setattr(settings, "credentials_key", None)
    return tmp_path


def make_account(name):
    cookies = accounts.profile_dir(name) / "Default" / "Cookies"
    cookies.parent.mkdir(parents=True)
    cookies.write_bytes(b"")


def test_sin_cuentas_falla_con_instruccion():
    with pytest.raises(FileNotFoundError, match="make login"):
        accounts.rotation_order()


def test_rotacion_parte_por_la_siguiente_a_la_ultima():
    for name in ("b", "a", "c"):
        make_account(name)
    assert accounts.rotation_order() == ["a", "b", "c"]
    accounts.mark_used("a")
    assert accounts.rotation_order() == ["b", "c", "a"]
    accounts.mark_used("c")
    assert accounts.rotation_order() == ["a", "b", "c"]


def test_cuenta_forzada_no_rota():
    make_account("a")
    make_account("b")
    assert accounts.rotation_order("b") == ["b"]
    with pytest.raises(ValueError, match="no existe"):
        accounts.rotation_order("zz")


def test_ultima_cuenta_borrada_reinicia_rotacion():
    make_account("a")
    accounts.mark_used("borrada")
    assert accounts.rotation_order() == ["a"]


def test_directorio_sin_perfil_no_cuenta():
    make_account("a")
    (accounts.accounts_dir() / "vacia").mkdir()
    assert accounts.list_accounts() == ["a"]


def test_migra_perfil_de_cuenta_unica(session_tmp):
    legacy = session_tmp / "chrome-profile" / "Default"
    legacy.mkdir(parents=True)
    (legacy / "Cookies").write_bytes(b"")
    (session_tmp / "credentials.enc").write_bytes(b"x")

    assert accounts.list_accounts() == [accounts.DEFAULT_ACCOUNT]
    assert not (session_tmp / "chrome-profile").exists()
    assert accounts.credentials_path(accounts.DEFAULT_ACCOUNT).exists()


def test_resolve_account_con_varias_exige_nombre():
    assert accounts.resolve_account(None) == accounts.DEFAULT_ACCOUNT
    make_account("a")
    assert accounts.resolve_account(None) == "a"
    make_account("b")
    with pytest.raises(ValueError, match="ACCOUNT="):
        accounts.resolve_account(None)
    assert accounts.resolve_account("nueva") == "nueva"


@pytest.mark.parametrize("text", [
    "No tienes suficientes créditos para generar",
    "Créditos insuficientes",
    "Te quedaste sin créditos de IA",
    "You're out of AI credits",
    "Not enough credits",
    "Alcanzaste el límite diario",
])
def test_detecta_avisos_de_creditos(text):
    assert NO_CREDITS_RE.search(text)


@pytest.mark.parametrize("text", ["100 créditos de IA", "Crear", "Nano Banana 2", "Imagen generada"])
def test_no_confunde_textos_normales(text):
    assert not NO_CREDITS_RE.search(text)


def test_flow_url_por_cuenta():
    make_account("a")
    assert accounts.flow_url("a") == settings.base_url
    accounts.save_meta("a", email="a@x.com", flow_url="https://flow.google.com/u/1/")
    accounts.save_meta("a", otra="cosa")
    assert accounts.flow_url("a") == "https://flow.google.com/u/1/"
    assert accounts.load_meta("a")["email"] == "a@x.com"


def test_solo_cookies_de_autenticacion():
    from core.chrome_import import filter_auth_cookies

    cookies = [
        {"name": "SID", "domain": ".google.com"},
        {"name": "LSID", "domain": "accounts.google.com"},
        {"name": "NID", "domain": ".google.com"},
        {"name": "OSID", "domain": "flow.google.com"},
        {"name": "SID", "domain": ".google.cl"},
    ]
    assert [(c["name"], c["domain"]) for c in filter_auth_cookies(cookies)] == [
        ("SID", ".google.com"), ("LSID", "accounts.google.com"),
    ]
