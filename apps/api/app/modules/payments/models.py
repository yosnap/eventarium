"""Modelos de pagos con Stripe Connect.

Fase 6 del PRD, fase 1 de trabajo. Mismo patrón que el resto del esquema:
`organization_id` denormalizado y FK **compuestas** contra `(id,
organization_id)` del padre, nunca FK simples — la integridad referencial de
PostgreSQL no pasa por RLS.

Nada de este módulo llama a Stripe: es solo el esquema sobre el que se apoyan
las fases 2-5 (`plans/260909-0030-prd-fase-6-pagos-stripe-connect/`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.shared.identifiers import new_uuid7


class OrganizationStripeAccount(Base, TimestampMixin):
    """Cuenta Stripe Connect de una organización.

    Una organización puede tener varias filas a lo largo del tiempo, pero
    **una sola activa** (`deauthorized_at IS NULL`): el índice único es
    parcial, no `UNIQUE(organization_id)` a secas (hallazgo #17 del red-team
    de la fase 6). Con la constraint simple, una organización que desconecta
    su cuenta no podría reconectarse nunca sin tocar la base de datos a mano,
    y se perdería el `acct_id` con el que se cobraron los pagos antiguos —
    necesario para reembolsarlos. Por eso `event_payments` copia su propio
    `stripe_account_id`: el reembolso se resuelve por la cuenta *del pago*,
    nunca por la cuenta actual de la organización.
    """

    __tablename__ = "organization_stripe_accounts"
    __table_args__ = (
        UniqueConstraint(
            "id", "organization_id", name="uq_organization_stripe_accounts_id_organization_id"
        ),
        UniqueConstraint(
            "stripe_account_id", name="uq_organization_stripe_accounts_stripe_account_id"
        ),
        # Parcial: permite histórico de cuentas desconectadas, ver docstring.
        Index(
            "uq_organization_stripe_accounts_activa",
            "organization_id",
            unique=True,
            postgresql_where=text("deauthorized_at IS NULL"),
        ),
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_stripe_accounts_organization_id",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    stripe_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    charges_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payouts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details_submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deauthorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventTicketType(Base, TimestampMixin):
    """Tipo de entrada de un evento (nombre, precio, cupo, ventana de venta).

    No es reutilizable entre eventos (decisión de producto ya tomada): cada
    fila pertenece a un único `event_id`.
    """

    __tablename__ = "event_ticket_types"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_ticket_types_event_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "organization_id", name="uq_event_ticket_types_id_organization_id"),
        UniqueConstraint("event_id", "name", name="uq_event_ticket_types_event_id_name"),
        CheckConstraint("price_cents >= 0", name="ck_event_ticket_types_price_cents_no_negativo"),
        CheckConstraint(
            "max_quantity IS NULL OR max_quantity > 0",
            name="ck_event_ticket_types_max_quantity_positivo",
        ),
        CheckConstraint(
            "sales_end_at IS NULL OR sales_start_at IS NULL OR sales_end_at > sales_start_at",
            name="ck_event_ticket_types_ventana_de_venta",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # Formato de Stripe: ISO 4217 en minúsculas.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="eur")
    # `NULL` = sin límite.
    max_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sales_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EventDiscountCode(Base, TimestampMixin):
    """Código de descuento de un evento, gestionado en base de datos propia.

    **Sin columna `used_count`** (hallazgo #19 del red-team de la fase 6): el
    consumo de un código se deriva de un `COUNT` sobre `event_payments` en los
    estados consumibles (`pending`, `paid`, `partially_refunded`, `refunded`),
    ejecutado con la fila del código bloqueada (`FOR UPDATE`, fase 3/4 de
    trabajo). Un contador que la compra incrementa y el barrido de caducados
    decrementa se desajusta en cuanto dos ejecuciones del cron se solapan, y
    ninguna constraint lo detecta; el derivado no puede desajustarse porque
    sale de la misma tabla que decide si se cobró.
    """

    __tablename__ = "event_discount_codes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_discount_codes_event_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: RESTRICT por defecto — no se borra un tipo de entrada
        # con códigos de descuento que lo referencian.
        ForeignKeyConstraint(
            ["ticket_type_id", "organization_id"],
            ["event_ticket_types.id", "event_ticket_types.organization_id"],
            name="fk_event_discount_codes_ticket_type_id_organization_id",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_event_discount_codes_id_organization_id"
        ),
        UniqueConstraint("event_id", "code", name="uq_event_discount_codes_event_id_code"),
        CheckConstraint(
            "discount_type IN ('percentage', 'fixed_amount')",
            name="ck_event_discount_codes_discount_type",
        ),
        # Condicionado por `discount_type`, mismo patrón que
        # `event_registration_questions.options` (`registrations/models.py`):
        # 1..100 si es porcentaje, cualquier importe positivo si es fijo.
        CheckConstraint(
            "(discount_type = 'percentage' AND discount_value BETWEEN 1 AND 100) "
            "OR (discount_type = 'fixed_amount' AND discount_value > 0)",
            name="ck_event_discount_codes_discount_value_por_tipo",
        ),
        CheckConstraint(
            "max_uses IS NULL OR max_uses > 0", name="ck_event_discount_codes_max_uses_positivo"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Guardado en mayúsculas; comparado en mayúsculas por el servicio.
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # `NULL` = aplica a todos los tipos de entrada del evento.
    ticket_type_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)


class EventPayment(Base, TimestampMixin):
    """Pago de una compra de entrada, con su ciclo de vida de Checkout.

    `stripe_account_id` **se copia aquí**, no se resuelve consultando a la
    organización en el momento de reembolsar (hallazgos #8 y #17 del red-team
    de la fase 6): un pago cobrado en una cuenta que después se desconectó
    solo se puede reembolsar contra *esa* cuenta.
    """

    __tablename__ = "event_payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_payments_event_id_organization_id",
            ondelete="CASCADE",
        ),
        # Lista de columnas obligatoria (Postgres 15+): un `SET NULL` a secas
        # sobre una FK compuesta intentaría anular también `organization_id`,
        # que es `NOT NULL`. El borrado RGPD
        # (`app/modules/admin/service.py:borrar_inscrito_por_email`) borra la
        # fila de `event_registrations`; sin este `ondelete`, ese borrado
        # fallaría con `IntegrityError` en cuanto exista un pago (hallazgo
        # #15).
        ForeignKeyConstraint(
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_payments_registration_id_organization_id",
            ondelete="SET NULL (registration_id)",
        ),
        # Sin `ondelete`: RESTRICT por defecto — no se borra un tipo de
        # entrada ni un código de descuento con pagos hechos.
        ForeignKeyConstraint(
            ["ticket_type_id", "organization_id"],
            ["event_ticket_types.id", "event_ticket_types.organization_id"],
            name="fk_event_payments_ticket_type_id_organization_id",
        ),
        ForeignKeyConstraint(
            ["discount_code_id", "organization_id"],
            ["event_discount_codes.id", "event_discount_codes.organization_id"],
            name="fk_event_payments_discount_code_id_organization_id",
        ),
        UniqueConstraint("id", "organization_id", name="uq_event_payments_id_organization_id"),
        # Una inscripción, un pago: un reintento tras caducar reutiliza la
        # fila (hallazgo #7), no crea una segunda.
        UniqueConstraint("registration_id", name="uq_event_payments_registration_id"),
        UniqueConstraint(
            "stripe_checkout_session_id", name="uq_event_payments_stripe_checkout_session_id"
        ),
        UniqueConstraint(
            "stripe_payment_intent_id", name="uq_event_payments_stripe_payment_intent_id"
        ),
        CheckConstraint(
            "status IN ('pending', 'paid', 'refunded', 'partially_refunded', 'expired')",
            name="ck_event_payments_status",
        ),
        # Consulta del panel de pagos por evento.
        Index("ix_event_payments_event_id_status", "event_id", "status"),
        # Consumo derivado de un código de descuento.
        Index("ix_event_payments_discount_code_id", "discount_code_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    # Nullable: sobrevive al borrado RGPD de la inscripción, ver `ondelete` de
    # la FK compuesta de arriba.
    registration_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    stripe_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    ticket_type_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    discount_code_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    # Nulo hasta que se crea la Checkout Session.
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkout_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkout_link_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Nulo hasta que el pago completa.
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    refunded_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EventPaymentRefund(Base, TimestampMixin):
    """Intención de reembolso, persistida **antes** de llamar a Stripe.

    Sin esta fila, un reembolso que Stripe acepta y cuya transacción de base
    de datos falla después es dinero devuelto sin ningún registro (hallazgos
    #11 y #12 del red-team de la fase 6). La `idempotency_key` que se envía a
    Stripe se deriva de esta PK (`refund_{id}`) en la fase 5 de trabajo, no se
    guarda en ninguna columna: así un reintento de la tarea no puede generar
    una clave distinta.
    """

    __tablename__ = "event_payment_refunds"
    __table_args__ = (
        ForeignKeyConstraint(
            ["payment_id", "organization_id"],
            ["event_payments.id", "event_payments.organization_id"],
            name="fk_event_payment_refunds_payment_id_organization_id",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id", "organization_id", name="uq_event_payment_refunds_id_organization_id"
        ),
        UniqueConstraint("stripe_refund_id", name="uq_event_payment_refunds_stripe_refund_id"),
        CheckConstraint(
            "reason IN ('cancellation', 'manual')", name="ck_event_payment_refunds_reason"
        ),
        CheckConstraint(
            "status IN ('pending', 'submitted', 'succeeded', 'failed')",
            name="ck_event_payment_refunds_status",
        ),
        Index("ix_event_payment_refunds_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    revoke_ticket: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    stripe_refund_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StripeWebhookEvent(Base):
    """Registro antirreplay de eventos de webhook de Stripe.

    Tabla de **instalación**, sin RLS: `REVOKE ALL ... FROM app_user` en la
    migración (Decisión #11 del plan), mismo patrón que `audit_log`/
    `cookie_consents` (`0012_patrocinio_legal_auditoria.py`). Solo la
    escribe/lee `app_maintainer`.

    `payload` **no es el evento crudo de Stripe** (hallazgo #15): es una
    proyección con lista blanca de campos, nunca datos personales del
    comprador (`customer_details.email`/`address` de un
    `checkout.session.completed`, por ejemplo). Lo que la fase de trabajo que
    procese el webhook no necesite, no se guarda.
    """

    __tablename__ = "stripe_webhook_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="ck_stripe_webhook_events_status",
        ),
    )

    # El `evt_...` de Stripe: es la propia clave de idempotencia, no se genera
    # ninguna PK propia.
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    stripe_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
