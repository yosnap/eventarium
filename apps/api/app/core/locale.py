"""Catálogo de idiomas soportados por la cuenta de usuario.

Vive en `app.core`, no en `app.modules.users.schemas` (dueño natural de la columna
`users.locale`): `users.schemas` ya importa de `organizations.schemas`
(`SLUG_PATTERN`, `PublicOrganizationRef`), así que si el alias viviera en `users.schemas`,
que `organizations.schemas` lo importara de vuelta (fase 2, `InvitationAcceptRequest`)
cerraría un ciclo. `app.core` es el único punto neutral que `auth`, `organizations` y
`users` ya pueden importar sin crear una dependencia nueva entre módulos de dominio —
mismo patrón que `Environment` en `app.core.config`.

Espejo en el frontend: `apps/web/src/app/core/i18n/locale-de-cuenta.ts`
(`LOCALES_DE_CUENTA`). Ampliar los dos a la vez.
"""

from __future__ import annotations

from typing import Literal

Locale = Literal["es-ES", "en-US"]
DEFAULT_LOCALE: Locale = "es-ES"
