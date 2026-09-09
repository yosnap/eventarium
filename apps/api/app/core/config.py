"""Configuración tipada de la aplicación."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _localizar_env() -> Path | None:
    """Busca `infra/env/.env` subiendo desde este fichero.

    En desarrollo el fichero vive en la raíz del repositorio, fuera del paquete. En un
    contenedor no existe —la configuración llega por variables de entorno— y la ruta es
    además más corta, así que no se puede asumir una profundidad fija.
    """
    for directorio in Path(__file__).resolve().parents:
        candidato = directorio / "infra" / "env" / ".env"
        if candidato.is_file():
            return candidato
    return None


ENV_FILE = _localizar_env()

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Variables de entorno de la API. Ver `infra/env/.env.example`."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Environment = "development"
    log_level: str = "INFO"

    # Base de datos: la API usa app_user (sin BYPASSRLS); migraciones y seed, app_maintainer.
    database_url: str
    database_migrations_url: str

    # Almacenamiento S3 (SeaweedFS por defecto).
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "media"
    s3_region: str = "us-east-1"
    s3_public_base_url: str

    redis_url: str

    # Autenticación.
    jwt_secret: str
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    cookie_domain: str | None = None

    # Red y multi-tenant.
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"
    cors_origins: str = ""
    default_organization_slug: str = ""
    web_base_url: str = "http://localhost:8080"

    # Semilla de demostración.
    seed_owner_email: str = "owner@example.com"
    seed_owner_password: str = ""

    # Límites de subida.
    max_image_bytes: int = Field(default=5 * 1024 * 1024, gt=0)

    # Correo saliente (Mailpit en desarrollo, SMTP genérico en producción).
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_from: str = "no-responder@example.com"

    # Turnstile: obligatorio en producción, desactivable en desarrollo y tests.
    turnstile_enabled: bool = True
    turnstile_secret_key: str = ""

    # Dominio de la instalación: cada organización recibe {slug}.{dominio_base}.
    # Vacío en desarrollo (se resuelve por localhost); obligatorio en producción.
    dominio_base: str = ""

    # Ventana de confirmación al promover desde la lista de espera (fase 3 del
    # PRD, fase 3 de trabajo). Fija a nivel de aplicación, no por evento —
    # decisión confirmada en el predict/debate del plan: no ampliar sin que se
    # pida.
    waitlist_promotion_window_hours: int = 48

    # Vigencia del enlace de autocancelación de una inscripción (fase 3 del
    # PRD, fase 4 de trabajo). Generoso a propósito: una inscripción puede
    # cancelarse en cualquier momento hasta el evento, no solo en las horas
    # posteriores al alta.
    registration_cancel_token_ttl_days: int = 90

    # Entrada QR (fase 4 del PRD). Secreto **propio**, distinto de `jwt_secret`:
    # comprometer el secreto de entradas no debe permitir forjar tokens de
    # sesión, y viceversa (decisión #3 del plan de la fase 4).
    ticket_qr_secret: str
    # Margen tras `event.ends_at` durante el que el QR sigue siendo válido —
    # absorbe cierres tardíos y desajustes de reloj (decisión #4 del plan).
    ticket_qr_expiry_margin_hours: int = 48

    # Pagos con Stripe Connect (fase 6 del PRD). Con valor por defecto vacío
    # (hallazgo #14 del red-team): una instalación que no vende nada, y el CI
    # que escribe su propio `.env`, no deben dejar de arrancar por dos
    # secretos de una pasarela que no usan. La ventana de checkout es un
    # campo por evento (tabla `events`), no vive en esta configuración.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Plazo del reembolso automático al cancelar una inscripción de pago
    # (hallazgo #13): se consume en la fase 5 de trabajo.
    payment_refund_cutoff_hours: int = 24
    # Purga de `stripe_webhook_events` (hallazgo #15): se consume en la fase 5
    # de trabajo.
    stripe_webhook_retention_days: int = 90

    @field_validator("jwt_secret", "ticket_qr_secret")
    @classmethod
    def _validar_secreto(cls, valor: str) -> str:
        if len(valor) < 32:
            raise ValueError("El secreto debe tener al menos 32 caracteres")
        return valor

    @field_validator("stripe_secret_key", "stripe_webhook_secret")
    @classmethod
    def _validar_secreto_de_stripe_si_informado(cls, valor: str) -> str:
        """Mismo mínimo que `_validar_secreto`, pero solo si hay valor: estos
        dos secretos son opcionales (ver arriba), a diferencia de
        `jwt_secret`/`ticket_qr_secret`, que son obligatorios y por tanto
        pueden validarse incondicionalmente."""
        if valor and len(valor) < 32:
            raise ValueError("El secreto debe tener al menos 32 caracteres")
        return valor

    @field_validator("s3_public_base_url", "web_base_url")
    @classmethod
    def _sin_barra_final(cls, valor: str) -> str:
        return valor.rstrip("/")

    @model_validator(mode="after")
    def _validar_produccion(self) -> Settings:
        if self.app_env == "production" and self.default_organization_slug:
            raise ValueError(
                "DEFAULT_ORGANIZATION_SLUG debe estar vacío en producción: la organización "
                "se resuelve siempre por Host."
            )
        if self.app_env == "production" and not self.turnstile_enabled:
            raise ValueError(
                "TURNSTILE_ENABLED no puede estar desactivado en producción: desprotegería "
                "el registro y el reenvío de verificación frente a scripts automatizados."
            )
        if self.app_env == "production" and not self.dominio_base:
            raise ValueError(
                "DOMINIO_BASE no puede estar vacío en producción: cada organización "
                "necesita saber bajo qué dominio registrar su subdominio."
            )
        if self.app_env == "production" and self.stripe_secret_key.startswith("sk_test_"):
            raise ValueError(
                "STRIPE_SECRET_KEY es una clave de test (sk_test_...) en producción: "
                "cobraría contra la cuenta de pruebas de Stripe con dinero real."
            )
        return self

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def payments_enabled(self) -> bool:
        """`False` si la instalación no tiene Stripe configurado: los
        endpoints de pagos devuelven 503 y un evento `paid` no se puede
        publicar."""
        return bool(self.stripe_secret_key) and bool(self.stripe_webhook_secret)

    @property
    def cookie_secure(self) -> bool:
        """`Secure` solo se relaja fuera de producción, donde se sirve HTTP en local."""
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]

    @property
    def trusted_proxy_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        redes: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for bruto in self.trusted_proxy_cidrs.split(","):
            texto = bruto.strip()
            if texto:
                redes.append(ipaddress.ip_network(texto, strict=False))
        return redes


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instancia única de configuración."""
    return Settings()  # type: ignore[call-arg]
