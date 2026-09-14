"""Modelos de la plataforma: identidad, dominios y páginas legales.

Las tres tablas son de **instalación** (sin `organization_id`, sin RLS de
organización): describen a la plataforma entera, no a un tenant. Eso no las
deja abiertas: `ALTER DEFAULT PRIVILEGES` (`infra/postgres/sql/roles.sql`)
concede DML completo a `app_user` sobre toda tabla nueva, así que la
migración les retira todo menos `SELECT` — una sesión de organización puede
leer la identidad para el endpoint público, pero no puede reescribir el logo
ni los textos legales que se sirven a toda la instalación. Solo
`app/modules/admin` escribe, con la sesión de mantenimiento (`app_maintainer`,
`BYPASSRLS`).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7

#: Claves válidas de `platform_legal_pages.kind`. Las cuatro páginas legales,
#: todas de plataforma: Eventarium es una SaaS centralizada (como Luma), así
#: que es ella quien fija sus condiciones frente a quien se inscribe a
#: cualquier evento, no cada organización por separado (decisión del usuario,
#: 2026-09-14, que sustituye el reparto anterior por organización).
PLATFORM_LEGAL_PAGE_KINDS: tuple[str, ...] = (
    "aviso-legal",
    "privacidad",
    "cookies",
    "condiciones-de-inscripcion",
)

#: Nombre por defecto al sembrar la identidad de plataforma.
NOMBRE_PLATAFORMA = "Eventarium"


class PlatformBranding(Base, TimestampMixin):
    """Identidad de la plataforma: exactamente **una** fila.

    La unicidad se garantiza en la base de datos con una clave primaria de
    valor fijo (`singleton`), no con lógica de aplicación: así un segundo
    `INSERT` choca con la PK en vez de crear una identidad duplicada que el
    endpoint público tendría que desambiguar.
    """

    __tablename__ = "platform_branding"

    #: PK de valor fijo (`'default'`): la tabla admite una sola fila por
    #: construcción, no por convención. El `id` UUID sobra aquí — hay una
    #: sola identidad de instalación y una PK textual la hace evidente.
    singleton: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    logo_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    favicon_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Plantilla del chrome de plataforma (fase 2). `NULL` = la marcada
    # `is_default` del catálogo `theme_templates`, misma convención que
    # `OrganizationBranding.theme_template_id`.
    theme_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("theme_templates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    social_links: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa_text("'[]'::jsonb")
    )


class PlatformDomain(Base, TimestampMixin):
    """Host que sirve la web de la plataforma.

    Es lo que distingue un host de plataforma de uno de organización:
    `resolve_host` consulta esta tabla **antes** que `organization_domains`.
    Las dos son excluyentes en la práctica — un host que estuviera en ambas se
    resolvería como plataforma, porque se comprueba primero; no se añade una
    constraint cruzada entre tablas por no complicar la migración por un caso
    que solo se produce editando a mano.
    """

    __tablename__ = "platform_domains"
    __table_args__ = (Index("uq_platform_domains_host", "host", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    host: Mapped[str] = mapped_column(String(255), nullable=False)


class PlatformLegalPage(Base, TimestampMixin):
    """Texto legal de la plataforma, por tipo de página.

    `content` nulo = plantilla por defecto de plataforma. No se siembra una
    fila por página: el resolutor cae a la plantilla cuando falta, así que
    una fila solo existe si el admin la ha editado.
    """

    __tablename__ = "platform_legal_pages"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('aviso-legal', 'privacidad', 'cookies', 'condiciones-de-inscripcion')",
            name="ck_platform_legal_pages_kind",
        ),
        Index("uq_platform_legal_pages_kind", "kind", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
