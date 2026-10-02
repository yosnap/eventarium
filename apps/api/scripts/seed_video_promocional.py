"""Organización de demostración para el vídeo promocional (fabrica-videos).

Crea una organización ficticia, «Cumbre Digital Valencia», con una propietaria inventada y le
siembra el catálogo de eventos de demostración (`scripts.seed_eventos_demo`). Así las capturas del
vídeo nunca enseñan datos de una organización real ni de producción.

La contraseña de la propietaria se lee de `EVENTARIUM_VIDEO_CLAVE` (la guarda fabrica-videos en su
fichero de entorno) y se fija en cada ejecución; nunca se imprime.

Idempotente: cada paso busca por su clave natural antes de crear.

Uso:
    cd apps/api && EVENTARIUM_VIDEO_CLAVE=… uv run python -m scripts.seed_video_promocional
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import maintenance_session
from app.core.security import hash_password
from app.modules.accounting.models import AccountingBudgetLine, AccountingExpense, AccountingIncome
from app.modules.events.models import Event
from app.modules.organizations import service
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.registrations.models import EventRegistration
from app.modules.roles.models import Role
from app.modules.roles.system_roles import OWNER_KEY
from app.modules.users.models import User
from scripts.seed_eventos_demo.__main__ import main as sembrar_eventos
from scripts.seed_eventos_demo.datos import PERSONAS

SLUG = "cumbre-digital"
NOMBRE = "Cumbre Digital Valencia"
CORREO_PROPIETARIA = "laura.martin.video@example.com"
EVENTO_ESTRELLA = "demo-completo-presencial"

# Inscritos inventados (dominio reservado .test) para la tabla de inscripciones.
INSCRITOS = (
    "Alba Navarro",
    "Bruno Sanz",
    "Carla Gil",
    "David Ortega",
    "Eva Molina",
    "Fran Castillo",
    "Gema Rubio",
    "Héctor Iglesias",
    "Irene Prieto",
    "Javier Lozano",
    "Kiara Benítez",
    "Luis Herrero",
    "Marta Pascual",
    "Nacho Vega",
    "Olga Cano",
    "Pablo Ferrer",
    "Raquel Soler",
    "Sergio Domínguez",
    "Tania Crespo",
    "Unai Marín",
    "Vera Campos",
    "Xavi Peña",
    "Yaiza Fuentes",
    "Zoe Calvo",
)
# (días atrás, concepto, importe en céntimos): suman más que los gastos.
INGRESOS = (
    (5, "Subvención Ayuntamiento (ficticia)", 900_000),
    (12, "Subvención Generalitat (ficticia)", 600_000),
)
# (partida, presupuesto en céntimos, proveedor, base del gasto, IVA)
CONTABILIDAD = (
    ("Sala y montaje", 600_000, "Palacio de Congresos (ficticio)", 520_000, 109_200),
    ("Catering", 450_000, "Catering Mediterráneo (ficticio)", 390_000, 39_000),
    ("Ponentes y viajes", 300_000, "Viajes Turia (ficticio)", 118_000, 11_800),
    ("Comunicación", 150_000, "Imprenta Levante (ficticia)", 64_000, 13_440),
)


async def crear_organizacion(clave: str) -> None:
    async with maintenance_session() as session:
        organizacion = await session.scalar(select(Organization).where(Organization.slug == SLUG))
        if organizacion is None:
            organizacion = await service.create_organization(
                session,
                slug=SLUG,
                name=NOMBRE,
                legal_name="Asociación Cumbre Digital Valencia",
                contact_email="hola@example.com",
            )
        rol_owner = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == OWNER_KEY)
        )
        if rol_owner is None:
            rol_owner = (await service.clone_system_roles(session, organizacion.id))[OWNER_KEY]

        usuaria = await session.scalar(select(User).where(User.email == CORREO_PROPIETARIA))
        if usuaria is None:
            usuaria = User(
                email=CORREO_PROPIETARIA,
                first_name="Laura",
                last_name="Martín",
                password_hash=hash_password(clave),
                is_active=True,
                is_superadmin=False,
            )
            session.add(usuaria)
            await session.flush()
        else:
            usuaria.password_hash = hash_password(clave)
        # Sin verificar, todo el panel enseña un aviso que taparía las capturas.
        usuaria.email_verified_at = usuaria.email_verified_at or datetime.now(UTC)

        membresia = await session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organizacion.id,
                OrganizationMember.user_id == usuaria.id,
            )
        )
        if membresia is None:
            session.add(
                OrganizationMember(
                    organization_id=organizacion.id,
                    user_id=usuaria.id,
                    role_id=rol_owner.id,
                    profile_data={},
                )
            )
        await session.flush()


def _correo(nombre: str) -> str:
    sin_tildes = nombre.lower().translate(str.maketrans("áéíóúñ", "aeioun"))
    return f"{sin_tildes.replace(' ', '.')}@example.test"


async def completar_evento_estrella() -> None:
    """Inscritos y contabilidad del evento estrella, para que esas pantallas no salgan vacías."""
    async with maintenance_session() as session:
        organizacion = await session.scalar(select(Organization).where(Organization.slug == SLUG))
        if organizacion is None:
            raise RuntimeError(f"Falta la organización «{SLUG}».")
        evento = await session.scalar(
            select(Event).where(
                Event.organization_id == organizacion.id, Event.slug == EVENTO_ESTRELLA
            )
        )
        if evento is None:
            raise RuntimeError(f"Falta el evento «{EVENTO_ESTRELLA}» en «{SLUG}».")
        ahora = datetime.now(UTC)
        existentes = set(
            await session.scalars(
                select(EventRegistration.email).where(EventRegistration.event_id == evento.id)
            )
        )
        for i, nombre in enumerate(INSCRITOS):
            correo = _correo(nombre)
            if correo in existentes:
                continue
            estado = "cancelled" if i >= 22 else "waitlisted" if i >= 20 else "confirmed"
            momento = ahora - timedelta(days=30 - i)
            session.add(
                EventRegistration(
                    event_id=evento.id,
                    organization_id=organizacion.id,
                    email=correo,
                    full_name=nombre,
                    status=estado,
                    verified_at=momento,
                    confirmed_at=momento if estado == "confirmed" else None,
                    cancelled_at=momento if estado == "cancelled" else None,
                    waitlist_position=(i - 19) if estado == "waitlisted" else None,
                )
            )

        for orden, (partida, presupuesto, proveedor, base, iva) in enumerate(CONTABILIDAD):
            linea = await session.scalar(
                select(AccountingBudgetLine).where(
                    AccountingBudgetLine.event_id == evento.id, AccountingBudgetLine.name == partida
                )
            )
            if linea is None:
                linea = AccountingBudgetLine(
                    event_id=evento.id,
                    organization_id=organizacion.id,
                    name=partida,
                    budgeted_cents=presupuesto,
                    sort_order=orden,
                )
                session.add(linea)
                await session.flush()
            gasto = await session.scalar(
                select(AccountingExpense).where(
                    AccountingExpense.event_id == evento.id,
                    AccountingExpense.provider_name == proveedor,
                )
            )
            if gasto is None:
                session.add(
                    AccountingExpense(
                        event_id=evento.id,
                        organization_id=organizacion.id,
                        budget_line_id=linea.id,
                        provider_name=proveedor,
                        expense_date=ahora - timedelta(days=10 + orden),
                        base_cents=base,
                        vat_cents=iva,
                        total_cents=base + iva,
                    )
                )
        # Cubren los gastos: el evento de demo cierra en positivo. El importe se fija en cada
        # ejecución para que la cifra del vídeo no dependa de siembras anteriores.
        for dias, concepto, importe in INGRESOS:
            ingreso = await session.scalar(
                select(AccountingIncome).where(
                    AccountingIncome.event_id == evento.id, AccountingIncome.concept == concepto
                )
            )
            if ingreso is None:
                session.add(
                    AccountingIncome(
                        event_id=evento.id,
                        organization_id=organizacion.id,
                        origin="subvencion",
                        concept=concepto,
                        amount_cents=importe,
                        status="collected",
                        collected_at=ahora - timedelta(days=dias),
                    )
                )
            else:
                ingreso.amount_cents = importe
        await session.flush()


def slugs_propios_de_ponente() -> None:
    """El perfil público de ponente tiene un slug único en toda la instalación y el catálogo ya los
    usa en la organización de demostración principal: aquí llevan un sufijo propio."""
    for persona in PERSONAS:
        if persona.get("slug") and not persona["slug"].endswith(f"-{SLUG}"):
            persona["slug"] = f"{persona['slug']}-{SLUG}"


async def main() -> None:
    # Datos ficticios para capturas: nunca en la base de producción.
    if get_settings().app_env == "production":
        raise SystemExit("seed_video_promocional no se ejecuta en producción (APP_ENV=production).")
    clave = os.environ.get("EVENTARIUM_VIDEO_CLAVE", "")
    if len(clave) < 12:
        raise SystemExit("Falta EVENTARIUM_VIDEO_CLAVE (mínimo 12 caracteres) en el entorno.")
    await crear_organizacion(clave)
    slugs_propios_de_ponente()
    await sembrar_eventos(SLUG)
    await completar_evento_estrella()
    print(f"Organización «{NOMBRE}» lista; propietaria {CORREO_PROPIETARIA}.")


if __name__ == "__main__":
    asyncio.run(main())
