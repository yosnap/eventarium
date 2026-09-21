"""Tablas de la pasarela de IA: configuración, servicios y uso.

Cuatro tablas de configuración, dos de plataforma y dos de organización:

- `platform_ai_settings`: fila **única** de la instalación (`CHECK id = 1`),
  con la configuración por defecto del admin y el techo de gasto.
- `organization_ai_settings`: override **opcional** por organización
  (PK = `organization_id`, `CASCADE`), mismo patrón 1:1 que
  `organization_branding`. **Ausencia de fila = heredar** de plataforma.
- `platform_services` / `organization_services`: interruptores globales y su
  override binario por organización.

Las dos de organización llevan `FORCE ROW LEVEL SECURITY` con
`CREATE POLICY tenant_<tabla>`; las dos de plataforma no son de organización
y se protegen en la migración con `REVOKE ALL … FROM app_user` +
`GRANT SELECT` (V-2): `app_user` **lee** la config de plataforma en su propia
sesión —para que la organización heredera y el worker la resuelvan sin abrir
una segunda sesión (V-3/V-4)— pero no puede escribirla ni borrarla. Lo que
lee es texto cifrado; el secreto real (`AI_SETTINGS_ENCRYPTION_KEY`) no está
en la base de datos.

Invariante de `organization_ai_settings` (V-5, resolución todo-o-nada por
fila): si la fila existe, tiene proveedor, modelo y clave. No hay overrides a
medias que pudieran mezclar la clave compartida de plataforma con un
`api_base` del tenant. Se sostiene con columnas `NOT NULL`, no solo con
validación en el servicio.

Y dos de uso (fase 2), las dos de organización y con RLS forzado:

- `ai_usage_records`: una fila por llamada, con el coste en **USD**. La
  reserva la escribe `reservado` con un coste estimado **no nulo**; la
  liquidación la pasa a `liquidado` con el real, o a `fallido`.
- `ai_usage_periods`: una fila por `(organización, periodo)`, **sin totales**.
  Es solo el mutex de la reserva: existe siempre —también para la
  organización que hereda la configuración de plataforma y por tanto no tiene
  fila en `organization_ai_settings`— así que dos llamadas concurrentes de la
  misma organización se serializan sobre ella. El gasto acumulado se calcula
  sumando `ai_usage_records`, que es la única fuente de verdad.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.modules.ai_gateway.errores import CODIGOS_DE_ERROR
from app.modules.ai_gateway.proveedores import LONGITUD_MODELO, LONGITUD_PROVEEDOR
from app.modules.ai_gateway.servicios import LONGITUD_SERVICE_KEY
from app.shared.identifiers import new_uuid7

#: Importes en **USD** con `Numeric(14,6)`, nunca céntimos enteros: el coste
#: por llamada de un LLM son fracciones de céntimo y un `Integer` en céntimos
#: las redondearía a 0, dejando el límite ciego (hallazgo S2-5).
_IMPORTE_USD = Numeric(14, 6)

#: Longitud de `api_key_hint`: los últimos caracteres de la clave.
LONGITUD_PISTA = 8

#: Longitud máxima de un `api_base`. Solo `custom` lo usa.
LONGITUD_API_BASE = 300

#: Identificador de la fila única de `platform_ai_settings`.
ID_FILA_DE_PLATAFORMA = 1

#: Longitud de `ai_usage_records.use_case` («accounting_ocr», …).
LONGITUD_USE_CASE = 60

#: Longitud de `ai_usage_records.status`.
LONGITUD_ESTADO = 20

#: Longitud de `ai_usage_records.error_code`.
LONGITUD_ERROR_CODE = 40

#: `'YYYY-MM'`: el periodo del límite de gasto es mensual.
LONGITUD_PERIODO = 7

#: Estado de una fila de uso. Cerrado, con `CHECK` en la migración.
ESTADO_RESERVADO = "reservado"
ESTADO_LIQUIDADO = "liquidado"
ESTADO_FALLIDO = "fallido"
ESTADOS_DE_USO: tuple[str, ...] = (ESTADO_RESERVADO, ESTADO_LIQUIDADO, ESTADO_FALLIDO)

#: Estados que **cuentan** para el límite del periodo: la reserva en vuelo y
#: la llamada ya liquidada. `fallido` no cuenta — el proveedor no lo cobra.
ESTADOS_QUE_GASTAN: tuple[str, ...] = (ESTADO_RESERVADO, ESTADO_LIQUIDADO)


class PlatformAiSettings(Base, TimestampMixin):
    """Configuración de IA por defecto de la instalación. Una sola fila."""

    __tablename__ = "platform_ai_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_platform_ai_settings_fila_unica"),
        # La fila puede existir solo con el techo de gasto (sin credenciales
        # todavía), pero nunca con credenciales a medias: o están las tres
        # columnas o no está ninguna.
        CheckConstraint(
            "(provider IS NULL AND default_model IS NULL AND api_key_encrypted IS NULL) "
            "OR (provider IS NOT NULL AND default_model IS NOT NULL "
            "AND api_key_encrypted IS NOT NULL)",
            name="ck_platform_ai_settings_credencial_completa",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=ID_FILA_DE_PLATAFORMA)
    provider: Mapped[str | None] = mapped_column(String(LONGITUD_PROVEEDOR), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(LONGITUD_MODELO), nullable=True)
    #: `NULL` salvo en `custom`: la base URL de los proveedores con
    #: `api_base` fijo vive en el catálogo, no en la fila.
    api_base: Mapped[str | None] = mapped_column(String(LONGITUD_API_BASE), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(LONGITUD_PISTA), nullable=True)
    #: Techo de gasto mensual de toda la instalación. `NULL` = sin techo.
    monthly_ceiling_usd: Mapped[Decimal | None] = mapped_column(_IMPORTE_USD, nullable=True)


class OrganizationAiSettings(Base, TimestampMixin):
    """Override de configuración de IA de una organización. 1:1, opcional."""

    __tablename__ = "organization_ai_settings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_ai_settings_organization_id",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    # NOT NULL: una fila de override sin credencial completa no existe (V-5).
    provider: Mapped[str] = mapped_column(String(LONGITUD_PROVEEDOR), nullable=False)
    default_model: Mapped[str] = mapped_column(String(LONGITUD_MODELO), nullable=False)
    api_base: Mapped[str | None] = mapped_column(String(LONGITUD_API_BASE), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hint: Mapped[str] = mapped_column(String(LONGITUD_PISTA), nullable=False)
    #: Límite propio. `NULL` = sin límite propio (manda el techo, si lo hay).
    monthly_limit_usd: Mapped[Decimal | None] = mapped_column(_IMPORTE_USD, nullable=True)


class PlatformService(Base, TimestampMixin):
    """Interruptor global de un servicio conmutable de la instalación."""

    __tablename__ = "platform_services"

    service_key: Mapped[str] = mapped_column(String(LONGITUD_SERVICE_KEY), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OrganizationService(Base, TimestampMixin):
    """Override de un servicio para una organización concreta.

    Binario y en un solo sentido (V-7): la fila existe **solo** para forzar
    el servicio a `off`; volver a heredar es borrar la fila. Nunca «forzar
    on», así que un servicio apagado globalmente no se reactiva por
    organización. La escribe **solo** el admin (V-8).
    """

    __tablename__ = "organization_services"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "service_key", name="pk_organization_services"),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_services_organization_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["service_key"],
            ["platform_services.service_key"],
            name="fk_organization_services_service_key",
            ondelete="CASCADE",
        ),
        CheckConstraint("enabled = false", name="ck_organization_services_solo_desactiva"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    service_key: Mapped[str] = mapped_column(String(LONGITUD_SERVICE_KEY), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AiUsagePeriod(Base, TimestampMixin):
    """Mutex de la reserva de gasto: una fila por organización y periodo.

    Deliberadamente **sin columna de total**: el acumulado se calcula sumando
    `ai_usage_records`, que es la única fuente de verdad del gasto. Un total
    denormalizado aquí sería un segundo número que mantener sincronizado y
    que podría discrepar del detalle que ve el panel.

    Su única función es existir **siempre** —se crea con `INSERT … ON CONFLICT
    DO NOTHING` en la primera llamada del periodo— para que el `SELECT …
    FOR UPDATE` de la reserva tenga una fila que bloquear también cuando la
    organización hereda la configuración de plataforma y por tanto no tiene
    ninguna fila propia que bloquear (hallazgo V-1 del red-team: bloquear
    `organization_ai_settings` no serializa a la organización heredera).
    """

    __tablename__ = "ai_usage_periods"
    __table_args__ = (
        PrimaryKeyConstraint("organization_id", "periodo", name="pk_ai_usage_periods"),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_usage_periods_organization_id",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    periodo: Mapped[str] = mapped_column(String(LONGITUD_PERIODO), nullable=False)


class AiUsageRecord(Base, TimestampMixin):
    """Una llamada a un proveedor de IA: lo que se reservó y lo que costó.

    `provider`/`model` se **copian** a la fila en vez de resolverse por join
    (mismo criterio que `payments/models.py`): la configuración cambia y el
    histórico tiene que seguir diciendo con qué se hizo cada llamada.

    `cost_usd` es `NOT NULL` desde el primer `INSERT`: una fila `reservado`
    sin importe no sumaría al gasto del periodo y dejaría el límite **ciego**
    (V-1, Critical). La reserva escribe una estimación; la liquidación la
    sustituye por el coste real cuando el proveedor lo da, y si no lo da
    conserva la estimación y baja `cost_auditable` — nunca un `0` silencioso.

    La unidad va en el nombre de la columna a propósito: son **dólares** con
    seis decimales, no céntimos enteros. Una extracción de un modelo barato
    cuesta fracciones de céntimo y un entero de céntimos la redondearía a 0.
    """

    __tablename__ = "ai_usage_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_ai_usage_records_organization_id",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('" + "', '".join(ESTADOS_DE_USO) + "')",
            name="ck_ai_usage_records_status",
        ),
        CheckConstraint(
            "error_code IS NULL OR error_code IN ('" + "', '".join(sorted(CODIGOS_DE_ERROR)) + "')",
            name="ck_ai_usage_records_error_code",
        ),
        # Gasto del periodo y listado del panel: los dos filtran por
        # organización y recortan por fecha.
        Index("ix_ai_usage_records_organization_id_created_at", "organization_id", "created_at"),
        # Barrido de reservas colgadas y recuento por estado.
        Index("ix_ai_usage_records_organization_id_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    use_case: Mapped[str] = mapped_column(String(LONGITUD_USE_CASE), nullable=False)
    provider: Mapped[str] = mapped_column(String(LONGITUD_PROVEEDOR), nullable=False)
    model: Mapped[str] = mapped_column(String(LONGITUD_MODELO), nullable=False)
    status: Mapped[str] = mapped_column(String(LONGITUD_ESTADO), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal] = mapped_column(_IMPORTE_USD, nullable=False)
    #: `False` cuando el importe es la estimación de la reserva porque el
    #: proveedor (o el mapa de precios de LiteLLM) no da el coste real.
    cost_auditable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(LONGITUD_ERROR_CODE), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
