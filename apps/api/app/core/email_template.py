"""Plantilla de correo saliente: cabecera con logo, cuerpo y pie legal.

Todos los correos de la plataforma pasan por `enviar_con` (`core/email.py`),
que aplica esta plantilla al cuerpo. El objetivo es dar el mismo aspecto a los
~16 tipos de correo (invitaciones, verificación, recuperación, inscripciones,
pago, ponentes…) sin tocar una sola tarea: el punto de inserción es único.

El renderizado vive **aquí**, no en `email.py`: convertir el cuerpo en HTML,
detectar la URL de acción y armar cabecera/pie no depende de nada del envío
(SMTP, caché de configuración, adjuntos). `email.py` es la capa de envío y
depende de esta, nunca al revés. Así el HTML de correo se puede testear sin
tocar `aiosmtplib`.

Dos decisiones que condicionan el diseño:

- **El logo va por `cid:` (recursos embebidos), no por URL externa.** Gmail
  bloquea las imágenes externas por defecto; el `cid:` no. `email.py` lee los
  bytes del logo del almacén y los adjunta como parte embebida, y `plantilla`
  recibe ya el `<img>` referenciado (o `None` → cabecera solo con la marca).
- **El botón de acción se detecta en el cuerpo, no se pasa como parámetro.**
  Los cuerpos son texto plano con la URL a pelo, y casi todos tienen una URL de
  acción. Se mira el cuerpo: 1 URL → botón; >1 → la primera es el botón y el
  resto enlaces; 0 → sin botón. Se **promociona** la URL (se quita del párrafo
  y se renderiza solo como botón) para no mostrarla dos veces: `texto_a_html`
  ya la convertiría en un `<a href>` dentro del cuerpo.

El HTML de correo es limitado a propósito: tablas simples + estilos inline,
lo que Gmail y Outlook respetan. El *cuerpo* sigue siendo el de `texto_a_html`
(`<p>` simple, sin CSS ni tablas); solo el *envoltorio* (cabecera, botón, pie)
usa tablas + inline.
"""

from __future__ import annotations

import html
import re

#: Teal de marca (acento de la cabecera y del botón).
TEAL_MARCA = "#1B94A5"
#: Gris del pie de página (discreto, no compite con el cuerpo).
GRIS_PIE = "#6b7280"
GRIS_PIE_BORDE = "#e5e7eb"

#: URL hasta el siguiente espacio o `<`. La regex no descarta un punto de
#: frase colado al final — solo lo evita de facto porque los cuerpos del
#: sistema llevan cada URL sola en su línea (ver `tasks.py`), sin texto pegado.
#: La detección del botón y la conversión a enlaces comparten esta misma
#: expresión, de modo que lo que `texto_a_html` convierte en `<a href>` es
#: exactamente lo que `detectar_accion` ve.
_RE_ENLACE = re.compile(r"https?://[^\s<]+")


def _linea_a_html(linea: str) -> str:
    """Una línea del cuerpo: cada URL se convierte en `<a href>` de verdad.

    Se escapa **antes** de sustituir: el enlace resultante lleva su propio
    `&amp;` ya escapado, válido tanto en el atributo `href` como en el texto.
    """

    def sustituir(match: re.Match[str]) -> str:
        url = html.escape(match.group(0))
        return f'<a href="{url}">{url}</a>'

    return _RE_ENLACE.sub(sustituir, html.escape(linea))


def texto_a_html(cuerpo: str) -> str:
    """Versión HTML del cuerpo en texto plano, con enlaces de verdad.

    Todos los cuerpos del sistema siguen el mismo patrón (párrafos
    separados por línea en blanco, las URLs solas en su línea), y el
    resultado va solo al cliente de correo que prefiere HTML:

    - cada párrafo es un `<p>` (los clientes de correo se llevan bien solo
      con lo más básico: ni CSS ni tablas);
    - cada URL se convierte en `<a href>`: los clientes de correo móvil
      envuelven una URL larga en mitad de línea y el enlace de texto plano
      se rompe al pulsarlo; con el elemento real se toca igual;
    - el resto se escapa, para que un nombre con `&` o `<` no se trague la
      estructura.

    El texto plano original viaja siempre como alternativa (ver
    `enviar_con`): los clientes que solo lean texto reciben el cuerpo
    intacto.
    """
    parrafos = (
        [_linea_a_html(linea) for linea in bruto.split("\n") if linea.strip()]
        for bruto in cuerpo.split("\n\n")
    )
    return "".join(f"<p>{' '.join(partes)}</p>" for partes in parrafos if partes)


def detectar_accion(cuerpo: str) -> str | None:
    """La URL de acción del cuerpo: la primera URL que aparece.

    `None` si el cuerpo no tiene ninguna URL (avisos sin enlace: cambio de
    correo, suplantación, rechazo, cancelación, evento cancelado).
    """
    match = _RE_ENLACE.search(cuerpo)
    return match.group(0) if match else None


def pie_texto_plano(*, base_url: str) -> str:
    """El pie legal en líneas, para la alternativa de texto plano.

    El cuerpo llega intacto; esto solo añade las tres URLs legales por debajo.
    """
    return f"—\n{base_url}/legal/aviso-legal\n{base_url}/legal/privacidad\n{base_url}/legal/cookies"


