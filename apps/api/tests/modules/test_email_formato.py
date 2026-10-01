"""Formato del correo saliente: plantilla con cabecera, botón y pie legal.

Los cuerpos son texto plano con la URL a pelo. El envío centralizado
(`enviar_con`) aplica la plantilla de plataforma a todos los correos sin tocar
las tareas:

- **texto plano** intacto + pie con los enlaces legales (los clientes sin HTML
  reciben el cuerpo y, por debajo, las URLs legales en línea);
- **HTML** con cabecera (logo de la plataforma embebido por `cid:` + acento),
  el cuerpo, un **botón de acción** (la URL del cuerpo, promovida para no
  duplicarla) y el pie;
- el logo **no** rompe el envío: si no hay logo, el correo va con la marca.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core import email, email_template
from app.modules.email_settings import presets

BASE = "https://eventarium.org"


def _config() -> presets.ConfigSmtp:
    return presets.ConfigSmtp(
        host="correo.de.prueba",
        port=587,
        username="",
        password="",
        tls_mode="starttls",
        from_address="no-responder@eventarium.org",
    )


@contextmanager
def _plataforma(con_logo: bool = False, base_url: str = BASE):
    """Parchea la identidad de plataforma y el `web_base_url` del envío.

    Así los tests no abren sesión ni tocan el almacén: `branding_efectiva`
    devuelve el `Branding` que pedimos y `get_settings` la base fija.
    """
    branding = email.Branding(
        nombre="Eventarium",
        logo=b"\x89PNG" if con_logo else None,
        logo_mime="image/png" if con_logo else None,
    )
    with (
        patch("app.core.email.branding_efectiva", new=AsyncMock(return_value=branding)),
        patch("app.core.email.get_settings", return_value=SimpleNamespace(web_base_url=base_url)),
    ):
        yield base_url


async def _enviar(body: str, *, con_logo: bool = False, adjuntos=(), base_url: str = BASE):
    """Lanza `enviar_con` con la plataforma parcheada y devuelve el mensaje."""
    with (
        patch("app.core.email.aiosmtplib.send", new=AsyncMock()) as enviar,
        _plataforma(con_logo=con_logo, base_url=base_url),
    ):
        await email.enviar_con(
            _config(), to="ana@ejemplo.org", subject="Asunto", body=body, attachments=adjuntos
        )
    return enviar.await_args.args[0]


# --- La plantilla (capa pura, sin SMTP) ---


def test_el_html_convierte_las_urls_en_enlaces_y_escapa_el_resto() -> None:
    html_ = email_template.texto_a_html(
        "Confirma tu correo:\nhttp://localhost:8080/verificar-correo?token=abc\n"
    )
    assert '<a href="http://localhost:8080/verificar-correo?token=abc">' in html_
    # Un nombre o una organización con `&` no puede abrir estructura propia.
    con_especial = email_template.texto_a_html("Organización «A & B» <reunion>")
    assert "A &amp; B" in con_especial
    assert "<reunion>" not in con_especial


def test_la_plantilla_lleva_cabecera_cuerpo_y_pie_legal() -> None:
    html_ = email_template.plantilla_html(
        "Hola,\n\nEsto es el cuerpo.",
        nombre_marca="Eventarium",
        logo_html=None,
        base_url=BASE,
    )
    # Cabecera: el nombre de marca (sin logo, cae a la marca).
    assert "Eventarium" in html_
    # Cuerpo.
    assert "Esto es el cuerpo." in html_
    # Pie: las tres URLs legales, resueltas contra la base.
    assert f"{BASE}/legal/aviso-legal" in html_
    assert f"{BASE}/legal/privacidad" in html_
    assert f"{BASE}/legal/cookies" in html_


def test_una_url_del_cuerpo_se_promociona_a_boton_sin_duplicarla() -> None:
    url = f"{BASE}/verificar?token=abc"
    html_ = email_template.plantilla_html(
        f"Hola,\n\nConfirma tu correo:\n{url}\n\nCaduca en 24 horas.",
        nombre_marca="Eventarium",
        logo_html=None,
        base_url=BASE,
    )
    # La URL es el botón («Abrir»), no un enlace de texto.
    assert f'<a href="{url}" ' in html_
    assert ">Abrir</a>" in html_
    # No sale dos veces: no hay `<a href="url">url</a>` en el cuerpo.
    assert f">{url}</a>" not in html_


def test_con_dos_urls_la_primera_es_el_boton_y_la_segunda_enlace() -> None:
    accion = f"{BASE}/mi-entrada"
    cancelar = f"{BASE}/cancelar"
    html_ = email_template.plantilla_html(
        f"Hola,\n\nTu entrada:\n{accion}\n\nPara cancelar:\n{cancelar}",
        nombre_marca="Eventarium",
        logo_html=None,
        base_url=BASE,
    )
    # La primera se promociona a botón…
    assert f'<a href="{accion}" ' in html_
    assert f">{accion}</a>" not in html_
    # …y la segunda queda como enlace de texto en el cuerpo.
    assert f'<a href="{cancelar}">{cancelar}</a>' in html_


def test_sin_url_no_hay_boton() -> None:
    html_ = email_template.plantilla_html(
        "Hola,\n\nTu correo cambiará a otra dirección.",
        nombre_marca="Eventarium",
        logo_html=None,
        base_url=BASE,
    )
    assert ">Abrir</a>" not in html_


def test_el_pie_de_texto_plano_lleva_las_tres_urls() -> None:
    pie = email_template.pie_texto_plano(base_url=BASE)
    assert f"{BASE}/legal/aviso-legal" in pie
    assert f"{BASE}/legal/privacidad" in pie
    assert f"{BASE}/legal/cookies" in pie


def test_invalidar_branding_borra_la_caché_del_logo() -> None:
    """`invalidar_branding_en_cache` deja la caché a `None`.

    El router de identidad la llama al subir el logo: sin esto, el proceso que
    guardó el logo seguiría enviando el anterior hasta el TTL de 30 s.
    """
    email._cache_branding = (999.0, email.Branding(nombre="Eventarium"))
    email.invalidar_branding_en_cache()
    assert email._cache_branding is None


# --- El envío completo (MIME) ---


async def test_el_envio_lleva_cuerpo_intacto_y_pie_en_texto_plano() -> None:
    cuerpo = (
        "Hola,\n\n"
        "Te han invitado a unirte a «IA Week»:\n"
        f"{BASE}/invitacion?token=abc\n\n"
        "El enlace caduca en 7 días."
    )
    mensaje = await _enviar(cuerpo)
    assert mensaje.get_content_type() == "multipart/alternative"
    partes = list(mensaje.walk())
    texto = next(p for p in partes if p.get_content_type() == "text/plain")
    # El cuerpo llega intacto y por debajo, el pie legal (salvo el salto final
    # que `set_content` añade a todo mensaje de texto).
    esperado = f"{cuerpo}\n\n{email_template.pie_texto_plano(base_url=BASE)}\n"
    assert texto.get_content() == esperado
    html_ = next(p for p in partes if p.get_content_type() == "text/html").get_content()
    assert f'<a href="{BASE}/invitacion?token=abc" ' in html_


async def test_el_logo_se_embebe_por_cid_y_se_referencia_en_el_html() -> None:
    mensaje = await _enviar("Hola,\n\nEsto llega con logo.", con_logo=True)
    partes = list(mensaje.walk())
    html_ = next(p for p in partes if p.get_content_type() == "text/html").get_content()
    assert 'src="cid:logo@eventarium"' in html_
    logo = next(
        (
            p
            for p in partes
            if p.get_content_type() == "image/png"
            and "logo@eventarium" in (p.get("Content-ID") or "")
        ),
        None,
    )
    assert logo is not None


async def test_sin_logo_el_correo_llega_con_la_marca_y_sin_imagen() -> None:
    mensaje = await _enviar("Hola,\n\nEsto llega sin logo.")
    partes = list(mensaje.walk())
    # No hay ninguna parte de imagen (ni logo embebido ni adjunto).
    assert not [p for p in partes if p.get_content_type().startswith("image/")]
    html_ = next(p for p in partes if p.get_content_type() == "text/html").get_content()
    assert "Eventarium" in html_


async def test_con_adjunto_el_alternativo_y_la_plantilla_se_mantienen() -> None:
    adjunto = email.EmailAttachment(
        filename="entrada.png", content=b"\x89PNG", maintype="image", subtype="png"
    )
    mensaje = await _enviar("Hola,\n\nTu entrada está lista.", adjuntos=(adjunto,))
    assert mensaje.get_content_type() == "multipart/mixed"
    partes = list(mensaje.walk())
    tipos = [p.get_content_type() for p in partes]
    assert "multipart/alternative" in tipos
    assert "text/plain" in tipos
    assert "text/html" in tipos
    assert tipos.count("image/png") == 1
    # La plantilla sigue en el HTML del alternativo.
    html_ = next(p for p in partes if p.get_content_type() == "text/html").get_content()
    assert f"{BASE}/legal/aviso-legal" in html_


async def test_con_logo_y_adjunto_coexisten_el_embedido_y_el_qr() -> None:
    adjunto = email.EmailAttachment(
        filename="entrada.png", content=b"\x89PNG", maintype="image", subtype="png"
    )
    mensaje = await _enviar("Hola,\n\nConfirmada.", con_logo=True, adjuntos=(adjunto,))
    partes = list(mensaje.walk())
    # Dos PNG: el logo (embebedido, con Content-ID) y el QR (adjunto).
    pngs = [p for p in partes if p.get_content_type() == "image/png"]
    assert len(pngs) == 2
    assert any("logo@eventarium" in (p.get("Content-ID") or "") for p in pngs)
    assert any(p.get_filename() == "entrada.png" for p in pngs)
