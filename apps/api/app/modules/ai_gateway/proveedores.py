"""Catálogo cerrado de proveedores y modelos de IA.

**Única fuente de verdad** de qué proveedores y qué modelos son válidos
(decisión #10 del `plan.md`, 2026-09-19). Lo consumen:

- el esquema de entrada (`schemas.py`), que publica la lista en el
  `openapi.json` para que el desplegable de la fase 3 no la reescriba;
- la validación del `PUT` de ambos niveles (`service.py`);
- el cliente de la fase 2, que traduce `(proveedor, modelo)` al `model` y al
  `api_base` que espera LiteLLM.

Ningún otro sitio puede declarar proveedores ni modelos: añadir uno es
añadir una entrada aquí.

**Ya no es la única validación de qué modelo se admite** (revierte la
decisión #10 original de "sin descubrimiento dinámico, no-objetivo del
PRD"): `service._validar_modelo_en_vivo` consulta primero el listado real
del proveedor (`descubrimiento.listar_modelos`, la misma llamada que
«Probar conexión» y el desplegable) y solo cae a esta lista fija cuando esa
consulta falla (proveedor caído, timeout…) — un catálogo anotado a mano se
queda corto en cuanto el proveedor saca un modelo nuevo (hallazgo del
usuario: `gemma4` es un modelo real de `nan_builders`, con visión, que este
fichero no tenía anotado). Esta lista sigue siendo la fuente de verdad para
el enrutado a LiteLLM (`prefijo_litellm`) y el respaldo del desplegable/
validación cuando el proveedor no responde. Cada modelo listado aquí sigue
anotado a mano desde la documentación del proveedor, incluida su **marca de
visión** (`vision`), que `accounting_ocr` necesita para no enviar una
factura rasterizada a un modelo que no acepta imágenes.

La marca de visión es **conservadora**: `False` en toda entrada cuyo
`capabilities.vision` no se haya verificado contra la fuente del proveedor.
Un `False` de más solo impide usar ese modelo para OCR; un `True` de más
provoca un fallo en la llamada real, que es peor.

`api_base`: en `nan_builders` y `cheaper_inference` es una **constante de
este fichero**, nunca un campo que escriba el usuario — así un cambio de
base URL del proveedor se hace en un sitio y no obliga a migrar filas, y
ninguno de los dos abre superficie SSRF. `custom` es el **único** proveedor
con `api_base` introducido por el usuario, y por eso el único que pasa por
`validacion.validar_api_base`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Modelo:
    """Un modelo del catálogo de un proveedor.

    `clave` es el identificador tal cual lo espera el proveedor (sin el
    prefijo de LiteLLM, que lo pone `prefijo_litellm` del proveedor).
    """

    clave: str
    etiqueta: str
    #: `capabilities.vision` del proveedor. Conservador: ver el docstring del módulo.
    vision: bool = False


@dataclass(frozen=True, slots=True)
class Proveedor:
    """Una entrada del catálogo cerrado."""

    clave: str
    etiqueta: str
    #: Prefijo con el que LiteLLM enruta el modelo (`openai/<modelo>`, …).
    prefijo_litellm: str
    #: Base URL fija del proveedor, o `None` si LiteLLM ya conoce la suya.
    api_base_fijo: str | None
    #: `True` solo en `custom`: el `api_base` lo escribe quien configura.
    api_base_editable: bool
    modelos: tuple[Modelo, ...]
    #: `True` si el modelo lo escribe quien configura en vez de elegirlo del
    #: catálogo. Solo `custom`: su endpoint es arbitrario, así que no existe
    #: ninguna lista de modelos que podamos cerrar sin dejarlo inservible.
    modelos_abiertos: bool = False
    #: `False` si LiteLLM no conoce los precios del proveedor (los dos
    #: gateways y `custom`): el gasto no es auditable sin precio declarado.
    #: Lo consume la fase 2; aquí se declara para no duplicar el catálogo.
    coste_auditable: bool = True

    def acepta_modelo(self, modelo: str) -> bool:
        if self.modelos_abiertos:
            return bool(modelo.strip())
        return any(entrada.clave == modelo for entrada in self.modelos)

    def modelo(self, clave: str) -> Modelo | None:
        for entrada in self.modelos:
            if entrada.clave == clave:
                return entrada
        return None


#: Catálogo cerrado. El orden es el del desplegable de la fase 3: primero los
#: tres proveedores que se implementan y prueban de verdad (decisión #10).
PROVEEDORES: dict[str, Proveedor] = {
    # NaN (`nan.builders`), API OpenAI-compatible; clave `sk-…`. Verificado
    # contra <https://nan.builders/docs/getting-started> (2026-09-19). La
    # clave del enum es `nan_builders`, no `nan`: el literal `nan` se
    # coerciona a *Not-a-Number* en YAML 1.1, pandas y exportaciones CSV, y
    # esta cadena viaja a `ai_usage_records.provider` y a las exportaciones
    # de contabilidad (decisión #11).
    "nan_builders": Proveedor(
        clave="nan_builders",
        etiqueta="NaN (nan.builders)",
        prefijo_litellm="openai",
        api_base_fijo="https://api.nan.builders/v1",
        api_base_editable=False,
        coste_auditable=False,
        modelos=(
            Modelo(clave="deepseek-v4-flash", etiqueta="DeepSeek v4 Flash"),
            Modelo(clave="glm5.3", etiqueta="GLM 5.3"),
            # Con visión: confirmado por el usuario (2026-09-22), no
            # verificado contra documentación propia — nan.builders no
            # publica `capabilities.vision` en su listado de modelos (API
            # OpenAI-compatible genérica), así que `descubrimiento.py` no
            # puede resolverlo solo y cae aquí, la anotación manual.
            Modelo(clave="gemma4", etiqueta="Gemma 4", vision=True),
        ),
    ),
    # OpenRouter: el único de los tres con precios en el mapa de LiteLLM, y
    # por tanto con control de gasto fiable de serie.
    "openrouter": Proveedor(
        clave="openrouter",
        etiqueta="OpenRouter",
        prefijo_litellm="openrouter",
        api_base_fijo=None,
        api_base_editable=False,
        modelos=(
            Modelo(clave="openai/gpt-4o", etiqueta="GPT-4o (OpenRouter)", vision=True),
            Modelo(clave="openai/gpt-4o-mini", etiqueta="GPT-4o mini (OpenRouter)", vision=True),
            Modelo(
                clave="anthropic/claude-3.5-sonnet",
                etiqueta="Claude 3.5 Sonnet (OpenRouter)",
                vision=True,
            ),
            Modelo(
                clave="google/gemini-2.0-flash-001",
                etiqueta="Gemini 2.0 Flash (OpenRouter)",
                vision=True,
            ),
        ),
    ),
    # CheaperInference: gateway OpenAI-compatible, clave `ci_live_…`.
    # Verificado contra <https://platform.cheaperinference.com/docs>
    # (2026-09-19). Solo se usa su interfaz OpenAI-compatible, nunca la
    # Anthropic-compatible que también expone (decisión #13). Los modelos
    # salen de los ejemplos de su documentación; su `capabilities.vision`
    # **no** está verificado, así que van todos con `vision=False` hasta
    # comprobarlo contra `GET /v1/models`.
    "cheaper_inference": Proveedor(
        clave="cheaper_inference",
        etiqueta="CheaperInference",
        prefijo_litellm="openai",
        api_base_fijo="https://api.cheaperinference.com/v1",
        api_base_editable=False,
        coste_auditable=False,
        modelos=(
            Modelo(clave="claude-opus-4.6", etiqueta="Claude Opus 4.6"),
            Modelo(clave="gpt-5.4", etiqueta="GPT-5.4"),
            Modelo(clave="gpt-5.5-pro", etiqueta="GPT-5.5 Pro"),
            Modelo(clave="gemini-3.7-flash", etiqueta="Gemini 3.7 Flash"),
        ),
    ),
    # Los cuatro siguientes salen gratis con LiteLLM y el usuario puede
    # quererlos, pero no llevan prueba de extremo a extremo en esta entrega.
    "anthropic": Proveedor(
        clave="anthropic",
        etiqueta="Anthropic",
        prefijo_litellm="anthropic",
        api_base_fijo=None,
        api_base_editable=False,
        modelos=(
            Modelo(clave="claude-opus-5", etiqueta="Claude Opus 5", vision=True),
            Modelo(clave="claude-sonnet-5", etiqueta="Claude Sonnet 5", vision=True),
            Modelo(clave="claude-haiku-4-5-20251001", etiqueta="Claude Haiku 4.5", vision=True),
        ),
    ),
    "openai": Proveedor(
        clave="openai",
        etiqueta="OpenAI",
        prefijo_litellm="openai",
        api_base_fijo=None,
        api_base_editable=False,
        modelos=(
            Modelo(clave="gpt-4o", etiqueta="GPT-4o", vision=True),
            Modelo(clave="gpt-4o-mini", etiqueta="GPT-4o mini", vision=True),
        ),
    ),
    "gemini": Proveedor(
        clave="gemini",
        etiqueta="Google Gemini",
        prefijo_litellm="gemini",
        api_base_fijo=None,
        api_base_editable=False,
        modelos=(
            Modelo(clave="gemini-1.5-pro", etiqueta="Gemini 1.5 Pro", vision=True),
            Modelo(clave="gemini-2.0-flash", etiqueta="Gemini 2.0 Flash", vision=True),
        ),
    ),
    # Único proveedor con `api_base` del usuario, y por tanto el único que
    # pasa por la validación SSRF. Su modelo también lo escribe el usuario:
    # el endpoint es suyo y no hay ninguna lista que podamos cerrar sin
    # dejar el proveedor inservible.
    "custom": Proveedor(
        clave="custom",
        etiqueta="Endpoint personalizado (OpenAI-compatible)",
        prefijo_litellm="openai",
        api_base_fijo=None,
        api_base_editable=True,
        coste_auditable=False,
        modelos=(),
        modelos_abiertos=True,
    ),
}

#: Claves válidas, en el orden del catálogo. Lo publica el `openapi.json`.
CLAVES_DE_PROVEEDOR: tuple[str, ...] = tuple(PROVEEDORES)

#: Longitud máxima de `provider`/`default_model` en base de datos. Vive aquí
#: para que el esquema y el modelo no la declaren por separado.
LONGITUD_PROVEEDOR = 40
LONGITUD_MODELO = 120


def obtener(clave: str) -> Proveedor | None:
    """El proveedor del catálogo, o `None` si la clave no existe."""
    return PROVEEDORES.get(clave)


def api_base_efectivo(clave: str, api_base_guardado: str | None) -> str | None:
    """Base URL con la que se llamará de verdad al proveedor.

    Para `nan_builders`/`cheaper_inference` es la constante del catálogo
    aunque la columna de la fila esté a `NULL` (que es como se guarda); para
    `custom` es la que se guardó; para el resto, `None` (la pone LiteLLM).
    """
    proveedor = PROVEEDORES.get(clave)
    if proveedor is None:
        return None
    if proveedor.api_base_fijo is not None:
        return proveedor.api_base_fijo
    return api_base_guardado if proveedor.api_base_editable else None
