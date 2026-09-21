"""Piezas puras del OCR de justificantes: rasterización, parseo y validación.

Nada de esto toca la red ni una clave real: la rasterización es local y el
parseo recibe el texto que habría devuelto el modelo. Los tests de integración
(borrador, cola, confirmación) viven en `test_accounting_ocr_drafts.py`.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from app.modules.accounting import drafts_service, ocr_client, rasterizacion
from app.shared.errors import ValidationDomainError

CONTENIDO_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d"
    b"\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def pdf_de_prueba(paginas: int = 1) -> bytes:
    """PDF real generado con la misma librería que lo rasteriza."""
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument.new()
    for _ in range(paginas):
        documento.new_page(400, 600)
    buffer = io.BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def imagen_de_prueba(ancho: int, alto: int, *, formato: str = "PNG") -> bytes:
    """Imagen real del tamaño pedido, para comprobar el reescalado."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=(200, 30, 30)).save(buffer, format=formato)
    return buffer.getvalue()


def _dimensiones(contenido: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(contenido)) as imagen:
        return imagen.width, imagen.height


def _respuesta(campos: dict[str, object], confianza: dict[str, object]) -> str:
    return json.dumps({"campos": campos, "confianza": confianza})


def _campos_completos() -> dict[str, object]:
    return {
        "provider_name": "Catering Paco",
        "expense_date": "2026-09-01",
        "base": "100.00",
        "vat": "21.00",
        "total": "121.00",
        "currency": "EUR",
    }


def _confianza_alta() -> dict[str, object]:
    return dict.fromkeys(ocr_client.CAMPOS, "alta")


# --- Rasterización -----------------------------------------------------------


def test_pdf_con_mas_paginas_que_el_limite_se_trunca() -> None:
    imagenes = rasterizacion.preparar_para_ocr(
        pdf_de_prueba(paginas=5), "application/pdf", max_paginas=2, ancho_maximo_px=800
    )
    assert len(imagenes) == 2
    assert all(imagen.mime == "image/png" for imagen in imagenes)
    assert all(imagen.contenido.startswith(b"\x89PNG") for imagen in imagenes)


def test_pdf_malformado_no_revienta_el_worker() -> None:
    """Un PDF roto tiene que salir como error de dominio, no como una
    excepción de PDFium que tumbe la tarea."""
    with pytest.raises(rasterizacion.DocumentoIlegible):
        rasterizacion.preparar_para_ocr(
            b"%PDF-1.4\nesto no es un pdf\n", "application/pdf", max_paginas=3, ancho_maximo_px=800
        )


def test_una_imagen_que_ya_cabe_pasa_tal_cual_sin_recodificar() -> None:
    imagenes = rasterizacion.preparar_para_ocr(
        CONTENIDO_PNG, "image/png", max_paginas=3, ancho_maximo_px=800
    )
    assert len(imagenes) == 1
    assert imagenes[0].contenido == CONTENIDO_PNG


