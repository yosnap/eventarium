"""Cifrado en reposo de las claves de proveedor de IA.

Único punto del proyecto que toca el texto plano de una clave de proveedor.
Fernet (AES-128-CBC + HMAC-SHA256, con marca de tiempo) de `cryptography`:
autenticado, con formato estable y sin parámetros que elegir mal.

La clave simétrica es `AI_SETTINGS_ENCRYPTION_KEY`, que vive **fuera** de la
base de datos (variables de entorno) y se valida **al arrancar**
(`core/config.py`), no en el primer `PUT`. Vacía por defecto: una instalación
que no usa IA arranca igual y solo falla al intentar guardar una clave, con
`CifradoNoConfigurado`.

Riesgo aceptado y documentado (hallazgo #2 de la sesión 1 de red-team): es
una única clave de aplicación, como `jwt_secret`; si se filtra, descifra las
credenciales de todas las organizaciones. No se diseña cifrado por sobre
(envelope) por organización en esta entrega. **Rotarla exige re-cifrar todas
las filas**: procedimiento en `app/cli.py rotate-ai-encryption-key`.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.modules.ai_gateway.errores import CifradoNoConfigurado, CredencialIlegible

#: Cuántos caracteres finales de la clave se muestran como pista. Cuatro es
#: lo justo para reconocer «cuál de mis claves es esta» sin acercarse a
#: revelarla.
LONGITUD_DE_PISTA = 4


def cifrado_disponible() -> bool:
    """`True` si la instalación tiene clave de cifrado configurada."""
    return bool(get_settings().ai_settings_encryption_key)


def _fernet(clave: str | None = None) -> Fernet:
    """Instancia de Fernet con la clave indicada o la de la instalación.

    No se memoiza a propósito: `get_settings()` ya está cacheado y construir
    un `Fernet` es barato; memoizarlo aquí dejaría una clave viva en memoria
    después de rotarla.
    """
    material = clave if clave is not None else get_settings().ai_settings_encryption_key
    if not material:
        raise CifradoNoConfigurado()
    try:
        return Fernet(material.encode("utf-8"))
    except (ValueError, TypeError) as error:
        # No debería ocurrir: el validador de arranque ya rechaza un formato
        # inválido. Se traduce igualmente a error de dominio para que una
        # rotación mal hecha no salga como 500.
        raise CifradoNoConfigurado(
            "AI_SETTINGS_ENCRYPTION_KEY no es una clave Fernet válida."
        ) from error


def cifrar_clave(clave_en_claro: str, *, clave_de_cifrado: str | None = None) -> str:
    """Devuelve el texto cifrado que se guarda en la columna `api_key_encrypted`."""
    if not clave_en_claro:
        raise CifradoNoConfigurado("No hay ninguna clave que cifrar.")
    return _fernet(clave_de_cifrado).encrypt(clave_en_claro.encode("utf-8")).decode("ascii")


def descifrar_clave(texto_cifrado: str, *, clave_de_cifrado: str | None = None) -> str:
    """Texto plano de una clave guardada.

    Lanza `CredencialIlegible` si el token no descifra (clave de cifrado
    rotada sin re-cifrar, fila manipulada o copiada de otra instalación).
    **Ningún endpoint llama a esta función**: solo el cliente de la fase 2, y
    el valor no sale nunca de él.
    """
    try:
        return _fernet(clave_de_cifrado).decrypt(texto_cifrado.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as error:
        raise CredencialIlegible() from error


def pista_de_clave(clave_en_claro: str) -> str:
    """Los últimos caracteres de la clave, para reconocerla sin revelarla.

    Una clave más corta que la pista no deja pista (cadena vacía) en vez de
    devolverse entera: el caso solo se da con una clave inválida, y devolverla
    sería justo lo que esta función existe para evitar.
    """
    if len(clave_en_claro) <= LONGITUD_DE_PISTA:
        return ""
    return clave_en_claro[-LONGITUD_DE_PISTA:]
