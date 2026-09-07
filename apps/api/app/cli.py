"""Herramientas de línea de comandos.

Todas usan el rol `app_maintainer`: son operaciones transversales (alta de
organización, superadmin, seed) que por definición ocurren fuera del contexto de un
tenant. Ejecutar con `python -m app.cli <comando>`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from sqlalchemy import select

from app.core.database import maintenance_session
from app.core.security import generate_password, hash_password
from app.modules.organizations import service
from app.modules.users.models import User
from app.seed.demo import seed_demo

app = typer.Typer(help="Utilidades de administración de la API de IA Week.", no_args_is_help=True)


@app.command()
def seed(
    reset_password: bool = typer.Option(
        False, "--reset-password", help="Regenera la contraseña del usuario propietario."
    ),
) -> None:
    """Carga los datos de demostración (idempotente)."""

    async def _ejecutar() -> None:
        async with maintenance_session() as session:
            resultado = await seed_demo(session, reset_password=reset_password)

        typer.echo(f"Organización: {resultado.organization_slug} (nueva: {resultado.created})")
        typer.echo(f"Usuario propietario: {resultado.owner_email}")
        if resultado.owner_password:
            typer.secho(
                f"Contraseña generada: {resultado.owner_password}",
                fg=typer.colors.YELLOW,
                bold=True,
            )
            typer.echo("Guárdala ahora: no se vuelve a mostrar.")
        else:
            typer.echo("La contraseña no ha cambiado (usa --reset-password para regenerarla).")

    asyncio.run(_ejecutar())


@app.command("create-organization")
def create_organization(
    slug: str = typer.Argument(..., help="Identificador corto, en minúsculas."),
    name: str = typer.Argument(..., help="Nombre visible."),
    host: str = typer.Argument(..., help="Dominio principal, por ejemplo eventos.example.com."),
    contact_email: str | None = typer.Option(None, help="Correo de contacto."),
) -> None:
    """Crea una organización con su dominio, branding y roles clonados."""

    async def _ejecutar() -> None:
        async with maintenance_session() as session:
            organizacion = await service.create_organization(
                session, slug=slug, name=name, host=host, contact_email=contact_email
            )
            typer.echo(f"Organización creada: {organizacion.slug} ({organizacion.id})")

    asyncio.run(_ejecutar())


@app.command("add-domain")
def add_domain(
    slug: str = typer.Argument(..., help="Identificador de la organización."),
    host: str = typer.Argument(..., help="Dominio a añadir."),
    primary: bool = typer.Option(False, "--primary", help="Marcarlo como dominio principal."),
) -> None:
    """Añade un dominio a una organización existente."""

    async def _ejecutar() -> None:
        from app.modules.organizations.models import Organization

        async with maintenance_session() as session:
            organizacion = await session.scalar(
                select(Organization).where(Organization.slug == slug)
            )
            if organizacion is None:
                typer.secho(f"No existe la organización «{slug}».", fg=typer.colors.RED)
                raise typer.Exit(code=1)
            dominio = await service.add_domain(
                session, organization_id=organizacion.id, host=host, is_primary=primary
            )
            typer.echo(f"Dominio añadido: {dominio.host}")

    asyncio.run(_ejecutar())


@app.command("create-superadmin")
def create_superadmin(
    email: str = typer.Argument(..., help="Correo del superadministrador."),
    first_name: str = typer.Option("Super", help="Nombre."),
    last_name: str = typer.Option("Administrador", help="Apellidos."),
    password: str | None = typer.Option(
        None, help="Contraseña. Si se omite, se genera una y se muestra."
    ),
) -> None:
    """Crea o promociona a superadministrador de la instalación."""

    async def _ejecutar() -> None:
        correo = email.strip().lower()
        async with maintenance_session() as session:
            usuario = await session.scalar(select(User).where(User.email == correo))
            secreto = password or generate_password()
            if usuario is None:
                usuario = User(
                    email=correo,
                    first_name=first_name,
                    last_name=last_name,
                    password_hash=hash_password(secreto),
                    is_active=True,
                    is_superadmin=True,
                )
                session.add(usuario)
                typer.echo(f"Superadministrador creado: {correo}")
            else:
                usuario.is_superadmin = True
                usuario.password_hash = hash_password(secreto)
                typer.echo(f"Usuario promocionado a superadministrador: {correo}")
            typer.secho(f"Contraseña: {secreto}", fg=typer.colors.YELLOW, bold=True)

    asyncio.run(_ejecutar())


@app.command("export-openapi")
def export_openapi(
    destino: Path = typer.Option(Path("openapi.json"), help="Fichero de salida."),
) -> None:
    """Exporta el esquema OpenAPI para generar los tipos del frontend."""
    from app.main import create_app

    esquema = create_app().openapi()
    destino.write_text(json.dumps(esquema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    typer.echo(f"OpenAPI exportado a {destino}")


if __name__ == "__main__":
    app()
