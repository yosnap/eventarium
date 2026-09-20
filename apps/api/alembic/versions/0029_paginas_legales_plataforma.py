"""páginas legales solo de plataforma

Decisión del usuario, 2026-09-14: Eventarium es una SaaS centralizada (como
Luma), no un conjunto de instalaciones independientes por organización — así
que es ella quien fija sus condiciones frente a quien se inscribe a
cualquier evento, no cada organización por separado. Se retira la
posibilidad de que una organización edite su propio aviso legal, política
de privacidad, política de cookies o condiciones de inscripción
(`/organizations/me/legal-pages`, fase 5 del PRD original); a partir de
aquí las cuatro páginas legales son siempre las de plataforma
(`/admin/legales`), incluidas las condiciones de inscripción, que hasta
ahora quedaban fuera a propósito por ser "un contrato de la organización".

Se retiran también `legal_address` y `tax_id` de `organizations`: solo
existían para rellenar las plantillas legales por organización
(migración `0012`) y no los usa ninguna otra función (contabilidad,
facturación) — comprobado por grep antes de esta migración.

Sin backfill de contenido: cualquier texto que una organización hubiera
personalizado se pierde (aceptado, es la propia decisión). Los cuatro
campos de `organizations` quedan disponibles para quien tenga la base de
datos de antes por si hiciera falta rescatar algo a mano antes de subir
esta migración; después de aplicarla, no.

Revision ID: 0029_paginas_legales_plataforma
Revises: 0028_estado_de_cuenta_invitada
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_paginas_legales_plataforma"
down_revision: str | None = "0028_estado_de_cuenta_invitada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNAS_DE_ORGANIZATION = (
    "legal_address",
    "tax_id",
    "legal_notice_content",
    "privacy_policy_content",
    "cookies_policy_content",
    "registration_terms_content",
)


def upgrade() -> None:
    op.drop_constraint("ck_platform_legal_pages_kind", "platform_legal_pages", type_="check")
    op.create_check_constraint(
        "ck_platform_legal_pages_kind",
        "platform_legal_pages",
        "kind IN ('aviso-legal', 'privacidad', 'cookies', 'condiciones-de-inscripcion')",
    )

    for columna in _COLUMNAS_DE_ORGANIZATION:
        op.drop_column("organizations", columna)


def downgrade() -> None:
    op.add_column("organizations", sa.Column("legal_address", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("tax_id", sa.String(length=40), nullable=True))
    op.add_column("organizations", sa.Column("legal_notice_content", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("privacy_policy_content", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("cookies_policy_content", sa.Text(), nullable=True))
    op.add_column(
        "organizations", sa.Column("registration_terms_content", sa.Text(), nullable=True)
    )

    op.drop_constraint("ck_platform_legal_pages_kind", "platform_legal_pages", type_="check")
    op.create_check_constraint(
        "ck_platform_legal_pages_kind",
        "platform_legal_pages",
        "kind IN ('aviso-legal', 'privacidad', 'cookies')",
    )
