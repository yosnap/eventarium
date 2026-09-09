"""pagos stripe connect

Fase 6 del PRD, fase 1 de trabajo. Seis tablas nuevas
(`organization_stripe_accounts`, `event_ticket_types`,
`event_discount_codes`, `event_payments`, `event_payment_refunds`,
`stripe_webhook_events`), dos columnas nuevas
(`event_registrations.payment_expires_at`,
`events.payment_checkout_window_minutes`) y los permisos
`payments:read`/`payments:write`.

Mismo patrón de FK **compuestas** contra `(id, organization_id)` del padre y
RLS `tenant_<tabla>` que el resto del esquema
(`0012_patrocinio_legal_auditoria.py`). `stripe_webhook_events` es tabla de
**instalación**: sin RLS, con `REVOKE ALL ... FROM app_user` (precedente
exacto en `0012`, hallazgo #1 de su red-team) — es el mecanismo antirreplay
de los webhooks, y si `app_user` pudiera borrarla cualquier sesión de
organización podría reabrir la ventana de reprocesar un evento ya aplicado.

El índice único de `organization_stripe_accounts` es **parcial**
(`WHERE deauthorized_at IS NULL`), no `UNIQUE(organization_id)` a secas
(hallazgo #17 del red-team de la fase 6): permite histórico de cuentas
desconectadas sin perder el `acct_id` con el que se cobraron sus pagos.

`event_payments.registration_id` usa `ondelete="SET NULL (registration_id)"`
(sintaxis Postgres 15+, lista de columnas explícita): el borrado RGPD
(`app/modules/admin/service.py:borrar_inscrito_por_email`) no debe fallar por
un pago asociado, y un `SET NULL` a secas sobre esta FK compuesta intentaría
anular también `organization_id`, que es `NOT NULL`.

`event_discount_codes` no lleva `used_count`: su consumo se deriva de un
`COUNT` sobre `event_payments` (hallazgo #19).

Backfill de `payments:read`/`payments:write` a cualquier rol con
`organizations:write` (mismo criterio que `0010`/`0011`/`0012`), más la
plantilla `ORGANIZER` actualizada en `app/modules/roles/system_roles.py` para
las organizaciones creadas después de esta migración (decisión #16 del plan).

Revision ID: 0013_pagos_stripe_connect
Revises: 0012_patrocinio_legal_auditoria
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0013_pagos_stripe_connect"
down_revision: str | None = "0012_patrocinio_legal_auditoria"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Solo las de dominio (con RLS); `stripe_webhook_events` se comprueba aparte
# porque su comprobación de privilegios es negativa, no positiva.
TABLAS_DE_DOMINIO = (
    "organization_stripe_accounts",
    "event_ticket_types",
    "event_discount_codes",
    "event_payments",
    "event_payment_refunds",
)

TABLAS_DE_INSTALACION = ("stripe_webhook_events",)


def upgrade() -> None:
    _crear_tablas()
    _anadir_columnas()
    _verificar_privilegios_de_app_user()
    _activar_rls_de_dominio()
    _restringir_tablas_de_instalacion()
    _backfill_permisos_de_pagos()


def _crear_tablas() -> None:
    op.create_table(
        "organization_stripe_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("stripe_account_id", sa.String(length=255), nullable=False),
        sa.Column("charges_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payouts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("details_submitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deauthorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_stripe_accounts_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_stripe_accounts")),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            name="uq_organization_stripe_accounts_id_organization_id",
        ),
        sa.UniqueConstraint(
            "stripe_account_id", name="uq_organization_stripe_accounts_stripe_account_id"
        ),
    )
    op.create_index(
        op.f("ix_organization_stripe_accounts_organization_id"),
        "organization_stripe_accounts",
        ["organization_id"],
        unique=False,
    )
    # Parcial: una organización tiene una sola cuenta *activa*, pero conserva
    # el histórico de las desconectadas (hallazgo #17).
    op.create_index(
        "uq_organization_stripe_accounts_activa",
        "organization_stripe_accounts",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("deauthorized_at IS NULL"),
    )

    op.create_table(
        "event_ticket_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="eur"),
        sa.Column("max_quantity", sa.Integer(), nullable=True),
        sa.Column("sales_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sales_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_ticket_types_event_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_ticket_types")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_event_ticket_types_id_organization_id"
        ),
        sa.UniqueConstraint("event_id", "name", name="uq_event_ticket_types_event_id_name"),
        sa.CheckConstraint(
            "price_cents >= 0", name="ck_event_ticket_types_price_cents_no_negativo"
        ),
        sa.CheckConstraint(
            "max_quantity IS NULL OR max_quantity > 0",
            name="ck_event_ticket_types_max_quantity_positivo",
        ),
        sa.CheckConstraint(
            "sales_end_at IS NULL OR sales_start_at IS NULL OR sales_end_at > sales_start_at",
            name="ck_event_ticket_types_ventana_de_venta",
        ),
    )
    op.create_index(
        op.f("ix_event_ticket_types_event_id"), "event_ticket_types", ["event_id"], unique=False
    )

    op.create_table(
        "event_discount_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("discount_type", sa.String(length=20), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ticket_type_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_discount_codes_event_id_organization_id",
            ondelete="CASCADE",
        ),
        # Sin `ondelete`: RESTRICT por defecto, no se borra un tipo de entrada
        # con códigos de descuento que lo referencian.
        sa.ForeignKeyConstraint(
            ["ticket_type_id", "organization_id"],
            ["event_ticket_types.id", "event_ticket_types.organization_id"],
            name="fk_event_discount_codes_ticket_type_id_organization_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_discount_codes")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_event_discount_codes_id_organization_id"
        ),
        sa.UniqueConstraint("event_id", "code", name="uq_event_discount_codes_event_id_code"),
        sa.CheckConstraint(
            "discount_type IN ('percentage', 'fixed_amount')",
            name="ck_event_discount_codes_discount_type",
        ),
        # Condicionado por `discount_type`, mismo patrón que
        # `event_registration_questions.options`: 1..100 si es porcentaje,
        # cualquier importe positivo si es fijo.
        sa.CheckConstraint(
            "(discount_type = 'percentage' AND discount_value BETWEEN 1 AND 100) "
            "OR (discount_type = 'fixed_amount' AND discount_value > 0)",
            name="ck_event_discount_codes_discount_value_por_tipo",
        ),
        sa.CheckConstraint(
            "max_uses IS NULL OR max_uses > 0", name="ck_event_discount_codes_max_uses_positivo"
        ),
    )
    op.create_index(
        op.f("ix_event_discount_codes_event_id"), "event_discount_codes", ["event_id"], unique=False
    )

    op.create_table(
        "event_payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("registration_id", sa.UUID(), nullable=True),
        sa.Column("stripe_account_id", sa.String(length=255), nullable=False),
        sa.Column("ticket_type_id", sa.UUID(), nullable=False),
        sa.Column("discount_code_id", sa.UUID(), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("checkout_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkout_link_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("refunded_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "organization_id"],
            ["events.id", "events.organization_id"],
            name="fk_event_payments_event_id_organization_id",
            ondelete="CASCADE",
        ),
        # Lista de columnas obligatoria (Postgres 15+): un `SET NULL` a secas
        # sobre esta FK compuesta intentaría anular también `organization_id`,
        # que es `NOT NULL`. Sin este `ondelete`, el borrado RGPD de una
        # inscripción con pago asociado fallaría con `IntegrityError`
        # (hallazgo #15).
        sa.ForeignKeyConstraint(
            ["registration_id", "organization_id"],
            ["event_registrations.id", "event_registrations.organization_id"],
            name="fk_event_payments_registration_id_organization_id",
            ondelete="SET NULL (registration_id)",
        ),
        # Sin `ondelete`: RESTRICT por defecto, no se borra un tipo de entrada
        # ni un código de descuento con pagos hechos.
        sa.ForeignKeyConstraint(
            ["ticket_type_id", "organization_id"],
            ["event_ticket_types.id", "event_ticket_types.organization_id"],
            name="fk_event_payments_ticket_type_id_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["discount_code_id", "organization_id"],
            ["event_discount_codes.id", "event_discount_codes.organization_id"],
            name="fk_event_payments_discount_code_id_organization_id",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_payments")),
        sa.UniqueConstraint("id", "organization_id", name="uq_event_payments_id_organization_id"),
        # Una inscripción, un pago: un reintento tras caducar reutiliza la
        # fila (hallazgo #7), no crea una segunda.
        sa.UniqueConstraint("registration_id", name="uq_event_payments_registration_id"),
        sa.UniqueConstraint(
            "stripe_checkout_session_id", name="uq_event_payments_stripe_checkout_session_id"
        ),
        sa.UniqueConstraint(
            "stripe_payment_intent_id", name="uq_event_payments_stripe_payment_intent_id"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'refunded', 'partially_refunded', 'expired')",
            name="ck_event_payments_status",
        ),
    )
    op.create_index(
        op.f("ix_event_payments_organization_id"),
        "event_payments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_payments_event_id"), "event_payments", ["event_id"], unique=False
    )
    # Consulta del panel de pagos por evento.
    op.create_index(
        "ix_event_payments_event_id_status", "event_payments", ["event_id", "status"], unique=False
    )
    # Consumo derivado de un código de descuento.
    op.create_index(
        "ix_event_payments_discount_code_id", "event_payments", ["discount_code_id"], unique=False
    )

    op.create_table(
        "event_payment_refunds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("revoke_ticket", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("stripe_refund_id", sa.String(length=255), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["payment_id", "organization_id"],
            ["event_payments.id", "event_payments.organization_id"],
            name="fk_event_payment_refunds_payment_id_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_payment_refunds")),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_event_payment_refunds_id_organization_id"
        ),
        sa.UniqueConstraint("stripe_refund_id", name="uq_event_payment_refunds_stripe_refund_id"),
        sa.CheckConstraint(
            "reason IN ('cancellation', 'manual')", name="ck_event_payment_refunds_reason"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'submitted', 'succeeded', 'failed')",
            name="ck_event_payment_refunds_status",
        ),
    )
    op.create_index(
        op.f("ix_event_payment_refunds_organization_id"),
        "event_payment_refunds",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_payment_refunds_payment_id"),
        "event_payment_refunds",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        "ix_event_payment_refunds_status", "event_payment_refunds", ["status"], unique=False
    )

    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("stripe_account_id", sa.String(length=255), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        # Proyección con lista blanca de campos, nunca el evento crudo de
        # Stripe (hallazgo #15): nunca `customer_details.email`/`address` ni
        # ningún otro dato personal del comprador.
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="received"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stripe_webhook_events")),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="ck_stripe_webhook_events_status",
        ),
    )


def _anadir_columnas() -> None:
    # Hermana de `waitlist_promotion_expires_at`: nula mientras no haya una
    # compra en curso.
    op.add_column(
        "event_registrations",
        sa.Column("payment_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Tipo de entrada y código de descuento elegidos en el formulario público
    # de compra (`POST /public/events/{slug}/checkout`), único punto de alta
    # de una inscripción de un evento de pago sea cual sea su
    # `registration_mode`. Se fijan una vez, en el alta, y sobreviven aunque
    # la inscripción pase por `pending_approval`/`waitlisted` antes de llegar
    # a `pending_payment`: sin esta columna, aprobar o promover una de esas
    # dos no tiene forma de saber qué entrada cobrar.
    op.add_column(
        "event_registrations",
        sa.Column("ticket_type_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "event_registrations",
        sa.Column("discount_code_id", sa.UUID(), nullable=True),
    )
    # Sin `ondelete`: RESTRICT por defecto, mismo criterio que
    # `event_payments.ticket_type_id`/`discount_code_id` — no se borra un tipo
    # de entrada ni un código de descuento con inscripciones que los eligieron.
    op.create_foreign_key(
        "fk_event_registrations_ticket_type_id_organization_id",
        "event_registrations",
        "event_ticket_types",
        ["ticket_type_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_event_registrations_discount_code_id_organization_id",
        "event_registrations",
        "event_discount_codes",
        ["discount_code_id", "organization_id"],
        ["id", "organization_id"],
    )
    # `server_default="30"` para que la columna `NOT NULL` se aplique sobre
    # eventos existentes; el valor por defecto en Python lo fija el modelo
    # para altas nuevas (mismo criterio que el resto del esquema).
    op.add_column(
        "events",
        sa.Column(
            "payment_checkout_window_minutes",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )
    op.create_check_constraint(
        "ck_events_payment_checkout_window_minutes_rango",
        "events",
        "payment_checkout_window_minutes BETWEEN 30 AND 1439",
    )


def _verificar_privilegios_de_app_user() -> None:
    """Mismo patrón que `0002_esquema_base`/`0011`/`0012`: falla aquí, no en runtime."""
    conexion = op.get_bind()
    for tabla in TABLAS_DE_DOMINIO:
        concedido = conexion.execute(
            sa.text("SELECT has_table_privilege('app_user', :tabla, 'SELECT')"),
            {"tabla": tabla},
        ).scalar()
        if not concedido:
            raise RuntimeError(
                f"El rol «app_user» no tiene SELECT sobre «{tabla}». Ejecuta "
                "infra/scripts/ensure-roles.sh para aplicar ALTER DEFAULT PRIVILEGES."
            )


def _activar_rls_de_dominio() -> None:
    for tabla in TABLAS_DE_DOMINIO:
        op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_{tabla} ON {tabla} "
            "USING (organization_id = app_current_organization()) "
            "WITH CHECK (organization_id = app_current_organization())"
        )


def _restringir_tablas_de_instalacion() -> None:
    """`stripe_webhook_events` no lleva RLS, pero eso no es "sin acceso":
    `ALTER DEFAULT PRIVILEGES` (`infra/postgres/sql/roles.sql`) concede
    SELECT/INSERT/UPDATE/DELETE a `app_user` sobre toda tabla nueva
    automáticamente. Sin este `REVOKE`, cualquier sesión de organización
    podría leer y **borrar** el registro antirreplay de webhooks completo de
    la instalación (mismo hallazgo #1 de `0012`, aplicado aquí). Solo la
    escribe/lee `app_maintainer` (endpoint de webhooks y tarea de fondo, fase
    3 de trabajo), así que el `REVOKE` no rompe ningún camino."""
    for tabla in TABLAS_DE_INSTALACION:
        op.execute(f"REVOKE ALL ON {tabla} FROM app_user")


# Ancla al permiso, no al nombre del rol (mismo criterio que `0010`-`0012`): un
# rol a medida con `organizations:write` también necesita `payments:*`, exista
# o no con la clave `owner`/`organizer`.
_BACKFILL_PAGOS = (
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'payments:read', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'payments:read'
)
    """,
    """
INSERT INTO role_permissions (role_id, permission, organization_id)
SELECT r.id, 'payments:write', r.organization_id
FROM roles r
WHERE EXISTS (
  SELECT 1 FROM role_permissions rp
  WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'
)
AND NOT EXISTS (
  SELECT 1 FROM role_permissions rp2
  WHERE rp2.role_id = r.id AND rp2.permission = 'payments:write'
)
    """,
)


