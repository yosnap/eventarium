"""estado en_extraccion para los borradores de gasto

Añade `en_extraccion` al `CHECK` de `status` de `accounting_expense_drafts`.

Sin este estado intermedio, `_reservar_intento` cuenta el intento y deja el
borrador en `pending_extraction` mientras dura la llamada al modelo de
visión: una segunda invocación de `extraer_campos_task` para el mismo
`draft_id` (una entrega duplicada de la cola, o el barrido de atascados
reencolando uno que en realidad solo estaba esperando turno en una cola con
retraso) pasa el mismo guardián de estado sin bloquear nada, y ambas acaban
llamando al proveedor de pago por el mismo documento.

Con `en_extraccion`, `_reservar_intento` lo escribe dentro de la misma
transacción bloqueada (`SELECT ... FOR UPDATE`) que cuenta el intento: la
segunda invocación, al adquirir el candado tras la primera, lee el estado ya
cambiado y no reserva. El barrido de atascados pasa a vigilar **dos**
señales de atasco, no una: `pending_extraction` con `updated_at` viejo (la
tarea nunca llegó a arrancar — se perdió de la cola) y `en_extraccion` con
`updated_at` viejo (arrancó y el worker murió a mitad).

Revision ID: 0051_ocr_draft_en_extraccion
Revises: 0050_ocr_draft_error_code
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0051_ocr_draft_en_extraccion"
down_revision: str | None = "0050_ocr_draft_error_code"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_ANTERIOR = (
    "status IN ('pending_extraction', 'pending_review', 'extraction_failed', "
    "'confirmed', 'discarded')"
)
_CHECK_NUEVO = (
    "status IN ('pending_extraction', 'en_extraccion', 'pending_review', "
    "'extraction_failed', 'confirmed', 'discarded')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_accounting_expense_drafts_status", "accounting_expense_drafts", type_="check"
    )
    op.create_check_constraint(
        "ck_accounting_expense_drafts_status", "accounting_expense_drafts", _CHECK_NUEVO
    )


def downgrade() -> None:
    op.execute(
        "UPDATE accounting_expense_drafts SET status = 'pending_extraction' "
        "WHERE status = 'en_extraccion'"
    )
    op.drop_constraint(
        "ck_accounting_expense_drafts_status", "accounting_expense_drafts", type_="check"
    )
    op.create_check_constraint(
        "ck_accounting_expense_drafts_status", "accounting_expense_drafts", _CHECK_ANTERIOR
    )