@pytest.mark.parametrize(
    ("formato", "mime"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_una_imagen_mas_ancha_que_el_limite_se_reescala(formato: str, mime: str) -> None:
    """Una foto del móvil no puede viajar al modelo con sus megapíxeles
    enteros solo por no ser un PDF: el mismo ancho máximo vale para las dos
    ramas."""
    original = imagen_de_prueba(2400, 1200, formato=formato)

    imagenes = rasterizacion.preparar_para_ocr(original, mime, max_paginas=3, ancho_maximo_px=800)

    assert len(imagenes) == 1
    assert imagenes[0].mime == mime
    assert _dimensiones(imagenes[0].contenido) == (800, 400)
    assert len(imagenes[0].contenido) < len(original)


def test_una_imagen_ilegible_no_revienta_el_worker() -> None:
    """Bytes que `validate_upload` aceptó por su cabecera pero que Pillow no
    puede abrir: error de dominio, nunca una excepción suelta."""
    with pytest.raises(rasterizacion.DocumentoIlegible):
        rasterizacion.preparar_para_ocr(
            CONTENIDO_PNG[:20] + b"basura", "image/png", max_paginas=3, ancho_maximo_px=1
        )


def test_el_adaptador_solo_recibe_imagenes() -> None:
    """Garantía por diseño de que ningún PDF sale hacia un proveedor: los
    mensajes se arman a partir de `ImagenParaOcr`, y el único camino que los
    produce a partir de un PDF es la rasterización."""
    imagenes = rasterizacion.preparar_para_ocr(
        pdf_de_prueba(), "application/pdf", max_paginas=1, ancho_maximo_px=800
    )
    mensajes = ocr_client.construir_mensajes(imagenes)
    partes = mensajes[-1]["content"]
    urls = [parte["image_url"]["url"] for parte in partes if parte["type"] == "image_url"]
    assert urls and all(url.startswith("data:image/png;base64,") for url in urls)
    assert not any("application/pdf" in url for url in urls)


# --- Normalización de la confianza -------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("alta", "alta"),
        ("ALTA", "alta"),
        ("media", "media"),
        ("baja", "baja"),
        ("high", "alta"),
        ("low", "baja"),
        (0.95, "alta"),
        (0.6, "media"),
        (0.2, "baja"),
        ("87%", "alta"),
        (None, "baja"),
        ("lo que sea", "baja"),
        (True, "baja"),
    ],
)
def test_la_confianza_se_normaliza_a_tres_niveles(entrada: object, esperado: str) -> None:
    assert ocr_client.normalizar_confianza(entrada) == esperado


def test_la_confianza_nunca_es_un_porcentaje() -> None:
    campos, confianza = ocr_client.parsear_respuesta(
        _respuesta(_campos_completos(), dict.fromkeys(ocr_client.CAMPOS, 0.93))
    )
    assert set(confianza.values()) <= set(ocr_client.NIVELES_DE_CONFIANZA)
    assert campos["total_cents"] == 12_100


# --- Parseo de la respuesta ---------------------------------------------------


def test_respuesta_fuera_de_esquema_se_rechaza_entera() -> None:
    for contenido in ("no soy json", "[]", json.dumps({"campos": {}}), json.dumps({"otra": 1})):
        with pytest.raises(ocr_client.RespuestaFueraDeEsquema):
            ocr_client.parsear_respuesta(contenido)


def test_un_campo_con_confianza_baja_llega_en_blanco() -> None:
    confianza = _confianza_alta() | {"total": "baja"}
    campos, niveles = ocr_client.parsear_respuesta(_respuesta(_campos_completos(), confianza))
    assert campos["total_cents"] is None
    assert niveles["total_cents"] == "baja"
    assert campos["base_cents"] == 10_000


def test_un_importe_ilegible_llega_en_blanco_y_con_confianza_baja() -> None:
    campos_crudos = _campos_completos() | {"total": "no se lee"}
    campos, niveles = ocr_client.parsear_respuesta(_respuesta(campos_crudos, _confianza_alta()))
    assert campos["total_cents"] is None
    assert niveles["total_cents"] == "baja"


def test_importe_en_formato_espanol_se_convierte_a_centimos() -> None:
    campos_crudos = _campos_completos() | {"total": "1.234,56"}
    campos, _ = ocr_client.parsear_respuesta(_respuesta(campos_crudos, _confianza_alta()))
    assert campos["total_cents"] == 123_456


def test_un_importe_negativo_o_desorbitado_no_llega_al_borrador() -> None:
    campos_crudos = _campos_completos() | {"base": "-10.00", "vat": "99999999999"}
    campos, _ = ocr_client.parsear_respuesta(_respuesta(campos_crudos, _confianza_alta()))
    assert campos["base_cents"] is None
    assert campos["vat_cents"] is None


def test_el_texto_extraido_se_recorta() -> None:
    campos_crudos = _campos_completos() | {"provider_name": "x" * 500}
    campos, _ = ocr_client.parsear_respuesta(_respuesta(campos_crudos, _confianza_alta()))
    assert campos["provider_name"] is not None
    assert len(campos["provider_name"]) == 200