def _backfill_permisos_de_pagos() -> None:
    for sentencia in _BACKFILL_PAGOS:
        op.execute(sentencia)


def downgrade() -> None:
    # Destructivo a partir de aquí: revierte el backfill y borra las tablas
    # enteras con sus datos. Válido para revertir un despliegue fallido antes
    # de que existan datos reales — no para producción con datos.
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission IN ('payments:read', 'payments:write') "
        "AND role_id IN ("
        "  SELECT r.id FROM roles r "
        "  WHERE EXISTS ("
        "    SELECT 1 FROM role_permissions rp "
        "    WHERE rp.role_id = r.id AND rp.permission = 'organizations:write'"
        "  )"
        ")"
    )

    for tabla in reversed(TABLAS_DE_DOMINIO):
        op.execute(f"DROP POLICY IF EXISTS tenant_{tabla} ON {tabla}")
        op.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")

    op.drop_constraint("ck_events_payment_checkout_window_minutes_rango", "events", type_="check")
    op.drop_column("events", "payment_checkout_window_minutes")
    op.drop_constraint(
        "fk_event_registrations_discount_code_id_organization_id",
        "event_registrations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_event_registrations_ticket_type_id_organization_id",
        "event_registrations",
        type_="foreignkey",
    )
    op.drop_column("event_registrations", "discount_code_id")
    op.drop_column("event_registrations", "ticket_type_id")
    op.drop_column("event_registrations", "payment_expires_at")

    op.drop_table("stripe_webhook_events")

    op.drop_index("ix_event_payment_refunds_status", table_name="event_payment_refunds")
    op.drop_index(op.f("ix_event_payment_refunds_payment_id"), table_name="event_payment_refunds")
    op.drop_index(
        op.f("ix_event_payment_refunds_organization_id"), table_name="event_payment_refunds"
    )
    op.drop_table("event_payment_refunds")

    op.drop_index("ix_event_payments_discount_code_id", table_name="event_payments")
    op.drop_index("ix_event_payments_event_id_status", table_name="event_payments")
    op.drop_index(op.f("ix_event_payments_event_id"), table_name="event_payments")
    op.drop_index(op.f("ix_event_payments_organization_id"), table_name="event_payments")
    op.drop_table("event_payments")

    op.drop_index(op.f("ix_event_discount_codes_event_id"), table_name="event_discount_codes")
    op.drop_table("event_discount_codes")

    op.drop_index(op.f("ix_event_ticket_types_event_id"), table_name="event_ticket_types")
    op.drop_table("event_ticket_types")

    op.drop_index(
        "uq_organization_stripe_accounts_activa", table_name="organization_stripe_accounts"
    )
    op.drop_index(
        op.f("ix_organization_stripe_accounts_organization_id"),
        table_name="organization_stripe_accounts",
    )
    op.drop_table("organization_stripe_accounts")
