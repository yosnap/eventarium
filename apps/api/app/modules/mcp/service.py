"""Conexiones MCP: claves de API, listado y revocación.

La clave (`evtm_` + 32 bytes aleatorios) se enseña una sola vez; en base de
datos solo queda su SHA-256. Con 256 bits de entropía no hace falta sal ni
pimienta: no hay diccionario contra el que probar (mismo criterio que los
tokens de acceso personales de GitHub).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_redaction import redactar_importes
from app.core.database import maintenance_session
from app.core.permissions import Permission
from app.modules.events.models import Event
from app.modules.mcp.models import McpConnection
from app.modules.mcp.scopes import PERMISO_REQUERIDO, Ambito
from app.modules.users.models import User
from app.shared.errors import NotFoundError, PermissionDeniedError, ValidationDomainError

PREFIJO_CLAVE = "evtm_"
DIAS_POR_DEFECTO = 90
DIAS_MAXIMOS = 365


def huella(clave: str) -> str:
    return hashlib.sha256(clave.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ClaveCreada:
    conexion: McpConnection
    clave: str


async def permisos_en_organizacion(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> set[Permission]:
    """Permisos actuales de la persona en la organización (sus roles, hoy)."""
    filas = await session.execute(
        text(
            "SELECT DISTINCT rp.permission "
            "FROM organization_members m "
            "JOIN role_permissions rp ON rp.role_id = m.role_id "
            "WHERE m.user_id = :user_id AND m.organization_id = :org_id"
        ),
        {"user_id": user_id, "org_id": organization_id},
    )
    permisos: set[Permission] = set()
    for (valor,) in filas:
        try:
            permisos.add(Permission(valor))
        except ValueError:
            continue
    return permisos


async def _validar_ambitos(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, ambitos: list[str]
) -> list[str]:
    if not ambitos:
        raise ValidationDomainError("Elige al menos un permiso para la conexión.")
    permisos = await permisos_en_organizacion(session, organization_id, user_id)
    resultado: list[str] = []
    for valor in dict.fromkeys(ambitos):
        try:
            ambito = Ambito(valor)
        except ValueError as exc:
            raise ValidationDomainError(f"Permiso desconocido: {valor}.") from exc
        if PERMISO_REQUERIDO[ambito] not in permisos:
            # No se puede conceder a un asistente lo que la propia persona no
            # puede hacer en la web.
            raise PermissionDeniedError(
                f"Tu rol no te permite conceder «{ambito.value}» a una conexión."
            )
        resultado.append(ambito.value)
    return resultado


async def _validar_eventos(
    session: AsyncSession, organization_id: uuid.UUID, event_ids: list[uuid.UUID] | None
) -> list[uuid.UUID] | None:
    if event_ids is None:
        return None
    unicos = list(dict.fromkeys(event_ids))
    if not unicos:
        raise ValidationDomainError("Elige al menos un evento o deja la conexión para todos.")
    existentes = set(
        await session.scalars(
            select(Event.id).where(Event.organization_id == organization_id, Event.id.in_(unicos))
        )
    )
    if existentes != set(unicos):
        raise ValidationDomainError("Alguno de los eventos indicados no existe.")
    return unicos


async def crear_clave(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    nombre: str,
    ambitos: list[str],
    event_ids: list[uuid.UUID] | None,
    dias: int = DIAS_POR_DEFECTO,
) -> ClaveCreada:
    if not 1 <= dias <= DIAS_MAXIMOS:
        raise ValidationDomainError(f"La caducidad debe estar entre 1 y {DIAS_MAXIMOS} días.")
    concedidos = await _validar_ambitos(session, organization_id, user_id, ambitos)
    eventos = await _validar_eventos(session, organization_id, event_ids)
    clave = PREFIJO_CLAVE + secrets.token_urlsafe(32)
    conexion = McpConnection(
        organization_id=organization_id,
        user_id=user_id,
        name=nombre.strip(),
        method="api_key",
        scopes=concedidos,
        event_ids=eventos,
        key_prefix=clave[:12],
        key_hash=huella(clave),
        expires_at=datetime.now(UTC) + timedelta(days=dias),
    )
    session.add(conexion)
    await session.flush()
    return ClaveCreada(conexion=conexion, clave=clave)


async def listar_de_persona(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[McpConnection]:
    return list(
        await session.scalars(
            select(McpConnection)
            .where(
                McpConnection.organization_id == organization_id,
                McpConnection.user_id == user_id,
            )
            .order_by(McpConnection.created_at.desc())
        )
    )


async def revocar(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    solo_propia: bool,
) -> McpConnection:
    conexion = await session.scalar(
        select(McpConnection).where(
            McpConnection.organization_id == organization_id, McpConnection.id == connection_id
        )
    )
    if conexion is None or (solo_propia and conexion.user_id != actor_user_id):
        raise NotFoundError("La conexión no existe.")
    if conexion.revoked_at is None:
        conexion.revoked_at = datetime.now(UTC)
        conexion.revoked_by = actor_user_id
        await session.flush()
    return conexion


async def revocar_todas_de_persona(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Cambio o restablecimiento de contraseña, o cuenta desactivada: revoca
    sus conexiones en todas sus organizaciones. Función `SECURITY DEFINER`
    porque se llama desde sesiones sin organización activa."""
    revocadas = await session.scalar(
        text("SELECT app_revoke_mcp_connections_of_user(:user_id)"), {"user_id": user_id}
    )
    return int(revocadas or 0)


