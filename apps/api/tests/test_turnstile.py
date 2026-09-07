"""Verificación de Turnstile: éxito, rechazo, caída del servicio y salvaguarda de producción."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.core.turnstile import InvalidTurnstileTokenError, verify_turnstile_token
from app.shared.errors import ServiceUnavailableError


class _RespuestaFalsa:
    def __init__(self, exito: bool) -> None:
        self._exito = exito

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, bool]:
        return {"success": self._exito}


async def test_token_valido_verifica_correctamente() -> None:
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_RespuestaFalsa(True))):
        assert await verify_turnstile_token("token", "1.2.3.4") is True


async def test_token_invalido_no_verifica() -> None:
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_RespuestaFalsa(False))):
        assert await verify_turnstile_token("token", "1.2.3.4") is False


async def test_servicio_caido_devuelve_503() -> None:
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.ConnectError("caído")),
    ):
        with pytest.raises(ServiceUnavailableError):
            await verify_turnstile_token("token", "1.2.3.4")


def test_arranque_falla_en_produccion_con_turnstile_desactivado(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TURNSTILE_ENABLED", "false")
    monkeypatch.setenv("DEFAULT_ORGANIZATION_SLUG", "")
    with pytest.raises(ValueError, match="TURNSTILE_ENABLED"):
        Settings()


def test_arranque_permite_produccion_con_turnstile_activo(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TURNSTILE_ENABLED", "true")
    monkeypatch.setenv("DEFAULT_ORGANIZATION_SLUG", "")
    Settings()  # no debe lanzar


def test_error_de_token_invalido_es_422() -> None:
    assert InvalidTurnstileTokenError("x").status_code == 422
