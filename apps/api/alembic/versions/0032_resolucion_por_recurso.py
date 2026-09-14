"""resolución pública por recurso, no por host

Fase 2 del plan «organización sin dominio»
(`plans/260914-0741-organizacion-sin-dominio/plan.md`). Los endpoints
públicos que hoy resuelven la organización por el `Host` de la petición no
pueden seguir haciéndolo: pasan a resolverla desde el propio recurso que
piden (el evento por su slug, la inscripción o la invitación por el `id`
que llevan dentro de su token de un solo uso), igual que ya hace
`checkout_service.iniciar_compra` con `event.organization_id`.

Tres funciones `SECURITY DEFINER` de alcance mínimo, mismo patrón que las
ya existentes (`0004`, `0006`, `0008`, `0028`, `0030`): antes de fijar el
contexto RLS no hay contexto que fijar, así que la propia resolución tiene
que saltárselo con una función de alcance mínimo, nunca abriendo la tabla
entera sin contexto.

- `app_resolve_public_event`: devuelve **solo** `(id, organization_id)`, y
  únicamente si el evento ya cumple las condiciones de "publicable"
  (`published` + `public`) — la comprobación de visibilidad va **dentro**
  de la función, no después (hallazgo S-3 del red-team de la fase 1: un
  evento no publicable no debe ni siquiera revelar que existe por su
  slug).
- `app_resolve_registration_organization`: dado el `id` de una inscripción
  (que ya viene de un token de un solo uso ya verificado — la función no
  añade ninguna comprobación de autorización propia, solo resuelve el
  contexto para la que ya se hizo), devuelve su `organization_id`. La
  reutilizan tanto la verificación/cancelación/promoción de lista de espera
  de inscripciones como la consulta pública de una entrada (`/mi-entrada`),
  que resuelve la misma tabla.
- `app_resolve_invitation_organization`: mismo patrón para invitaciones de
  equipo, dado el `id` que ya viene de su propio token de un solo uso.
- `app_resolve_speaker_organization`: dado el `public_slug` de un perfil de
  ponente (único en toda la instalación desde la fase 0), devuelve su
  `organization_id`. El perfil de ponente no tiene un estado "publicable"
  propio como el evento — la propia existencia de la fila con ese slug ya es
  la condición, igual que antes con el host.

Las cuatro exigen además que la organización siga activa
(`organizations.is_active`): antes de esta fase, `get_current_organization`
(resolución por host) era el único punto que lo comprobaba, y esa
comprobación se habría perdido en todo lo público sin este `EXISTS`
explícito (hallazgo del code-review de la fase 2) — una organización
desactivada no debe seguir sirviendo sus páginas públicas ni admitiendo
inscripciones o invitaciones nuevas.

Revision ID: 0032_resolucion_por_recurso
Revises: 0031_organizacion_activa_sesion
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0032_resolucion_por_recurso"
down_revision: str | None = "0031_organizacion_activa_sesion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCIONES = (
    """
CREATE OR REPLACE FUNCTION app_resolve_public_event(p_slug text)
RETURNS TABLE (id uuid, organization_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT e.id, e.organization_id
  FROM events e
  WHERE e.slug = p_slug
    AND e.status = 'published'
    AND e.visibility = 'public'
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = e.organization_id AND o.is_active)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_resolve_registration_organization(p_registration_id uuid)
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT r.organization_id
  FROM event_registrations r
  WHERE r.id = p_registration_id
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = r.organization_id AND o.is_active)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_resolve_invitation_organization(p_invitation_id uuid)
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT i.organization_id
  FROM organization_invitations i
  WHERE i.id = p_invitation_id
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = i.organization_id AND o.is_active)
$$
    """,
    """
CREATE OR REPLACE FUNCTION app_resolve_speaker_organization(p_public_slug text)
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT p.organization_id
  FROM speaker_public_profiles p
  WHERE p.public_slug = p_public_slug
    AND EXISTS (SELECT 1 FROM organizations o WHERE o.id = p.organization_id AND o.is_active)
$$
    """,
)

_NOMBRES = (
    "app_resolve_public_event(text)",
    "app_resolve_registration_organization(uuid)",
    "app_resolve_invitation_organization(uuid)",
    "app_resolve_speaker_organization(text)",
)


def upgrade() -> None:
    for sentencia in _FUNCIONES:
        op.execute(sentencia)
    for nombre in _NOMBRES:
        op.execute(f"REVOKE ALL ON FUNCTION {nombre} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {nombre} TO app_user")


def downgrade() -> None:
    for nombre in _NOMBRES:
        op.execute(f"DROP FUNCTION IF EXISTS {nombre}")