async def registrar_uso(session: AsyncSession, connection_id: uuid.UUID) -> None:
    """`last_used_at` como mucho una vez por minuto: no escribir en cada llamada."""
    ahora = datetime.now(UTC)
    await session.execute(
        update(McpConnection)
        .where(
            McpConnection.id == connection_id,
            (McpConnection.last_used_at.is_(None))
            | (McpConnection.last_used_at < ahora - timedelta(minutes=1)),
        )
        .values(last_used_at=ahora)
    )


async def listar_de_organizacion(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> list[tuple[McpConnection, str]]:
    """Para el dueño: todas las conexiones de la organización con el correo
    de su persona."""
    filas = await session.execute(
        select(McpConnection, User.email)
        .join(User, User.id == McpConnection.user_id)
        .where(McpConnection.organization_id == organization_id)
        .order_by(McpConnection.created_at.desc())
    )
    return [(conexion, email) for conexion, email in filas.all()]


async def historial(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    solo_de: uuid.UUID | None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Últimas acciones de una conexión, desde la auditoría.

    `audit_log` no tiene RLS y solo la lee `app_maintainer`, así que primero se
    comprueba **bajo RLS** que la conexión es de esta organización (y de la
    persona, si `solo_de`): así nunca se consulta la auditoría con un
    identificador de otra organización. Solo se devuelven unos pocos campos,
    con los importes redactados.
    """
    consulta = select(McpConnection.id).where(
        McpConnection.organization_id == organization_id, McpConnection.id == connection_id
    )
    if solo_de is not None:
        consulta = consulta.where(McpConnection.user_id == solo_de)
    if await session.scalar(consulta) is None:
        raise NotFoundError("La conexión no existe.")
    async with maintenance_session() as auditoria:
        filas = await auditoria.execute(
            text(
                "SELECT action, entity_type, entity_id, created_at, detail FROM audit_log "
                "WHERE organization_id = :org AND detail->>'connection_id' = :cid "
                "ORDER BY created_at DESC LIMIT :limite"
            ),
            {"org": organization_id, "cid": str(connection_id), "limite": limite},
        )
        return [
            {
                "action": fila.action,
                "entity_type": fila.entity_type,
                "entity_id": fila.entity_id,
                "created_at": fila.created_at,
                "detail": redactar_importes(
                    {k: v for k, v in (fila.detail or {}).items() if k != "connection_id"}
                ),
            }
            for fila in filas
        ]
