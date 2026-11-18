"""Traducción de los textos de la interfaz: qué se traduce, qué se respeta y qué se rechaza."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import traduccion_de_interfaz as modulo
from app.traduccion_de_interfaz import (
    aplanar,
    huella,
    planificar,
    reconstruir,
    traducir,
    validar,
    variables_del_servidor,
)

ORIGEN = {
    "comun": {"hola": "Hola, {{ nombre }}", "cerrar": "Cerrar"},
    "nuevo": "Nuevo",
}


def test_aplanar_y_reconstruir_conservan_forma_y_orden() -> None:
    plano = aplanar(ORIGEN)
    assert list(plano) == ["comun.hola", "comun.cerrar", "nuevo"]
    parcial = {"comun.cerrar": "Close", "nuevo": "New"}
    assert reconstruir(ORIGEN, parcial) == {"comun": {"cerrar": "Close"}, "nuevo": "New"}


def test_planificar_respeta_las_correcciones_a_mano() -> None:
    origen = {"a": "Uno", "b": "Dos (cambiado)", "c": "Tres (cambiado)", "d": "Cuatro"}
    destino = {"a": "One", "b": "Two", "c": "Three, edited by hand", "x": "Gone"}
    huellas = {
        "a": {"origen": huella("Uno"), "destino": huella("One")},
        "b": {"origen": huella("Dos"), "destino": huella("Two")},
        "c": {"origen": huella("Tres"), "destino": huella("Three")},
    }
    plan = planificar(origen, destino, huellas)
    # `a` está al día; `b` cambió en español; `d` falta; `c` se corrigió a mano.
    assert plan.traducir == ["b", "d"]
    assert plan.revisar == ["c"]
    assert plan.sobrantes == ["x"]


def test_validar_rechaza_variables_distintas_y_respuestas_vacias() -> None:
    originales = {"a": "Hola, {{ nombre }}", "b": "Cerrar", "c": "Ver"}
    respuesta = json.dumps({"a": "Hello, {{ name }}", "b": "Close", "c": " "})
    validas, rechazadas = validar(originales, respuesta)
    assert validas == {"b": "Close"}
    assert rechazadas == ["a", "c"]
    assert validar(originales, "no es json") == ({}, ["a", "b", "c"])


def test_variables_del_servidor_incluyen_especificador_y_conversion() -> None:
    assert variables_del_servidor("De {minimo} a {maximo:>3} ({x!r}), {{literal}}.") == [
        ("maximo", ">3", ""),
        ("minimo", "", ""),
        ("x", "", "r"),
    ]


def test_validar_del_servidor_rechaza_especificadores_y_conversiones_nuevos() -> None:
    originales = {
        "a": "Entre {minimo} y {maximo} caracteres.",
        "b": "Hola, {nombre}.",
        "c": "Hola, {nombre}.",
        "d": "Total: {importe:.2f} €.",
    }
    respuesta = json.dumps(
        {
            "a": "Between {minimo} and {maximo} characters.",
            "b": "Hi, {nombre!r}.",
            "c": "Hi, {nombre:>40}.",
            "d": "Total: {importe} €.",
        }
    )
    validas, rechazadas = validar(originales, respuesta, variables_del_servidor)
    assert validas == {"a": "Between {minimo} and {maximo} characters."}
    assert rechazadas == ["b", "c", "d"]


def test_validar_del_servidor_rechaza_solo_la_clave_con_llaves_mal_formadas() -> None:
    originales = {"a": "Hola, {nombre}.", "b": "Adiós, {nombre}.", "c": "Cerrar"}
    respuesta = json.dumps({"a": "Hi, {nombre.", "b": "Bye, {nombre}.", "c": "Close }"})
    validas, rechazadas = validar(originales, respuesta, variables_del_servidor)
    assert validas == {"b": "Bye, {nombre}."}
    assert rechazadas == ["a", "c"]


@pytest.fixture
def carpeta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    i18n = tmp_path / "assets"
    i18n.mkdir()
    (i18n / "es-ES.json").write_text(json.dumps(ORIGEN), encoding="utf-8")
    monkeypatch.setattr(modulo, "CARPETA_TRADUCCIONES", i18n)
    monkeypatch.setattr(modulo, "FICHERO_HUELLAS", tmp_path / "huellas.json")
    monkeypatch.setattr(modulo, "FICHERO_GLOSARIO", tmp_path / "glosario.json")
    return i18n


async def test_traduce_lo_pendiente_y_no_repite_lo_hecho(carpeta: Path) -> None:
    llamadas: list[dict[str, str]] = []

    async def traductor(mensajes: list[dict[str, str]]) -> str:
        textos = json.loads(mensajes[1]["content"])
        llamadas.append(textos)
        equivalencias = {"Hola, {{ nombre }}": "Hi, {{ nombre }}", "Cerrar": "Close"}
        return json.dumps(
            {clave: equivalencias.get(texto, "New") for clave, texto in textos.items()}
        )

    simulado = await traducir("en-US", None, simular=True)
    assert simulado.pendientes == 3
    assert not (carpeta / "en-US.json").exists()

    informe = await traducir("en-US", traductor)
    assert informe.traducidas == 3
    assert json.loads((carpeta / "en-US.json").read_text(encoding="utf-8")) == {
        "comun": {"hola": "Hi, {{ nombre }}", "cerrar": "Close"},
        "nuevo": "New",
    }

    # Segunda pasada sin cambios: no llama a la IA.
    llamadas.clear()
    assert (await traducir("en-US", traductor)).traducidas == 0
    assert llamadas == []


async def test_un_texto_que_rompe_las_variables_no_se_guarda(carpeta: Path) -> None:
    async def traductor(mensajes: list[dict[str, str]]) -> str:
        textos = json.loads(mensajes[1]["content"])
        return json.dumps({clave: "Sin variable" for clave in textos})

    informe = await traducir("en-US", traductor)
    assert informe.rechazadas == ["comun.hola"]
    guardado = json.loads((carpeta / "en-US.json").read_text(encoding="utf-8"))
    assert "hola" not in guardado["comun"]


async def test_un_lote_sin_respuesta_no_para_los_demas(
    carpeta: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modulo, "CLAVES_POR_LOTE", 1)

    async def traductor(mensajes: list[dict[str, str]]) -> str:
        textos = json.loads(mensajes[1]["content"])
        if "Nuevo" in textos.values():
            raise TimeoutError
        return json.dumps({clave: texto for clave, texto in textos.items()})

    informe = await traducir("en-US", traductor)
    assert informe.traducidas == 2
    assert informe.sin_respuesta == 1
    # La siguiente ejecución solo pide la que faltó.
    assert (await traducir("en-US", None, simular=True)).pendientes == 1


async def test_el_catalogo_del_servidor_usa_el_texto_como_clave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import mensajes as catalogo
    from app.core.mensajes import extraer as extractor

    monkeypatch.setattr(catalogo, "CARPETA", tmp_path)
    monkeypatch.setattr(modulo, "FICHERO_HUELLAS", tmp_path / "huellas.json")
    monkeypatch.setattr(modulo, "FICHERO_GLOSARIO", tmp_path / "glosario.json")
    monkeypatch.setattr(
        extractor,
        "extraer",
        lambda: extractor.Extraccion(mensajes={"No existe {slug}.", "Hecho."}),
    )
    traducidos = {"No existe {slug}.": "There is no {slug}.", "Hecho.": "Done."}

    async def traductor(mensajes: list[dict[str, str]]) -> str:
        textos = json.loads(mensajes[1]["content"])
        assert "{nombre}" in mensajes[0]["content"]  # el contexto del servidor
        return json.dumps({clave: traducidos[texto] for clave, texto in textos.items()})

    informe = await modulo.traducir_servidor("en-US", traductor)
    assert informe.traducidas == 2
    assert json.loads((tmp_path / "en-US.json").read_text(encoding="utf-8")) == traducidos
