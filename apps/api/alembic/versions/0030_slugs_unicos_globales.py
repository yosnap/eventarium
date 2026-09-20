"""slugs únicos en toda la instalación

Decisión del usuario, 2026-09-14: las organizaciones dejan de tener dominio
propio (`plans/260914-0741-organizacion-sin-dominio/plan.md`). Sin un host
que ya distinga "el evento `charlas` de acme" del "evento `charlas` de otra
organización", el slug de un evento y el `public_slug` de un ponente tienen
que ser únicos en toda la instalación, no solo dentro de su organización —
van a ser la única forma de resolver esos recursos en una URL pública.

Antes de tocar las constraints, se comprueba que no exista ya una colisión
real entre organizaciones distintas: si la hubiera, la migración falla con la
lista exacta de slugs en conflicto en vez de renombrar o fusionar nada a
ciegas (comprobado en la base de datos de desarrollo actual: cero colisiones
hoy, riesgo es solo de producción futura, ver
`plans/260914-0741-organizacion-sin-dominio/reports/predict.md`).

También se añade `app_check_public_slug_available`, `SECURITY DEFINER` igual
que la ya existente `app_check_slug_available` de organizaciones (migración
`0006`): con el slug ahora global, el `check-slug` de perfil de ponente
(`/users/me/public-profile/check-slug`) no puede seguir comprobando solo
dentro de la organización de quien pregunta bajo RLS normal, porque RLS le
impide ver perfiles de otras organizaciones.

Nota de acoplamiento: `downgrade()` borra `app_check_public_slug_available`.
Si la base de datos baja de versión sin desplegar a la vez el código anterior
a esta migración, `check_public_slug` (que la invoca) responde 500
(`UndefinedFunction`) hasta que ambos vuelvan a estar sincronizados — no es un
problema de integridad de datos, solo de despliegue.

Revision ID: 0030_slugs_unicos_globales
Revises: 0029_paginas_legales_plataforma
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030_slugs_unicos_globales"
down_revision: str | None = "0029_paginas_legales_plataforma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMPROBACION_EVENTS = """
DO $$
DECLARE
    conflictos text;
BEGIN
    SELECT string_agg(DISTINCT slug, ', ') INTO conflictos
    FROM (
        SELECT slug FROM events GROUP BY slug HAVING count(*) > 1
    ) duplicados;
    IF conflictos IS NOT NULL THEN
        RAISE EXCEPTION
            'No se puede aplicar la migración 0030: hay slugs de evento repetidos entre organizaciones distintas: %',
            conflictos;
    END IF;
END $$;
"""

_COMPROBACION_SPEAKER_PUBLIC_PROFILES = """
DO $$
DECLARE
    conflictos text;
BEGIN
    SELECT string_agg(DISTINCT public_slug, ', ') INTO conflictos
    FROM (
        SELECT public_slug FROM speaker_public_profiles GROUP BY public_slug HAVING count(*) > 1
    ) duplicados;
    IF conflictos IS NOT NULL THEN
        RAISE EXCEPTION
            'No se puede aplicar la migración 0030: hay public_slug de ponente repetidos entre organizaciones distintas: %',
            conflictos;
    END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(_COMPROBACION_EVENTS)
    op.execute(_COMPROBACION_SPEAKER_PUBLIC_PROFILES)

    op.drop_constraint("uq_events_organization_id_slug", "events", type_="unique")
    op.create_unique_constraint("uq_events_slug", "events", ["slug"])

    op.drop_constraint(
        "uq_speaker_public_profiles_organization_id_public_slug",
        "speaker_public_profiles",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_speaker_public_profiles_public_slug", "speaker_public_profiles", ["public_slug"]
    )

    op.execute(
        """
CREATE OR REPLACE FUNCTION app_check_public_slug_available(p_slug text)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT NOT EXISTS (
    SELECT 1 FROM speaker_public_profiles WHERE public_slug = lower(p_slug)
  )
$$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_check_public_slug_available(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_check_public_slug_available(text) TO app_user")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_check_public_slug_available(text)")

    op.drop_constraint("uq_speaker_public_profiles_public_slug", "speaker_public_profiles")
    op.create_unique_constraint(
        "uq_speaker_public_profiles_organization_id_public_slug",
        "speaker_public_profiles",
        ["organization_id", "public_slug"],
    )

    op.drop_constraint("uq_events_slug", "events")
    op.create_unique_constraint(
        "uq_events_organization_id_slug", "events", ["organization_id", "slug"]
    )
