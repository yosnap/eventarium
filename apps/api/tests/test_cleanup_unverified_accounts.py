"""Barrido de cuentas nunca verificadas: aviso a los 5 días, borrado a los 7."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cleanup import sweep_unverified_accounts
from app.modules.users.models import User


async def _crear_usuario_sin_verificar(
    maintenance_db: AsyncSession, *, email: str, antiguedad: timedelta, avisado: bool = False
) -> None:
    creado_en = datetime.now(UTC) - antiguedad
    usuario = User(email=email, is_active=True)
    maintenance_db.add(usuario)
    await maintenance_db.flush()
    await maintenance_db.execute(
        text(
            "UPDATE users SET created_at = :creado, "
            "verification_warning_sent_at = :avisado WHERE id = :id"
        ),
        {
            "creado": creado_en,
            "avisado": datetime.now(UTC) if avisado else None,
            "id": usuario.id,
        },
    )
    await maintenance_db.commit()


async def test_avisa_a_los_5_dias_y_no_antes(maintenance_db: AsyncSession) -> None:
    await _crear_usuario_sin_verificar(
        maintenance_db, email="cinco-dias@example.com", antiguedad=timedelta(days=5, hours=1)
    )
    await _crear_usuario_sin_verificar(
        maintenance_db, email="tres-dias@example.com", antiguedad=timedelta(days=3)
    )

    with patch("app.core.cleanup.get_email_provider") as proveedor_falso:
        envio = AsyncMock()
        proveedor_falso.return_value.send = envio
        await sweep_unverified_accounts()

    destinatarios = {llamada.kwargs["to"] for llamada in envio.await_args_list}
    assert destinatarios == {"cinco-dias@example.com"}

    avisado = await maintenance_db.scalar(
        select(User.verification_warning_sent_at).where(User.email == "cinco-dias@example.com")
    )
    assert avisado is not None


async def test_no_reenvia_el_aviso_ya_mandado(maintenance_db: AsyncSession) -> None:
    await _crear_usuario_sin_verificar(
        maintenance_db,
        email="ya-avisado@example.com",
        antiguedad=timedelta(days=6),
        avisado=True,
    )

    with patch("app.core.cleanup.get_email_provider") as proveedor_falso:
        envio = AsyncMock()
        proveedor_falso.return_value.send = envio
        await sweep_unverified_accounts()

    envio.assert_not_awaited()


async def test_borra_a_los_7_dias_y_no_antes(maintenance_db: AsyncSession) -> None:
    await _crear_usuario_sin_verificar(
        maintenance_db, email="siete-dias@example.com", antiguedad=timedelta(days=7, hours=1)
    )
    await _crear_usuario_sin_verificar(
        maintenance_db, email="seis-dias@example.com", antiguedad=timedelta(days=6)
    )

    with patch("app.core.cleanup.get_email_provider") as proveedor_falso:
        proveedor_falso.return_value.send = AsyncMock()
        await sweep_unverified_accounts()

    restantes = (
        await maintenance_db.scalars(
            select(User.email).where(
                User.email.in_(["siete-dias@example.com", "seis-dias@example.com"])
            )
        )
    ).all()
    assert list(restantes) == ["seis-dias@example.com"]


async def test_verificar_tras_el_aviso_cancela_el_borrado(maintenance_db: AsyncSession) -> None:
    await _crear_usuario_sin_verificar(
        maintenance_db,
        email="rescatada@example.com",
        antiguedad=timedelta(days=8),
        avisado=True,
    )
    await maintenance_db.execute(
        text("UPDATE users SET email_verified_at = now() WHERE email = :email"),
        {"email": "rescatada@example.com"},
    )
    await maintenance_db.commit()

    with patch("app.core.cleanup.get_email_provider") as proveedor_falso:
        proveedor_falso.return_value.send = AsyncMock()
        await sweep_unverified_accounts()

    sigue = await maintenance_db.scalar(
        select(User.id).where(User.email == "rescatada@example.com")
    )
    assert sigue is not None


async def test_un_fallo_de_envio_no_bloquea_el_resto_del_barrido(
    maintenance_db: AsyncSession,
) -> None:
    await _crear_usuario_sin_verificar(
        maintenance_db, email="falla-envio@example.com", antiguedad=timedelta(days=5, hours=1)
    )
    await _crear_usuario_sin_verificar(
        maintenance_db, email="envio-correcto@example.com", antiguedad=timedelta(days=5, hours=1)
    )

    with patch("app.core.cleanup.get_email_provider") as proveedor_falso:
        envio = AsyncMock(side_effect=[RuntimeError("SMTP caído"), None])
        proveedor_falso.return_value.send = envio
        await sweep_unverified_accounts()

    avisos = await maintenance_db.scalars(
        select(User.email).where(User.verification_warning_sent_at.is_not(None))
    )
    assert list(avisos) == ["envio-correcto@example.com"]
