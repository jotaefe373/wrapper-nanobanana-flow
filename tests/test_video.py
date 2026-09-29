"""Video: lo que no necesita navegador (costo, tope, parseo de la UI, referencias)."""

import pytest

from flow.video import (
    CreditCapError,
    check_cap,
    estimate_video_cost,
    parse_balance,
    parse_confirmation,
    resolve_model,
    split_mentions,
)


def test_resuelve_alias_de_modelo():
    assert resolve_model("lite") == "Veo 3.1 - Lite"
    assert resolve_model("FAST") == "Veo 3.1 - Fast"
    assert resolve_model("Omni 1.1 Flash") == "Omni 1.1 Flash"


@pytest.mark.parametrize("model,count,ultra,expected", [
    ("lite", 1, False, 10),
    ("lite", 3, False, 30),
    ("lite", 1, True, 5),
    ("fast", 1, False, 20),
    ("quality", 1, False, 100),
    ("omni", 1, False, 12),
    ("desconocido", 1, False, None),
])
def test_estimacion_de_costo(model, count, ultra, expected):
    assert estimate_video_cost(model, count, ultra) == expected


def test_tope():
    check_cap(10, 10)            # igual al tope: pasa
    check_cap(100, None)         # sin tope: no limita
    check_cap(None, 5)           # costo desconocido: decide la confirmacion del agente
    with pytest.raises(CreditCapError):
        check_cap(20, 10)


@pytest.mark.parametrize("text,expected", [
    ("¿Quieres que empiece a generar 1 vídeo, que cuesta 12 puntos?", {"n": 1, "kind": "video", "cost": 12}),
    ("¿Quieres que empiece a generar 2 imágenes, que cuesta 0 puntos?", {"n": 2, "kind": "image", "cost": 0}),
    ("¿Quieres que empiece a generar 1 imagen, que cuesta 2 puntos?", {"n": 1, "kind": "image", "cost": 2}),
    ("Do you want me to generate 3 videos? It costs 30 credits", None),  # otro formato: no se adivina
    ("I've started generating your video.", None),
])
def test_parseo_de_confirmacion(text, expected):
    assert parse_confirmation(text) == expected


def test_parseo_de_saldo():
    assert parse_balance("mr smith\n93 puntos de Google Flow\nActualizar") == 93
    assert parse_balance("1.250 puntos de Google Flow") == 1250
    assert parse_balance("nada") is None


def test_referencias_en_el_prompt():
    assert split_mentions("@{mujer} entra a @{cafeteria} y se sienta") == [
        ("ref", "mujer"), ("text", " entra a "), ("ref", "cafeteria"), ("text", " y se sienta")]
    assert split_mentions("sin referencias") == [("text", "sin referencias")]
    assert split_mentions("") == []


def test_elige_la_referencia_por_todas_las_palabras():
    from flow.video import pick_option
    names = ["Coffee shop interior morning light", "Woman standing in yellow jacket",
             "Woman standing looking at camera"]
    assert pick_option(names, "yellow jacket") == 1      # el bug de la prueba: no el primero
    assert pick_option(names, "Coffee shop") == 0
    assert pick_option(names, "woman camera") == 2
    assert pick_option(names, "cafetería") is None       # sin coincidencia: se falla antes de enviar
    assert pick_option(["Cafetería de barrio"], "cafeteria") == 0  # sin tildes


def test_prefiere_la_imagen_sobre_un_video_que_coincide():
    from flow.video import pick_option
    names = ["Woman entering coffee shop sitting", "Coffee shop interior morning light"]
    kinds = ["Vídeo", "Imagen"]
    assert pick_option(names, "coffee shop", kinds) == 1   # el bug del clip 2
    assert pick_option(names[:1], "coffee shop", kinds[:1]) == 0  # sin imagen: el video