def _boton(url: str) -> str:
    """El `<a>` de un botón de acción (centrado por su `<td>` en `plantilla_html`).

    Texto grande y en negrita: el teal de marca sobre blanco da ≈3,6:1, que
    pasa AA para texto grande pero no para texto normal (ver predict).
    """
    seguro = html.escape(url, quote=True)
    return (
        f'<a href="{seguro}" '
        'style="display:inline-block;padding:14px 28px;background-color:#1B94A5;'
        "color:#ffffff;text-decoration:none;font-family:Arial,Helvetica,sans-serif;"
        'font-size:16px;font-weight:bold;border-radius:6px;">Abrir</a>'
    )


def _cabecera(nombre_marca: str, logo_html: str | None) -> str:
    """Cabecera: logo (si lo hay) + nombre de marca, con la línea teal."""
    nombre_seguro = html.escape(nombre_marca)
    if logo_html:
        marca = logo_html
    else:
        marca = (
            '<div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;'
            f'font-weight:bold;color:{TEAL_MARCA};">{nombre_seguro}</div>'
        )
    return (
        '<tr><td align="center" style="padding:24px 0 16px;">'
        f"{marca}"
        "</td></tr>"
        f'<tr><td style="padding:0 0 8px;"><div style="height:3px;width:64px;margin:0 auto;'
        f'background-color:{TEAL_MARCA};"></div></td></tr>'
    )


def _rótulo(url: str) -> str:
    """Rótulo legible de un enlace legal, sacado del último segmento de la ruta."""
    segmentos = [s for s in url.rstrip("/").split("/") if s]
    if not segmentos:
        return url
    return segmentos[-1].replace("-", " ").title()


def _pie_html(base_url: str) -> str:
    """Pie: tres enlaces legales en gris, centrados."""
    enlaces = (
        f"{base_url}/legal/aviso-legal",
        f"{base_url}/legal/privacidad",
        f"{base_url}/legal/cookies",
    )
    items = " &middot; ".join(
        f'<a href="{html.escape(u, quote=True)}" '
        f'style="color:{GRIS_PIE};text-decoration:none;">'
        f"{html.escape(_rótulo(u))}</a>"
        for u in enlaces
    )
    return (
        '<tr><td align="center" style="padding:16px 0 24px;">'
        f'<div style="height:1px;background-color:{GRIS_PIE_BORDE};margin:0 0 16px;"></div>'
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;'
        f'color:{GRIS_PIE};line-height:1.8;">{items}</div>'
        "</td></tr>"
    )


def _cuerpo_y_boton(cuerpo: str) -> tuple[str, str | None]:
    """El cuerpo en HTML + la URL de acción, **promoviendo** el botón.

    Devuelve `(html_cuerpo, url_accion)`. La URL de acción se quita del párrafo
    (para que no salga dos veces: ni como botón ni como `<a>` en el cuerpo) y
    se devuelve aparte para que el llamador la renderice como botón.

    El párrafo que contiene la URL se recorta: si el párrafo era solo la URL,
    desaparece; si tenía más texto (p. ej. «…desde este enlace:\n{url}»), se
    queda el texto y la URL se va al botón.
    """
    url_accion = detectar_accion(cuerpo)
    if url_accion is None:
        return texto_a_html(cuerpo), None

    parrafos = cuerpo.split("\n\n")
    salidos: list[str] = []
    para_boton = False
    for bruto in parrafos:
        lineas = bruto.split("\n")
        lineas_url = [i for i, linea in enumerate(lineas) if _RE_ENLACE.fullmatch(linea.strip())]
        if lineas_url:
            # Solo se promociona la primera URL del cuerpo: el resto de URLs
            # (p. ej. la de cancelación) se quedan como enlaces en el cuerpo.
            if not para_boton:
                para_boton = True
                lineas = [linea for i, linea in enumerate(lineas) if i not in lineas_url]
        limpio = " ".join(linea for linea in lineas if linea.strip())
        if limpio:
            salidos.append(limpio)

    html_cuerpo = "".join(f"<p>{_linea_a_html(p)}</p>" for p in salidos)
    return html_cuerpo, url_accion


def plantilla_html(
    cuerpo: str,
    *,
    nombre_marca: str,
    logo_html: str | None,
    base_url: str,
) -> str:
    """El mensaje completo en HTML: cabecera + cuerpo (+ botón) + pie.

    `cuerpo` es el texto plano original: aquí se promueve la URL de acción y se
    convierte el resto a HTML. `logo_html` es el `<img src="cid:...">` ya
    construido por `email.py` (o `None` si no hay logo → la cabecera se queda
    con el nombre de marca).
    """
    html_cuerpo, url_accion = _cuerpo_y_boton(cuerpo)
    boton = (
        f'<tr><td align="center" style="padding:16px 32px 0;">{_boton(url_accion)}</td></tr>'
        if url_accion is not None
        else ""
    )
    return (
        '<!DOCTYPE html><html><body style="margin:0;padding:0;background-color:#f4f5f7;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f4f5f7;">'
        '<tr><td align="center" style="padding:16px;">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;width:100%;background-color:#ffffff;border-radius:8px;'
        'overflow:hidden;">'
        f"{_cabecera(nombre_marca, logo_html)}"
        f'<tr><td style="padding:8px 32px;">{html_cuerpo}</td></tr>'
        f"{boton}"
        f"{_pie_html(base_url)}"
        "</table></td></tr></table></body></html>"
    )
