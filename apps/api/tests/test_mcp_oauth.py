"""OAuth del MCP de extremo a extremo, como lo recorre un cliente real:
registro dinámico → `authorize` con PKCE → consentimiento en la web → canje
del código → llamada al MCP → renovación. Y los caminos que deben fallar."""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest
from httpx import AsyncClient

from app.core.database import SessionMaintenance
from app.core.redis_client import get_redis
from app.modules.mcp.models import McpOAuthClient
from app.modules.mcp.oauth import cimd
from app.modules.mcp.server_urls import url_del_emisor, url_del_recurso
from tests.conftest import OrganizacionDePrueba, iniciar_sesion
from tests.mcp_test_helpers import _rpc

RETORNO = "http://localhost:9999/callback"


def _pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(48)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=")
    return verificador, reto.decode()


async def _registrar(cliente_mcp: AsyncClient) -> str:
    respuesta = await cliente_mcp.post(
        "/mcp/oauth/register",
        json={
            "client_name": "Asistente de prueba",
            "redirect_uris": [RETORNO],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["client_id"]


async def _autorizar(
    cliente: AsyncClient,
    cliente_mcp: AsyncClient,
    cabeceras: dict[str, str],
    client_id: str,
    reto: str,
) -> str:
    """Hasta el código: `authorize`, lectura de la solicitud y aprobación."""
    autorizar = await cliente_mcp.get(
        "/mcp/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": RETORNO,
            "code_challenge": reto,
            "code_challenge_method": "S256",
            "state": "estado-123",
            "scope": "eventos:leer",
            "resource": url_del_recurso(),
        },
    )
    assert autorizar.status_code == 302, autorizar.text
    solicitud = parse_qs(urlsplit(autorizar.headers["location"]).query)["solicitud"][0]

    vista = await cliente.get(f"/api/v1/oauth/solicitudes/{solicitud}", headers=cabeceras)
    assert vista.status_code == 200, vista.text
    assert vista.json()["no_verificado"] is True
    assert "eventos:cancelar" not in vista.json()["ambitos_por_defecto"]

    aprobada = await cliente.post(
        f"/api/v1/oauth/solicitudes/{solicitud}/aprobar",
        headers=cabeceras,
        json={"scopes": ["eventos:leer"]},
    )
    assert aprobada.status_code == 200, aprobada.text
    destino = urlsplit(aprobada.json()["redirect_to"])
    parametros = parse_qs(destino.query)
    assert f"{destino.scheme}://{destino.netloc}{destino.path}" == RETORNO
    assert parametros["state"] == ["estado-123"]
    assert parametros["iss"] == [url_del_emisor()]
    return parametros["code"][0]


async def _canjear(  # type: ignore[no-untyped-def]
    cliente_mcp: AsyncClient, client_id: str, codigo: str, verificador: str, **extra: str
):
    return await cliente_mcp.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": codigo,
            "redirect_uri": RETORNO,
            "client_id": client_id,
            "code_verifier": verificador,
            "resource": url_del_recurso(),
            **extra,
        },
    )


async def _renovar(cliente_mcp: AsyncClient, client_id: str, renovacion: str):  # type: ignore[no-untyped-def]
    return await cliente_mcp.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": renovacion,
            "client_id": client_id,
            "resource": url_del_recurso(),
        },
    )


async def _conectar(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> tuple[str, dict]:  # type: ignore[type-arg]
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    client_id = await _registrar(cliente_mcp)
    verificador, reto = _pkce()
    codigo = await _autorizar(cliente, cliente_mcp, cabeceras, client_id, reto)
    canje = await _canjear(cliente_mcp, client_id, codigo, verificador)
    assert canje.status_code == 200, canje.text
    return client_id, canje.json()


async def test_flujo_completo_y_separacion_de_tokens(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    token_web, cabeceras = await iniciar_sesion(cliente, organizacion)
    client_id = await _registrar(cliente_mcp)
    verificador, reto = _pkce()
    codigo = await _autorizar(cliente, cliente_mcp, cabeceras, client_id, reto)

    canje = await _canjear(cliente_mcp, client_id, codigo, verificador)
    assert canje.status_code == 200, canje.text
    tokens = canje.json()
    assert tokens["token_type"] == "Bearer" and tokens["refresh_token"]

    # El token OAuth sirve en el MCP…
    herramientas = await _rpc(cliente_mcp, tokens["access_token"], "tools/list")
    assert herramientas.status_code == 200
    # …pero no en la API web, ni el de la web en el MCP.
    como_web = await cliente.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    web_en_mcp = await _rpc(cliente_mcp, token_web, "tools/list")
    assert como_web.status_code == 401
    assert web_en_mcp.status_code == 401

    # El código es de un solo uso.
    otra_vez = await _canjear(cliente_mcp, client_id, codigo, verificador)
    assert otra_vez.status_code == 400

    # La renovación rota; presentar la anterior revoca la conexión entera.
    renovada = await cliente_mcp.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
            "resource": url_del_recurso(),
        },
    )
    assert renovada.status_code == 200, renovada.text
    nuevos = renovada.json()
    # Pasado el margen de reintento (se simula borrando la marca).
    for clave in await get_redis().keys("mcp:oauth:rotado:*"):
        await get_redis().delete(clave)
    reutilizada = await cliente_mcp.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
            "resource": url_del_recurso(),
        },
    )
    assert reutilizada.status_code == 400
    tras_reutilizar = await _rpc(cliente_mcp, nuevos["access_token"], "tools/list")
    assert tras_reutilizar.status_code == 401


