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
    # Nulos para logos/favicons subidos antes de la biblioteca de medios de
    # plataforma (sin backfill): siguen su ciclo de vida de siempre. FK
    # simple (no compuesta): `platform_media` no tiene `organization_id`
    # con el que componer — es de instalación, no de un tenant.
    logo_media_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("platform_media.id"), nullable=True
    )
    favicon_media_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("platform_media.id"), nullable=True
    )
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


class PlatformAnalyticsSettings(Base, TimestampMixin):
    """Identificadores de proveedores externos de analítica: exactamente **una** fila.

    Misma forma que `PlatformBranding` (PK `'default'`). Los tres campos son
    **identificadores semi-públicos, no secretos**: el `ga4_measurement_id`
    (`G-…`) y el `meta_pixel_id` ya viajan en el HTML de cualquier sitio que
    los use, y el "token" de Cloudflare Web Analytics (hallazgo red-team #5)
    se embebe en el snippet público del beacon por diseño de Cloudflare.
    Que nadie los trate como credenciales — ni pegue ahí una real por error.
    Las credenciales de verdad (p. ej. la cuenta de servicio de la API de
    Datos de GA4) viven en variables de entorno, no en esta tabla.
    """

    __tablename__ = "platform_analytics_settings"
    __table_args__ = (
        CheckConstraint("singleton = 'default'", name="ck_platform_analytics_settings_singleton"),
    )

    singleton: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    ga4_measurement_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meta_pixel_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cloudflare_analytics_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Contenedor de Google Tag Manager: cuando está configurado, es el único
    # tag que se inyecta (la medición de GA4 va dentro del contenedor, y el
    # gtag directo se omite para no contar doble).
    gtm_container_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
