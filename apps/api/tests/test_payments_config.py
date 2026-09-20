"""Validación de configuración de Stripe (fase 6 del PRD, fase 1 de trabajo):
secretos opcionales con longitud mínima si se informan, y arranque bloqueado
en producción con una clave de test. Mismo patrón que `test_turnstile.py`.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def test_arrancar_sin_ninguna_variable_de_stripe_funciona(monkeypatch) -> None:
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    settings = Settings()  # no debe lanzar
    assert settings.stripe_secret_key == ""
    assert settings.stripe_webhook_secret == ""
    assert settings.payments_enabled is False


def test_payments_enabled_exige_los_dos_secretos(monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_" + "a" * 40)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    settings = Settings()
    assert settings.payments_enabled is False

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_" + "b" * 40)
    settings = Settings()
    assert settings.payments_enabled is True


def test_secreto_de_stripe_por_debajo_del_minimo_aborta(monkeypatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_corto")
    with pytest.raises(ValueError, match="al menos 32 caracteres"):
        Settings()


def test_produccion_con_clave_de_test_de_stripe_aborta(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    monkeypatch.setenv("DEFAULT_ORGANIZATION_SLUG", "")
    monkeypatch.setenv("DOMINIO_BASE", "ejemplo.org")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_" + "a" * 40)
    with pytest.raises(ValueError, match="STRIPE_SECRET_KEY"):
        Settings()


def test_produccion_con_clave_live_de_stripe_arranca(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    monkeypatch.setenv("DEFAULT_ORGANIZATION_SLUG", "")
    monkeypatch.setenv("DOMINIO_BASE", "ejemplo.org")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_" + "a" * 40)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_" + "b" * 40)
    Settings()  # no debe lanzar
