"""Errores de dominio y su traducción a `application/problem+json` (RFC 9457)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Starlette renombró la constante 422 entre versiones; el número no cambia.
HTTP_422 = 422


class DomainError(Exception):
    """Error de negocio con traducción directa a respuesta HTTP."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    title: str = "Error de dominio"

    def __init__(self, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}

    def to_problem(self, instance: str) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "type": "about:blank",
            "title": self.title,
            "status": self.status_code,
            "detail": self.detail,
            "instance": instance,
        }
        cuerpo.update(self.extra)
        return cuerpo


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Recurso no encontrado"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Conflicto con el estado actual"


class ValidationDomainError(DomainError):
    status_code = HTTP_422
    title = "Datos no válidos"


class AuthenticationError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    title = "No autenticado"


class PermissionDeniedError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    title = "Permiso denegado"


class ServiceUnavailableError(DomainError):
    """Dependencia crítica no disponible: se falla cerrado, nunca abierto."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Servicio no disponible"


class ExternalServiceError(DomainError):
    """Un proveedor externo (p. ej. Stripe) ha fallado o rechazado la petición.

    Distinta de `ServiceUnavailableError`: esta última es «no configurado»
    (falla siempre, antes de intentar nada); esta es «configurado pero la
    llamada ha fallado» — típicamente `stripe.StripeError` traducido por
    `payments/stripe_client.py` (fase 6 del PRD, decisión #7 del plan). Nunca
    lleva el mensaje crudo del proveedor: solo un texto accionable para quien
    usa el panel.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    title = "Fallo de un servicio externo"


def _problem_response(status_code: int, cuerpo: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=cuerpo, media_type=PROBLEM_CONTENT_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los manejadores. Ninguna respuesta expone trazas ni detalles de BD."""

    @app.exception_handler(DomainError)
    async def _dominio(request: Request, exc: DomainError) -> JSONResponse:
        return _problem_response(exc.status_code, exc.to_problem(request.url.path))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem_response(
            exc.status_code,
            {
                "type": "about:blank",
                "title": "Error HTTP",
                "status": exc.status_code,
                "detail": str(exc.detail),
                "instance": request.url.path,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem_response(
            HTTP_422,
            {
                "type": "about:blank",
                "title": "Datos no válidos",
                "status": HTTP_422,
                "detail": "La petición no supera la validación.",
                "instance": request.url.path,
                "errors": [
                    {"campo": ".".join(str(p) for p in e["loc"]), "mensaje": e["msg"]}
                    for e in exc.errors()
                ],
            },
        )

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception) -> JSONResponse:
        return _problem_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {
                "type": "about:blank",
                "title": "Error interno",
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "detail": "Se ha producido un error inesperado.",
                "instance": request.url.path,
            },
        )
