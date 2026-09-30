"""Formato del correo saliente: el texto plano viaja con su versión HTML.

La queja era real: los cuerpos son texto plano con la URL a pelo, y los
clientes de correo móvil envuelven la línea en mitad de la URL — el enlace
deja de funcionar (era, con casi toda seguridad, «las invitaciones no
llegan»). El fix es centralizado en `enviar_con`: `multipart/alternative`
con el texto plano intacto y una versión HTML con `<a href>` de verdad.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.core import email
from app.modules.email_settings import presets


def _config() -> presets.ConfigSmtp:
    return presets.ConfigSmtp(
        host="correo.de.prueba",
        port=587,
        username="",
        password="",
        tls_mode="starttls",
        from_address="no-responder@eventarium.org",
    )


def test_el_html_convierte_las_urls_en_enlaces_y_escapa_el_resto() -> None:
    cuerpo = (
        "Hola,\n\n"
        "Confirma tu correo para completar el registro:\n"
        "http://localhost:8080/verificar-correo?token=abc\n\n"
        "El enlace caduca en 24 horas. Si no has sido tú, ignora este mensaje."
    )
    html_ = email.texto_a_html(cuerpo)
    assert '<a href="http://localhost:8080/verificar-correo?token=abc">' in html_
    assert html_.count("<p>") == 3
    # Un nombre o una organización con `&` no puede abrir estructura propia.
    con_especial = email.texto_a_html("Organización «A & B» <reunion>")
    assert "A &amp; B" in con_especial
    assert "<reunion>" not in con_especial


async def test_el_envio_lleva_texto_plano_intacto_y_html_con_enlaces() -> None:
    cuerpo = (
        "Hola,\n\n"
        "Te han invitado a unirte a «IA Week»:\n"
        "http://localhost:8080/invitacion?token=abc\n\n"
        "El enlace caduca en 7 días."
    )
    with patch("app.core.email.aiosmtplib.send", new=AsyncMock()) as enviar:
        await email.enviar_con(
            _config(), to="ana@ejemplo.org", subject="Te han invitado", body=cuerpo
        )
    mensaje = enviar.await_args.args[0]
    assert mensaje["To"] == "ana@ejemplo.org"
    assert mensaje.get_content_type() == "multipart/alternative"
    partes = list(mensaje.walk())
    tipos = [parte.get_content_type() for parte in partes]
    assert "text/plain" in tipos
    assert "text/html" in tipos
    # El texto plano llega intacto (salvo el salto de línea final que
    # `set_content` añade a todo mensaje): los clientes sin HTML no pierden
    # nada.
    texto = next(p for p in partes if p.get_content_type() == "text/plain")
    assert texto.get_content() == cuerpo + "\n"
    # El HTML lleva el enlace de verdad, no la URL a pelo envuelta.
    html_ = next(p for p in partes if p.get_content_type() == "text/html").get_content()
    assert '<a href="http://localhost:8080/invitacion?token=abc">' in html_


async def test_con_adjuntos_el_alternativo_es_la_primera_parte() -> None:
    adjunto = email.EmailAttachment(
        filename="entrada.png", content=b"\x89PNG", maintype="image", subtype="png"
    )
    with patch("app.core.email.aiosmtplib.send", new=AsyncMock()) as enviar:
        await email.enviar_con(
            _config(),
            to="ana@ejemplo.org",
            subject="Tu inscripción está confirmada",
            body="Hola,\n\nTu inscripción está confirmada.",
            attachments=(adjunto,),
        )
    mensaje = enviar.await_args.args[0]
    assert mensaje.get_content_type() == "multipart/mixed"
    sub = [
        parte
        for parte in mensaje.walk()
        if parte.get_content_type() in {"multipart/alternative", "image/png"}
    ]
    tipos = [parte.get_content_type() for parte in sub]
    assert "multipart/alternative" in tipos
    assert "image/png" in tipos
