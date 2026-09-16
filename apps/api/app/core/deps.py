"""Dependencias transversales de FastAPI.

Cadena de una petición autenticada (`DbDep`/`CurrentUserDep`):

    get_session → get_db_organizacion_activa → get_current_user → require_permission

La organización activa viene siempre del propio token (claim `org`), nunca del
`Host`: las organizaciones no tienen dominio propio. No queda ninguna
dependencia que resuelva por host (fase 6 del plan de organización sin
dominio: los últimos consumidores genuinamente públicos que quedaban —
`GET /tenant/branding`, `GET /public/events`, `POST /public/cookie-consent`
— dejaron de necesitarlo).

`get_db_organizacion_activa` es el único punto donde se fija el contexto de
RLS a partir de una sesión autenticada. Ningún router abre sesiones por su
cuenta ni usa el motor de mantenimiento.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionApp, SessionMaintenance, set_organization_context
from app.core.permissions import Permission
from app.core.security import AccessTokenClaims, decode_access_token
from app.shared.errors import (
    AuthenticationError,
    PermissionDeniedError,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Sesión con el rol de la API y una transacción abierta, sin contexto todavía."""
    async with SessionApp() as session:
        async with session.begin():
            yield session


#: Sesión sin ningún contexto de RLS fijado, para lo que no necesita ninguno:
#: funciones `SECURITY DEFINER` de alcance mínimo (login, registro, verificación
#: de correo, recuperación de contraseña, autoservicio de creación de
#: organizaciones) que resuelven su propia visibilidad sin depender del `Host`
#: ni de una organización activa.
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_db_organizacion_activa(
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncSession:
    """Sesión con el contexto RLS de la organización activa de la sesión (JWT).

    La organización activa es la que lleva el propio access token (claim
    `org`), cambiable sin volver a loguearse vía
    `POST /auth/switch-organization` — sin dominio por organización, no hay
    ningún host que pudiera decirlo.
    """
    await set_organization_context(session, claims.organization_id, claims.user_id)
    return session


async def get_maintenance_db() -> AsyncIterator[AsyncSession]:
    """Sesión con el rol `app_maintainer` (BYPASSRLS).

    Solo puede usarla `app.modules.admin`. La regla se verifica en CI con un test
    estático que falla si esta dependencia aparece en cualquier otro módulo.
    """
    async with SessionMaintenance() as session:
        async with session.begin():
            yield session


def _extraer_token(request: Request) -> str:
    cabecera = request.headers.get("authorization", "")
    esquema, _, token = cabecera.partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise AuthenticationError("Falta la cabecera Authorization: Bearer.")
    return token.strip()


async def get_token_claims(request: Request) -> AccessTokenClaims:
    """Contenido verificado del access token, sin tocar la base de datos.

    La única excepción es una sesión de impersonación: se comprueba contra
    Redis que siga viva. Un JWT no se puede invalidar por sí solo, así que sin
    esta consulta «salir de la suplantación» solo borraría el token del cliente
    y el token robado seguiría valiendo hasta su `exp`.
    """
    claims = decode_access_token(_extraer_token(request))
    if claims.impersonated_by is not None:
        from app.modules.admin import impersonation

        if not await impersonation.sesion_activa(claims.jti):
            raise AuthenticationError("La suplantación ha terminado.")
    return claims


class CurrentUser:
    """Usuario autenticado en el contexto de la organización de la petición."""

    __slots__ = (
        "id",
        "email",
        "first_name",
        "last_name",
        "is_superadmin",
        "organization_id",
        "refresh_family",
    )

    def __init__(
        self,
        *,
        id: uuid.UUID,
        email: str,
        first_name: str | None,
        last_name: str | None,
        is_superadmin: bool,
        organization_id: uuid.UUID,
        refresh_family: str | None = None,
    ) -> None:
        self.id = id
        self.email = email
        self.first_name = first_name
        self.last_name = last_name
        self.is_superadmin = is_superadmin
        self.organization_id = organization_id
        self.refresh_family = refresh_family


async def get_current_user(
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_db_organizacion_activa)],
) -> CurrentUser:
    """Carga el usuario del token en su organización activa.

    `session` ya llega con el contexto RLS fijado a la organización del propio
    token (`get_db_organizacion_activa`) — no hay ningún host contra el que
    comprobarla. Un token sin organización activa (cuenta recién verificada,
    sin crear ni unirse a ninguna todavía) no vale aquí: los endpoints
    organizativos siempre necesitan una: usa `VerifiedUserDep` para el
    autoservicio de creación de organizaciones, que no la necesita.
    """
    if claims.organization_id is None:
        raise PermissionDeniedError("Esta cuenta no tiene ninguna organización activa.")

    fila = (
        await session.execute(
            text(
                "SELECT id, email, first_name, last_name, is_superadmin, is_active "
                "FROM users WHERE id = :id"
            ),
            {"id": claims.user_id},
        )
    ).first()
    if fila is None or not fila[5]:
        raise AuthenticationError("El usuario ya no existe o está desactivado.")

    return CurrentUser(
        id=fila[0],
        email=fila[1],
        first_name=fila[2],
        last_name=fila[3],
        is_superadmin=fila[4],
        organization_id=claims.organization_id,
        refresh_family=claims.family,
    )