async def test_sin_pkce_no_hay_autorizacion(cliente_mcp: AsyncClient) -> None:
    client_id = await _registrar(cliente_mcp)

    respuesta = await cliente_mcp.get(
        "/mcp/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": RETORNO,
            "state": "x",
            "resource": url_del_recurso(),
        },
    )

    assert respuesta.status_code in (302, 400)
    if respuesta.status_code == 302:
        assert "error=" in respuesta.headers["location"]
        assert "solicitud=" not in respuesta.headers["location"]


async def test_pkce_plain_no_se_acepta(cliente_mcp: AsyncClient) -> None:
    client_id = await _registrar(cliente_mcp)

    respuesta = await cliente_mcp.get(
        "/mcp/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": RETORNO,
            "code_challenge": "reto-en-claro-de-al-menos-43-caracteres-xxxxxxx",
            "code_challenge_method": "plain",
            "state": "x",
            "resource": url_del_recurso(),
        },
    )

    assert respuesta.status_code in (302, 400)
    assert "solicitud=" not in respuesta.headers.get("location", "")


async def test_canje_con_otro_retorno_se_rechaza(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    client_id = await _registrar(cliente_mcp)
    verificador, reto = _pkce()
    codigo = await _autorizar(cliente, cliente_mcp, cabeceras, client_id, reto)

    canje = await cliente_mcp.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": codigo,
            "redirect_uri": "http://localhost:9999/otro",
            "client_id": client_id,
            "code_verifier": verificador,
            "resource": url_del_recurso(),
        },
    )

    assert canje.status_code == 400


