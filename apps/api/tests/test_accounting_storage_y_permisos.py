"""Permisos de contabilidad, almacenamiento de justificantes y su endpoint de descarga.

Cubre tres criterios de éxito de `phase-01-modelo-de-datos-y-permisos.md`:
- Una organización creada tras la migración tiene `accounting:read`/`write`
  en su rol `organizer` sin intervención manual.
- `validate_upload` acepta PDF solo con `ALLOWED_DOCUMENT_MIMES` explícito;
  las llamadas existentes de branding siguen rechazando PDF.
- Una petición anónima o de otra organización al endpoint del justificante
  devuelve 401/403, y el propio dueño lo descarga con
  `Content-Disposition: attachment`.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from app.core.permissions import Permission
from app.core.storage import ALLOWED_DOCUMENT_MIMES, build_object_key, get_storage, validate_upload
from app.modules.roles.models import Role, RolePermission
from app.modules.roles.system_roles import ORGANIZER
from app.shared.errors import ValidationDomainError
from tests.conftest import OrganizacionDePrueba, SessionMaintenance, iniciar_sesion

# Cabecera de un PDF real: `%PDF-1.4`. `validate_upload` mira los bytes, no la
# extensión, así que basta con la firma para que `magic` lo reconozca.
CONTENIDO_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
CONTENIDO_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d"
    b"\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_organizacion_nueva_tiene_accounting_en_el_rol_organizer(
    organizacion: OrganizacionDePrueba,
) -> None:
    """`crear_organizacion` clona `SYSTEM_ROLE_TEMPLATES`, que incluye
    `ORGANIZER` ya actualizado con `accounting:read`/`write` — sin backfill
    manual, cubre organizaciones creadas *después* de la migración 0020."""
    assert Permission.ACCOUNTING_READ in ORGANIZER.permissions
    assert Permission.ACCOUNTING_WRITE in ORGANIZER.permissions

    async with SessionMaintenance() as session:
        rol = await session.scalar(
            select(Role).where(Role.organization_id == organizacion.id, Role.key == "organizer")
        )
        assert rol is not None
        permisos = set(
            (
                await session.scalars(
                    select(RolePermission.permission).where(RolePermission.role_id == rol.id)
                )
            ).all()
        )
    assert Permission.ACCOUNTING_READ.value in permisos
    assert Permission.ACCOUNTING_WRITE.value in permisos


def test_validate_upload_acepta_pdf_solo_con_allowed_document_mimes() -> None:
    mime, extension = validate_upload(CONTENIDO_PDF, allowed_mimes=ALLOWED_DOCUMENT_MIMES)
    assert mime == "application/pdf"
    assert extension == "pdf"


def test_validate_upload_sin_allowed_mimes_explicito_sigue_rechazando_pdf() -> None:
    """Retrocompatibilidad: una llamada que no pasa `allowed_mimes` (todas las
    existentes de branding/portada/logo) sigue usando `ALLOWED_IMAGE_MIMES`."""
    try:
        validate_upload(CONTENIDO_PDF)
    except ValidationDomainError as exc:
        assert "application/pdf" not in str(exc).split("Se aceptan")[-1]
        assert "image/png" in str(exc)
    else:
        raise AssertionError("un PDF no debería pasar validate_upload sin allowed_mimes")


async def test_subir_pdf_como_logo_de_organizacion_sigue_siendo_rechazado(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    """Regresión explícita contra el endpoint real de subida de logo
    (`PUT /organizations/me/branding/logo`), que nunca pasa `allowed_mimes`."""
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.put(
        "/api/v1/organizations/me/branding/logo",
        files={"fichero": ("logo.pdf", CONTENIDO_PDF, "application/pdf")},
        headers=cabeceras,
    )
    assert respuesta.status_code == 422, respuesta.text


async def test_descargar_justificante_sin_sesion_devuelve_401(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    clave = build_object_key(organizacion.id, "accounting-receipts", "pdf")
    respuesta = await cliente.get(f"/api/v1/accounting/receipts/{clave}")
    assert respuesta.status_code == 401, respuesta.text


async def test_descargar_justificante_de_otra_organizacion_devuelve_403(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    clave_ajena = build_object_key(otra_organizacion.id, "accounting-receipts", "pdf")
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(f"/api/v1/accounting/receipts/{clave_ajena}", headers=cabeceras)
    assert respuesta.status_code == 403, respuesta.text


async def test_descargar_justificante_con_travesia_de_ruta_devuelve_403(
    cliente: AsyncClient,
    organizacion: OrganizacionDePrueba,
    otra_organizacion: OrganizacionDePrueba,
) -> None:
    """`..` intercalados no deben esquivar la comprobación de organización.

    El proveedor S3 real resuelve `..` contra el filer: un validador que solo
    mira los tres primeros segmentos de la clave (en vez de la forma completa)
    deja pasar `orgs/{propia}/accounting-receipts/../../orgs/{ajena}/
    accounting-receipts/x.pdf` y sirve el documento de otra organización.
    """
    clave_ajena = build_object_key(otra_organizacion.id, "accounting-receipts", "pdf")
    clave_con_travesia = f"orgs/{organizacion.id}/accounting-receipts/../../{clave_ajena}"
    _, cabeceras = await iniciar_sesion(cliente, organizacion)

    respuesta = await cliente.get(
        f"/api/v1/accounting/receipts/{clave_con_travesia}", headers=cabeceras
    )
    assert respuesta.status_code in (403, 404), respuesta.text

    clave_percent_encoded = (
        f"orgs/{organizacion.id}/accounting-receipts/%2e%2e/%2e%2e/{clave_ajena}"
    )
    respuesta_encoded = await cliente.get(
        f"/api/v1/accounting/receipts/{clave_percent_encoded}", headers=cabeceras
    )
    assert respuesta_encoded.status_code in (403, 404), respuesta_encoded.text


async def test_descargar_justificante_propio_devuelve_el_contenido_como_adjunto(
    cliente: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    almacen = get_storage()
    await almacen.ensure_bucket()
    clave = build_object_key(organizacion.id, "accounting-receipts", "pdf")
    await almacen.put_object(
        clave, CONTENIDO_PDF, "application/pdf", content_disposition="attachment"
    )

    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    respuesta = await cliente.get(f"/api/v1/accounting/receipts/{clave}", headers=cabeceras)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.content == CONTENIDO_PDF
    disposicion = respuesta.headers.get("content-disposition", "")
    assert disposicion.startswith("attachment"), disposicion

    await almacen.delete_object(clave)
