"""Barrido periódico de cuentas nunca verificadas.

Lo ejecuta el proceso `scheduler` (Taskiq), no el `worker`: son procesos separados
desde Taskiq 0.12, confirmado por spike durante la fase 2 (`TaskiqScheduler` corre en
su propio proceso). Aviso a los 5 días desde el registro, borrado a los 7 — ambos
filtran por `email_verified_at IS NULL`, apoyados en el índice parcial de la fase 1
para no recorrer la tabla entera.

Usa `maintenance_session`, no una petición HTTP: no hay `Request` del que resolver una
organización, y de hecho el barrido es intencionadamente transversal a todas. Mismo
patrón que ya usan `app/cli.py` y `app/seed/demo.py` para tareas administrativas fuera
del ciclo de petición.

Fase 5 del plan de invitaciones detectó que este barrido también alcanzaba a las
cuentas creadas por `create_invitation` para un correo sin cuenta previa: esas
cuentas nacen con `email_verified_at IS NULL` igual que un registro abandonado, y
`TTL_INVITACION` (7 días) coincide con el plazo de borrado, así que quien tardaba
5 días en aceptar recibía el aviso de «tu cuenta se va a eliminar» sin tener
ninguna verificación de correo pendiente, y quien tardaba 7 podía perder la cuenta
antes de aceptar. Ambas consultas excluyen ahora a cualquier correo con una
invitación `pendiente` todavía no caducada: en cuanto esa invitación caduca, la
cuenta vuelve a ser candidata al barrido con normalidad.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.database import maintenance_session
from app.core.email import get_email_provider

logger = logging.getLogger(__name__)


async def sweep_unverified_accounts() -> None:
    """Avisa a los 5 días y borra a los 7. Idempotente: solo avisa una vez."""
    async with maintenance_session() as session:
        pendientes_de_aviso = (
            await session.execute(
                text(
                    "SELECT id, email FROM users "
                    "WHERE email_verified_at IS NULL "
                    "  AND verification_warning_sent_at IS NULL "
                    "  AND created_at <= now() - interval '5 days' "
                    "  AND NOT EXISTS ("
                    "    SELECT 1 FROM organization_invitations oi "
                    "    WHERE oi.email = users.email "
                    "      AND oi.estado = 'pendiente' "
                    "      AND oi.expires_at > now()"
                    "  )"
                )
            )
        ).all()

        for user_id, email in pendientes_de_aviso:
            try:
                await get_email_provider().send(
                    to=email,
                    subject="Tu cuenta se eliminará en 2 días si no verificas tu correo",
                    body=(
                        "Hola,\n\n"
                        "Creaste una cuenta hace 5 días y tu correo sigue sin verificar. "
                        "Si no lo verificas en los próximos 2 días, la cuenta se eliminará "
                        "automáticamente.\n\n"
                        "Si no fuiste tú, no hace falta que hagas nada: se eliminará sola."
                    ),
                )
            except Exception:
                # Un fallo de envío no debe bloquear el resto del barrido; se
                # reintentará en la siguiente pasada, dentro de los 2 días de margen.
                logger.exception("No se pudo enviar el aviso de cuenta sin verificar a %s", email)
                continue
            await session.execute(
                text("UPDATE users SET verification_warning_sent_at = now() WHERE id = :id"),
                {"id": user_id},
            )
        await session.commit()

        borradas = (
            await session.execute(
                text(
                    "DELETE FROM users "
                    "WHERE email_verified_at IS NULL AND created_at <= now() - interval '7 days' "
                    "  AND NOT EXISTS ("
                    "    SELECT 1 FROM organization_invitations oi "
                    "    WHERE oi.email = users.email "
                    "      AND oi.estado = 'pendiente' "
                    "      AND oi.expires_at > now()"
                    "  ) "
                    "RETURNING email"
                )
            )
        ).all()
        await session.commit()
        if borradas:
            logger.info("Cuentas no verificadas eliminadas por caducidad: %s", len(borradas))