async def test_un_reintento_de_renovacion_no_revoca_la_conexion(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    client_id, tokens = await _conectar(cliente, cliente_mcp, organizacion)

    renovada = await _renovar(cliente_mcp, client_id, tokens["refresh_token"])
    reintento = await _renovar(cliente_mcp, client_id, tokens["refresh_token"])

    assert renovada.status_code == 200, renovada.text
    assert reintento.status_code == 400
    # Recién rotado se toma por reintento: la conexión sigue viva.
    siguiente = await _rpc(cliente_mcp, renovada.json()["access_token"], "tools/list")
    assert siguiente.status_code == 200


async def test_revocar_el_token_de_acceso_corta_la_conexion(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    client_id, tokens = await _conectar(cliente, cliente_mcp, organizacion)

    revocado = await cliente_mcp.post(
        "/mcp/oauth/revoke",
        # El SDK exige el campo `client_secret` aunque el cliente sea público.
        data={"token": tokens["access_token"], "client_id": client_id, "client_secret": ""},
    )

    assert revocado.status_code == 200
    despues = await _rpc(cliente_mcp, tokens["access_token"], "tools/list")
    assert despues.status_code == 401


async def test_cliente_dinamico_confidencial_sin_secreto_guardado(
    cliente: AsyncClient, cliente_mcp: AsyncClient, organizacion: OrganizacionDePrueba
) -> None:
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    registro = await cliente_mcp.post(
        "/mcp/oauth/register",
        json={
            "client_name": "Confidencial",
            "redirect_uris": [RETORNO],
            "token_endpoint_auth_method": "client_secret_post",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert registro.status_code == 201, registro.text
    client_id, secreto = registro.json()["client_id"], registro.json()["client_secret"]
    async with SessionMaintenance() as session:
        guardado = await session.get(McpOAuthClient, client_id)
    assert guardado is not None and "client_secret" not in guardado.metadata_

    verificador, reto = _pkce()
    codigo = await _autorizar(cliente, cliente_mcp, cabeceras, client_id, reto)
    sin_secreto = await _canjear(cliente_mcp, client_id, codigo, verificador)
    con_secreto = await _canjear(cliente_mcp, client_id, codigo, verificador, client_secret=secreto)

    assert sin_secreto.status_code == 401
    assert con_secreto.status_code == 200, con_secreto.text


async def test_cliente_cimd_llega_al_consentimiento_pidiendo_ambitos(
    cliente: AsyncClient,
    cliente_mcp: AsyncClient,
    organizacion: OrganizacionDePrueba,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id = "https://asistente.example/oauth/cliente.json"
    for clave in await get_redis().keys("mcp:cimd:*"):
        await get_redis().delete(clave)

    async def descargar(url: str) -> dict:  # type: ignore[type-arg]
        return {"client_id": url, "client_name": "Asistente CIMD", "redirect_uris": [RETORNO]}

    monkeypatch.setattr(cimd, "_descargar", descargar)
    _, reto = _pkce()

    autorizar = await cliente_mcp.get(
        "/mcp/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": RETORNO,
            "code_challenge": reto,
            "code_challenge_method": "S256",
            "state": "s",
            "scope": "eventos:leer eventos:editar",
            "resource": url_del_recurso(),
        },
    )

    assert autorizar.status_code == 302, autorizar.text
    solicitud = parse_qs(urlsplit(autorizar.headers["location"]).query)["solicitud"][0]
    _, cabeceras = await iniciar_sesion(cliente, organizacion)
    vista = (await cliente.get(f"/api/v1/oauth/solicitudes/{solicitud}", headers=cabeceras)).json()
    assert vista["client_name"] == "Asistente CIMD" and vista["no_verificado"] is False
    assert vista["ambitos_pedidos"] == ["eventos:leer", "eventos:editar"]
    # Solo se ofrece lo pedido, y no se puede conceder otra cosa.
    assert set(vista["ambitos_permitidos"]) == {"eventos:leer", "eventos:editar"}
    de_mas = await cliente.post(
        f"/api/v1/oauth/solicitudes/{solicitud}/aprobar",
        headers=cabeceras,
        json={"scopes": ["eventos:leer", "eventos:cancelar"]},
    )
    assert de_mas.status_code in (400, 422)


async def test_no_se_registran_retornos_peligrosos(cliente_mcp: AsyncClient) -> None:
    respuesta = await cliente_mcp.post(
        "/mcp/oauth/register",
        json={"redirect_uris": ["http://atacante.example/callback"], "client_name": "Malo"},
    )
    assert respuesta.status_code == 400


async def test_metadatos_del_servidor_de_autorizacion(cliente_mcp: AsyncClient) -> None:
    raiz = await cliente_mcp.get("/.well-known/oauth-authorization-server/mcp/oauth")
    recurso = await cliente_mcp.get("/.well-known/oauth-protected-resource/mcp")

    assert raiz.status_code == 200
    metadatos = raiz.json()
    assert metadatos["issuer"].rstrip("/") == url_del_emisor()
    assert metadatos["code_challenge_methods_supported"] == ["S256"]
    assert metadatos["client_id_metadata_document_supported"] is True
    assert recurso.json()["authorization_servers"] == [url_del_emisor()]


class TestCimd:
    @pytest.mark.parametrize(
        ("uri", "permitida"),
        [
            ("https://claude.ai/api/mcp/auth_callback", True),
            ("http://localhost:33418/callback", True),
            ("http://127.0.0.1:5000/cb", True),
            ("cursor://anysphere.cursor-mcp/oauth/callback", True),
            ("http://atacante.example/cb", False),
            ("javascript:alert(1)", False),
            ("data:text/html,hola", False),
        ],
    )
    def test_direcciones_de_retorno(self, uri: str, permitida: bool) -> None:
        assert cimd.redireccion_permitida(uri) is permitida

    @pytest.mark.parametrize(
        "ip", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "100.64.1.1", "::1", "192.168.1.9"]
    )
    def test_rechaza_ips_no_publicas(self, ip: str) -> None:
        assert cimd._ip_publica(ip) is False  # noqa: SLF001

    async def test_un_cliente_que_resuelve_a_la_red_interna_no_se_descarga(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def resolver_a_interna(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            return [(None, None, None, None, ("10.0.0.5", 443))]

        class _Bucle:
            getaddrinfo = staticmethod(resolver_a_interna)

        monkeypatch.setattr(cimd.asyncio, "get_running_loop", lambda: _Bucle())

        with pytest.raises(cimd.CimdNoValido):
            await cimd._descargar("https://cliente.example/cimd.json")  # noqa: SLF001
