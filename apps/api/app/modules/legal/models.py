"""Modelo de registro de consentimiento de cookies.

Fase 5 del PRD, fase 1 de trabajo. `CookieConsent` es anónimo por diseño
(decisión #3 del plan): RGPD no exige identificar a la persona que
acepta/rechaza cookies, es la decisión de un navegador, no un consentimiento
de inscripción con datos personales asociados (a diferencia de
`EventRegistrationConsent`, fase 3, que sí liga el consentimiento a una
persona identificada).

Sin `user_id`, sin email, sin IP ni hash de IP en ninguna forma — un hash sin
sal sobre un espacio de IPv4 truncado es reversible por fuerza bruta en
segundos, no es anonimización. `(organization_id, categorías, timestamp)`
basta para probar que se pidió consentimiento.

**Sin política RLS y sin el acceso por defecto de `app_user`.** La migración
`0012_patrocinadores_legal_y_auditoria` ejecuta `REVOKE ALL ON
cookie_consents FROM app_user` seguido de `GRANT INSERT ON cookie_consents TO
app_user`: el endpoint público de consentimiento (fase 3 de trabajo) escribe
aquí desde una sesión sin autenticar, pero no puede leer ni borrar filas
ajenas ni propias.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.identifiers import new_uuid7


class CookieConsent(Base):
    """Una decisión del banner de cookies (aceptar/rechazar/personalizar)."""

    __tablename__ = "cookie_consents"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_uuid7)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Lista de categorías aceptadas, ej. `["necessary", "analytics"]`.
    # `necessary` siempre presente (el propio banner la marca como no
    # opcional); `analytics`/`marketing` solo si se aceptaron explícitamente.
    categories_accepted: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
