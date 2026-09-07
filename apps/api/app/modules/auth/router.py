"""Endpoints de autenticación."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import get_settings
from app.core.deps import DbDep, get_current_organization
from app.core.ratelimit import (
    LOGIN_POR_HOST,
    LOGIN_POR_IP,
    REENVIO_VERIFICACION_POR_IP,
    REFRESH_POR_IP,
    REGISTRO_POR_IP,
    VERIFICACION_CORREO_POR_IP,
    limit_per_host,
    limit_per_ip,
)
from app.core.security import create_access_token
from app.core.tenant import ResolvedOrganization
from app.core.turnstile import require_turnstile
from app.modules.auth import service
from app.modules.auth.schemas import (
    GenericMessageResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    UserSummary,
    VerifyEmailResponse,
)
from app.shared.errors import AuthenticationError

router = APIRouter(prefix="/auth", tags=["autenticación"])

# La cookie se limita a la ruta de auth: ningún otro endpoint necesita verla.
COOKIE_NOMBRE = "ia_week_refresh"
COOKIE_PATH = "/api/v1/auth"


def _fijar_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NOMBRE,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path=COOKIE_PATH,
        # Sin `Domain`: web y API comparten host tras Caddy, así que la cookie ya es
        # first-party. Añadir `Domain` solo ampliaría su alcance a subdominios.
        domain=settings.cookie_domain or None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _borrar_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=COOKIE_NOMBRE,
        path=COOKIE_PATH,
        domain=settings.cookie_domain or None,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.post(
    "/login",
    summary="Iniciar sesión",
    description="Devuelve un access token y fija la cookie de refresco.",
    response_model=LoginResponse,
    dependencies=[
        limit_per_ip("login", LOGIN_POR_IP),
        limit_per_host("login", LOGIN_POR_HOST),
    ],
)
async def login(
    datos: LoginRequest,
    response: Response,
    session: DbDep,
    organizacion: Annotated[ResolvedOrganization, Depends(get_current_organization)],
) -> LoginResponse:
    usuario = await service.authenticate(
        session,
        email=str(datos.email),
        password=datos.password,
        organization_id=organizacion.id,
    )
    tokens = await service.issue_tokens(usuario, organizacion.id)
    _fijar_cookie(response, tokens.refresh_token)
    return LoginResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=UserSummary(
            id=str(usuario.id),
            email=usuario.email,
            first_name=usuario.first_name,
            last_name=usuario.last_name,
            is_superadmin=usuario.is_superadmin,
        ),
    )


@router.post(
    "/refresh",
    summary="Renovar la sesión",
    description="Rota el refresh token de la cookie y devuelve un access token nuevo.",
    response_model=TokenResponse,
    dependencies=[limit_per_ip("refresh", REFRESH_POR_IP)],
)
async def refresh(request: Request, response: Response, session: DbDep) -> TokenResponse:
    cookie = request.cookies.get(COOKIE_NOMBRE)
    if not cookie:
        raise AuthenticationError("No hay sesión que renovar.")
    tokens, _ = await service.rotate_refresh_token(session, cookie)
    _fijar_cookie(response, tokens.refresh_token)
    return TokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post(
    "/register",
    summary="Registrar una cuenta",
    description=(
        "Crea una cuenta con el correo sin verificar y encola el enlace de "
        "verificación. Responde siempre igual, exista ya la cuenta o no."
    ),
    response_model=GenericMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[limit_per_ip("registro", REGISTRO_POR_IP)],
)
async def register(
    datos: RegisterRequest, request: Request, session: DbDep
) -> GenericMessageResponse:
    await require_turnstile(request, datos.turnstile_token)
    await service.register_user(session, email=str(datos.email), password=datos.password)
    return GenericMessageResponse(
        message="Si el correo no está ya registrado, recibirás un enlace de verificación."
    )


@router.get(
    "/verify-email",
    summary="Verificar el correo",
    description="Consume el token del enlace de verificación y marca el correo como verificado.",
    response_model=VerifyEmailResponse,
    dependencies=[limit_per_ip("verificar-correo", VERIFICACION_CORREO_POR_IP)],
)
async def verify_email(token: str, session: DbDep) -> VerifyEmailResponse:
    settings = get_settings()
    user_id = await service.verify_email(session, token=token)
    return VerifyEmailResponse(
        message="Correo verificado correctamente.",
        access_token=create_access_token(user_id, None, is_superadmin=False),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post(
    "/resend-verification",
    summary="Reenviar el correo de verificación",
    description=(
        "Encola un nuevo enlace solo si la cuenta existe y no está verificada. "
        "Responde siempre igual."
    ),
    response_model=GenericMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[limit_per_ip("reenvio-verificacion", REENVIO_VERIFICACION_POR_IP)],
)
async def resend_verification(
    datos: ResendVerificationRequest, request: Request, session: DbDep
) -> GenericMessageResponse:
    await require_turnstile(request, datos.turnstile_token)
    await service.resend_verification(session, email=str(datos.email))
    return GenericMessageResponse(
        message="Si la cuenta existe y no está verificada, recibirás un nuevo enlace."
    )


@router.post(
    "/logout",
    summary="Cerrar sesión",
    description="Revoca la familia de tokens y borra la cookie.",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def logout(request: Request, response: Response) -> Response:
    cookie = request.cookies.get(COOKIE_NOMBRE)
    if cookie:
        await service.revoke_refresh_token(cookie)
    salida = Response(status_code=status.HTTP_204_NO_CONTENT)
    _borrar_cookie(salida)
    return salida
