"""Índice por created_at en cookie_consents

Hallazgo de red-team del plan `260916-2246-cookies-analitica-externa`:
`agregados_de_consentimiento` (`app/modules/admin/analytics_service.py`)
filtra `cookie_consents` por `created_at` en rangos de hasta 366 días, sin
ningún índice que lo apoye — solo existe `ix_cookie_consents_organization_id`
(`0012`), y esa consulta no filtra por organización. Sin índice, cada carga
del panel de analítica es un seq scan completo sobre la tabla que más crece
del sistema (una fila por decisión de banner de cada visitante).

Sin `CONCURRENTLY`: la instalación está en fase de desarrollo, sin volumen
real todavía, así que el bloqueo breve de un `CREATE INDEX` normal es
aceptable — más simple que gestionar el bloque autocommit que exige
`CONCURRENTLY` fuera de una transacción. Revisar si conviene cambiarlo antes
de un primer despliegue con tráfico real.

Revision ID: 0046_indice_cookie_consents
Revises: 0045_event_theme_overrides
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0046_indice_cookie_consents"
down_revision: str | None = "0045_event_theme_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_cookie_consents_created_at",
        "cookie_consents",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cookie_consents_created_at", table_name="cookie_consents")