# --- Validación de importes al confirmar --------------------------------------


def test_validar_importes_acepta_el_caso_correcto_y_el_exento() -> None:
    drafts_service.validar_importes(
        base_cents=10_000, vat_cents=2_100, total_cents=12_100, confirmar_importe_alto=False
    )
    drafts_service.validar_importes(
        base_cents=10_000, vat_cents=None, total_cents=10_000, confirmar_importe_alto=False
    )


def test_validar_importes_rechaza_negativos_y_descuadres() -> None:
    with pytest.raises(ValidationDomainError):
        drafts_service.validar_importes(
            base_cents=-1, vat_cents=0, total_cents=-1, confirmar_importe_alto=False
        )
    with pytest.raises(ValidationDomainError):
        drafts_service.validar_importes(
            base_cents=10_000, vat_cents=2_100, total_cents=10_000, confirmar_importe_alto=False
        )
    with pytest.raises(ValidationDomainError):
        # Un `total=0` inyectado desde el documento no cuadra y se rechaza.
        drafts_service.validar_importes(
            base_cents=10_000, vat_cents=None, total_cents=0, confirmar_importe_alto=False
        )


def test_un_importe_por_encima_del_techo_exige_confirmacion_explicita() -> None:
    from app.core.config import get_settings

    techo = get_settings().accounting_expense_confirmation_ceiling_cents
    with pytest.raises(ValidationDomainError):
        drafts_service.validar_importes(
            base_cents=techo + 1,
            vat_cents=None,
            total_cents=techo + 1,
            confirmar_importe_alto=False,
        )
    drafts_service.validar_importes(
        base_cents=techo + 1, vat_cents=None, total_cents=techo + 1, confirmar_importe_alto=True
    )


# --- Regresión estructural ----------------------------------------------------

_MODULO = Path(__file__).resolve().parents[1] / "app" / "modules" / "accounting"


def _codigo_sin_comentarios(fichero: Path) -> str:
    """Fuente sin comentarios ni cadenas de documentación.

    Los comentarios del adaptador sí nombran a LiteLLM y a la pasarela para
    explicar precisamente que **no** los usa; lo que no puede aparecer es en
    el código."""
    import io as _io
    import tokenize

    with fichero.open("rb") as flujo:
        tokens = list(tokenize.tokenize(_io.BytesIO(flujo.read()).readline))
    return " ".join(
        token.string
        for token in tokens
        if token.type not in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE)
    )


def test_el_adaptador_no_conoce_ningun_proveedor() -> None:
    """Criterio de éxito de la fase: `ocr_client.py` solo conoce la interfaz de
    la pasarela. Si mañana alguien mete aquí un SDK de proveedor, este test lo
    para."""
    import ast

    fichero = _MODULO / "ocr_client.py"
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    importados: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.append(nodo.module)
    assert not any("litellm" in modulo for modulo in importados), importados

    codigo = _codigo_sin_comentarios(fichero).lower()
    for proveedor in (
        "litellm",
        "openai",
        "anthropic",
        "openrouter",
        "gemini",
        "nan_builders",
        "cheaper_inference",
    ):
        assert proveedor not in codigo, proveedor


def test_confirmar_draft_solo_se_llama_desde_su_endpoint() -> None:
    """Un gasto por OCR solo nace del endpoint de confirmación, con una
    persona detrás: ninguna otra ruta del backend puede invocarlo."""
    llamadas = [
        fichero.name
        for fichero in _MODULO.parent.rglob("*.py")
        if "confirmar_draft(" in fichero.read_text(encoding="utf-8")
    ]
    assert sorted(llamadas) == ["drafts_router.py", "drafts_service.py"]


def test_ningun_fichero_del_modulo_supera_las_mil_lineas() -> None:
    for fichero in _MODULO.glob("*.py"):
        lineas = len(fichero.read_text(encoding="utf-8").splitlines())
        assert lineas <= 1000, f"{fichero.name} tiene {lineas} líneas"
