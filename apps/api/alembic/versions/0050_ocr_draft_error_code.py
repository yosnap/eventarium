"""motivo del fallo y pagina rasterizada de los borradores de gasto

Añade `error_code` a `accounting_expense_drafts`: por qué falló la extracción
de un justificante. Sin esta columna, el barrido de extracciones atascadas no
puede distinguir «se agotó el presupuesto de IA» (recuperable en cuanto se
amplía el límite, y que **no** debe reintentarse por tiempo: con el límite
agotado cada pasada consumiría una reserva y la quemaría) de un fallo técnico
definitivo.

Sin `CHECK` a propósito, a diferencia de `ai_usage_records.error_code`: la
taxonomía vive en `app/modules/ai_gateway/errores.py` y duplicarla aquí
acoplaría los dos módulos por esquema y obligaría a una migración cada vez que
se ampliara. Se valida en el servicio, que ya importa esa taxonomía.

Nullable y sin backfill: `NULL` es «no ha fallado», el estado de todo borrador
existente.

Añade también `rasterized_object_key`: la clave de la imagen que se envió al
motor de visión, guardada junto al original en el mismo prefijo privado. El
original se conserva tal cual para descargarlo, y la pantalla de revisión
previsualiza exactamente lo que se envió sin volver a rasterizar. Sin esta
columna la clave no es deducible (la construye `build_object_key` con un UUID
propio) y habría que rasterizar otra vez en cada visita.

Revision ID: 0050_ocr_draft_error_code
Revises: 0049_uso_de_ia
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0050_ocr_draft_error_code"
down_revision: str | None = "0049_uso_de_ia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounting_expense_drafts",
        sa.Column("error_code", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "accounting_expense_drafts",
        sa.Column("rasterized_object_key", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("accounting_expense_drafts", "rasterized_object_key")
    op.drop_column("accounting_expense_drafts", "error_code")
