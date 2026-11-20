"""IA de plataforma para su propio contenido

- `platform_ai_usage`: uso de IA de la propia plataforma (traducir el legal y las
  categorías), aparte del de las organizaciones. Sin organización y sin RLS: solo
  la escribe el rol de mantenimiento.
- `platform_ai_settings`: tope mensual en USD y máximo de llamadas al día de esa
  traducción. Obligatorios: no hay «sin tope».
- `platform_legal_pages`: origen, estado y huella de cada versión traducida, como
  `content_translations`, y espera tras errores.
- `event_categories.name_i18n_origin`: quién escribió el nombre en cada idioma
  (`ia` o `manual`), para que la IA no pise lo escrito a mano.

Revision ID: 0077_ia_plataforma
Revises: 0076_legal_plataforma_idioma
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0077_ia_plataforma"
down_revision: str | None = "0076_legal_plataforma_idioma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USO = "platform_ai_usage"
_LEGAL = "platform_legal_pages"


def upgrade() -> None:
    op.create_table(
        _USO,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("use_case", sa.String(60), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("cost_auditable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_platform_ai_usage"),
        sa.CheckConstraint("status IN ('reservado', 'liquidado', 'fallido')", name="status"),
    )
    op.create_index("ix_platform_ai_usage_created_at", _USO, ["created_at"])
    op.execute(f"REVOKE ALL ON {_USO} FROM app_user")

    op.add_column(
        "platform_ai_settings",
        sa.Column(
            "translation_monthly_cap_usd",
            sa.Numeric(14, 6),
            nullable=False,
            server_default="5",
        ),
    )
    op.add_column(
        "platform_ai_settings",
        sa.Column("translation_daily_calls", sa.Integer(), nullable=False, server_default="200"),
    )
    op.create_check_constraint(
        "translation_monthly_cap_usd",
        "platform_ai_settings",
        "translation_monthly_cap_usd > 0",
    )
    op.create_check_constraint(
        "translation_daily_calls", "platform_ai_settings", "translation_daily_calls > 0"
    )

    op.add_column(_LEGAL, sa.Column("origin", sa.String(10), nullable=True))
    op.add_column(_LEGAL, sa.Column("status", sa.String(20), nullable=True))
    op.add_column(_LEGAL, sa.Column("source_hash", sa.String(64), nullable=True))
    op.add_column(
        _LEGAL, sa.Column("error_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(_LEGAL, sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "origin", _LEGAL, "origin IS NULL OR origin IN ('ia', 'manual', 'revisada')"
    )
    op.create_check_constraint(
        "status",
        _LEGAL,
        "status IS NULL OR status IN ('pendiente', 'en_curso', 'al_dia', 'error')",
    )
    # Las versiones en otro idioma que ya existan se escribieron a mano; sin huella,
    # se tratan como desfasadas hasta que se revisen o se vuelvan a guardar.
    op.execute(
        f"UPDATE {_LEGAL} SET origin = 'manual', status = 'al_dia' "
        "WHERE locale <> 'es-ES' AND content IS NOT NULL"
    )

    op.add_column(
        "event_categories",
        sa.Column(
            "name_i18n_origin",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Los nombres que ya había los escribió el superadmin.
    op.execute(
        "UPDATE event_categories SET name_i18n_origin = "
        "(SELECT COALESCE(jsonb_object_agg(clave, 'manual'), '{}'::jsonb) "
        "FROM jsonb_object_keys(name_i18n) AS clave)"
    )


def downgrade() -> None:
    # El esquema anterior sirve cualquier versión con texto: las de la IA sin revisar
    # y las desfasadas no deben quedar publicadas como si se hubieran escrito a mano.
    op.execute(
        f"DELETE FROM {_LEGAL} WHERE locale <> 'es-ES' AND (origin IS DISTINCT FROM 'manual' "
        "OR status IS DISTINCT FROM 'al_dia' OR source_hash IS NULL)"
    )
    op.drop_column("event_categories", "name_i18n_origin")
    for columna in ("retry_after", "error_count", "source_hash", "status", "origin"):
        op.execute(f"ALTER TABLE {_LEGAL} DROP COLUMN IF EXISTS {columna}")
    op.execute("ALTER TABLE platform_ai_settings DROP COLUMN IF EXISTS translation_daily_calls")
    op.execute("ALTER TABLE platform_ai_settings DROP COLUMN IF EXISTS translation_monthly_cap_usd")
    op.drop_index("ix_platform_ai_usage_created_at", table_name=_USO)
    op.drop_table(_USO)