async def get_user_permissions(session: AsyncSession, usuario: CurrentUser) -> set[Permission]:
    """Permisos efectivos del usuario en la organización de la petición."""
    filas = await session.execute(
        text(
            "SELECT DISTINCT rp.permission "
            "FROM organization_members m "
            "JOIN role_permissions rp ON rp.role_id = m.role_id "
            "WHERE m.user_id = :user_id AND m.organization_id = :org_id"
        ),
        {"user_id": usuario.id, "org_id": usuario.organization_id},
    )
    permisos: set[Permission] = set()
    for (valor,) in filas:
        try:
            permisos.add(Permission(valor))
        except ValueError:
            # Un permiso retirado del catálogo se ignora en lugar de romper la sesión.
            continue
    return permisos


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
#: Sesión con el contexto RLS de la organización activa de la sesión
#: autenticada (el claim `org` del propio token). Ningún endpoint, público o
#: autenticado, depende ya del host de la petición.
DbDep = Annotated[AsyncSession, Depends(get_db_organizacion_activa)]


async def current_permissions(usuario: CurrentUserDep, session: DbDep) -> set[Permission]:
    """Dependencia con los permisos efectivos del usuario."""
    return await get_user_permissions(session, usuario)


PermissionsDep = Annotated[set[Permission], Depends(current_permissions)]

#: Métodos que una sesión de impersonación puede usar. Todo lo demás se rechaza:
#: la suplantación es de **solo lectura**, y esa garantía tiene que vivir en el
#: backend, no en el banner del cliente (una petición directa no lo pinta).
_METODOS_DE_LECTURA = frozenset({"GET", "HEAD", "OPTIONS"})


async def bloquear_escritura_si_impersona(request: Request) -> None:
    """Impide escribir durante una sesión de impersonación.

    Se aplica como dependencia **global** (ver `main.py`), no endpoint a
    endpoint: así cubre los ~120 endpoints de la API sin tocar ninguno y sin
    que un endpoint nuevo se quede fuera por olvido. Una suplantación sirve para
    ver lo que ve la persona suplantada, no para actuar en su nombre.

    Es deliberadamente **opcional** respecto al token: se aplica a rutas
    públicas (login, registro, webhooks) que no llevan `Authorization`. Sin
    token no hay sesión de suplantación, así que se deja pasar; la exigencia de
    autenticación es cosa de cada endpoint, no de esta dependencia.
    """
    cabecera = request.headers.get("authorization", "")
    _, _, token = cabecera.partition(" ")
    if not token:
        return

    try:
        claims = decode_access_token(token)
    except AuthenticationError:
        # Un token inválido lo rechazará la autenticación del endpoint con su
        # propio mensaje; aquí no se adelanta ese juicio.
        return

    if claims.impersonated_by is None:
        return

    if request.method.upper() in _METODOS_DE_LECTURA:
        return

    # Salir de la suplantación es un `POST`, y tiene que poder hacerse desde la
    # propia sesión de suplantación: sin esta excepción, la regla de solo
    # lectura encerraría al administrador dentro de la sesión hasta que
    # caducase. Es la única escritura permitida, y no toca datos de nadie.
    if request.url.path.endswith("/impersonate/stop"):
        return

    raise PermissionDeniedError(
        "Una sesión de suplantación solo puede consultar, no modificar.",
        extra={"metodo": request.method},
    )


def require_permission(*requeridos: Permission):  # type: ignore[no-untyped-def]
    """Exige que el usuario tenga **todos** los permisos indicados."""

    async def dependencia(permisos: PermissionsDep) -> set[Permission]:
        faltan = {p for p in requeridos if p not in permisos}
        if faltan:
            raise PermissionDeniedError(
                "No tienes permiso para esta operación.",
                extra={"required": sorted(p.value for p in faltan)},
            )
        return permisos

    return Depends(dependencia)


