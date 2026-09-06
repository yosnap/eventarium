"""Configuración tipada de la aplicación."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# infra/env/.env vive fuera del paquete: apps/api/app/core/config.py → raíz del repo.
REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = REPO_ROOT / "infra" / "env" / ".env"

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

    @field_validator("jwt_secret")
    @classmethod
    def _validar_secreto(cls, valor: str) -> str:
        if len(valor) < 32:
            raise ValueError("JWT_SECRET debe tener al menos 32 caracteres")
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
        return self

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

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