async def require_superadmin(
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_maintenance_db)],
) -> CurrentUser:
    """Superadmin de la instalación.

    Los endpoints de administración son globales, así que no exigen organización en
    el token. `is_superadmin` se comprueba **en base de datos** en cada petición: un
    token antiguo no puede conservar el privilegio si se revocó.

    Un token de **impersonación** se rechaza siempre, aunque el usuario suplantado
    sea superadmin en la base de datos: el claim `sa` no es la defensa (este gate
    lee `users`, no el claim), así que sin esta comprobación una sesión de
    suplantación sobre un superadmin pasaría los endpoints de administración —
    que son, precisamente, los que no debe poder usar.
    """
    if claims.impersonated_by is not None:
        raise PermissionDeniedError(
            "Una sesión de suplantación no puede usar los endpoints de administración."
        )

    fila = (
        await session.execute(
            text(
                "SELECT id, email, first_name, last_name, is_superadmin, is_active "
                "FROM users WHERE id = :id"
            ),
            {"id": claims.user_id},
        )
    ).first()
    if fila is None or not fila[5]:
        raise AuthenticationError("El usuario ya no existe o está desactivado.")
    if not fila[4]:
        raise PermissionDeniedError("Se requieren privilegios de superadministrador.")
    return CurrentUser(
        id=fila[0],
        email=fila[1],
        first_name=fila[2],
        last_name=fila[3],
        is_superadmin=True,
        organization_id=claims.organization_id or uuid.UUID(int=0),
    )


async def require_platform_staff(
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_maintenance_db)],
) -> CurrentUser:
    """Personal de plataforma: `superadmin` **o** el rol aditivo `soporte`.

    Aditiva sobre `require_superadmin`, nunca la sustituye: los endpoints de
    escritura sensible (desactivar un usuario, asignar/retirar un rol de
    plataforma) siguen exigiendo `require_superadmin` sin más, no esta
    dependencia. `soporte` solo alcanza lectura (directorio de
    usuarios/eventos) y suplantación.

    Mismas dos garantías que `require_superadmin`, por el mismo motivo —
    plan `260916-0810-usuarios-y-permisos-plataforma`, hallazgos S-1/S-2 del
    red-team de ese plan:

    - `is_superadmin`/`platform_role` se comprueban **en base de datos**, en
      cada petición, nunca desde un claim del JWT: un token antiguo no
      conserva el privilegio si se revocó, y retirar `soporte` a alguien
      tiene efecto en la siguiente petición, no al expirar el token.
    - Un token de **impersonación** se rechaza siempre, aunque la cuenta
      suplantada sea `superadmin` o `soporte` en la base de datos: sin esta
      comprobación, una sesión de suplantación pasaría estos endpoints, que
      son precisamente los que no debe poder usar.
    """
    if claims.impersonated_by is not None:
        raise PermissionDeniedError(
            "Una sesión de suplantación no puede usar los endpoints de administración."
        )

    fila = (
        await session.execute(
            text(
                "SELECT id, email, first_name, last_name, is_superadmin, is_active, "
                "platform_role FROM users WHERE id = :id"
            ),
            {"id": claims.user_id},
        )
    ).first()
    if fila is None or not fila[5]:
        raise AuthenticationError("El usuario ya no existe o está desactivado.")
    if not fila[4] and fila[6] != "soporte":
        raise PermissionDeniedError("Se requieren privilegios de personal de plataforma.")
    return CurrentUser(
        id=fila[0],
        email=fila[1],
        first_name=fila[2],
        last_name=fila[3],
        is_superadmin=fila[4],
        organization_id=claims.organization_id or uuid.UUID(int=0),
    )


class VerifiedUser:
    """Persona con el correo verificado, sin organización todavía.

    Distinto de `CurrentUser`: ese exige una organización activa en el token, algo
    que no tiene sentido para quien acaba de verificar su correo y aún no ha creado
    ni se ha unido a ninguna. Solo lo usa el autoservicio de creación de
    organizaciones.
    """

    __slots__ = ("id", "email")

    def __init__(self, *, id: uuid.UUID, email: str) -> None:
        self.id = id
        self.email = email


async def require_verified_user(
    claims: Annotated[AccessTokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> VerifiedUser:
    """Exige un token válido de una persona con el correo ya verificado.

    La visibilidad normal de `users` bajo RLS exige compartir organización con quien
    pregunta; por eso usa `app_find_user_by_id`, la misma función `SECURITY DEFINER`
    de alcance mínimo que el registro (fase 1) usa por correo. Sesión sin contexto
    (`get_session`, no `get_db_organizacion_activa`): esto no depende de
    ninguna organización ni de ningún host — lo usa el autoservicio de
    creación de organizaciones, antes de que exista ninguna que fijar como
    contexto.
    """
    fila = (
        await session.execute(
            text(
                "SELECT id, email, email_verified_at, is_active FROM app_find_user_by_id(:id)"
            ),
            {"id": claims.user_id},
        )
    ).first()
    if fila is None or not fila[3]:
        raise AuthenticationError("El usuario ya no existe o está desactivado.")
    if fila[2] is None:
        raise PermissionDeniedError("El correo todavía no está verificado.")
    return VerifiedUser(id=fila[0], email=fila[1])


VerifiedUserDep = Annotated[VerifiedUser, Depends(require_verified_user)]
