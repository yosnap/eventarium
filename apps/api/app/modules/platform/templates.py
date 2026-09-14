"""Plantillas por defecto de las páginas legales de la plataforma.

Mismas reglas que las de organización (`legal/templates.py`): f-strings, sin
motor de plantillas, Markdown restringido a lo que el saneado del frontend
declara en su lista blanca (párrafos, negrita/cursiva, listas y enlaces). La
diferencia es que aquí no hay una `Organization` de la que sacar los datos: el
responsable es la plataforma, así que los datos identificativos son los que el
admin haya rellenado en la identidad de plataforma.
"""

from __future__ import annotations

from app.modules.platform.models import PlatformBranding, PlatformDomain


def _nombre(branding: PlatformBranding) -> str:
    return branding.name


def _sitios(dominios: list[PlatformDomain]) -> str:
    if not dominios:
        return "sin dominio público registrado"
    return ", ".join(dominio.host for dominio in dominios)


def legal_notice_template(branding: PlatformBranding, dominios: list[PlatformDomain]) -> str:
    """Aviso legal de la plataforma (LSSI-CE)."""
    nombre = _nombre(branding)
    return (
        f"**Identificación del responsable**\n\n"
        f"En cumplimiento del deber de información de la Ley 34/2002, de "
        f"Servicios de la Sociedad de la Información y de Comercio "
        f"Electrónico (LSSI-CE), se informa de que **{nombre}** es la "
        f"plataforma que opera los sitios {_sitios(dominios)}.\n\n"
        f"**Qué es esta plataforma**\n\n"
        f"{nombre} es un software de gestión de eventos: permite a cada "
        f"organización publicar sus eventos y gestionar las inscripciones, "
        f"bajo estas mismas condiciones y responsabilidad de {nombre}.\n\n"
        f"**Condiciones de uso**\n\n"
        f"El acceso y uso de la plataforma atribuye la condición de persona "
        f"usuaria e implica la aceptación de estas condiciones. La persona "
        f"usuaria se compromete a hacer un uso adecuado de los contenidos y "
        f"servicios y a no emplearlos para incurrir en actividades ilícitas "
        f"o contrarias a la buena fe y al ordenamiento legal.\n\n"
        f"**Propiedad intelectual**\n\n"
        f"El código de {nombre} es software libre. Los contenidos que cada "
        f"organización publica (textos, imágenes, marcas de sus eventos) son "
        f"suyos y ella responde de ellos.\n\n"
        f"**Legislación aplicable**\n\n"
        f"Esta relación se rige por la legislación española.\n"
    )


def privacy_policy_template(branding: PlatformBranding, dominios: list[PlatformDomain]) -> str:
    """Política de privacidad de la plataforma."""
    nombre = _nombre(branding)
    return (
        f"**Quién trata tus datos**\n\n"
        f"**{nombre}** opera la plataforma en los sitios {_sitios(dominios)} "
        f"y es responsable del tratamiento de los datos de tu cuenta y de "
        f"los que facilitas al inscribirte a cualquier evento publicado en "
        f"la plataforma.\n\n"
        f"**Qué datos tratamos**\n\n"
        f"Datos de cuenta (nombre, correo y credenciales), datos técnicos "
        f"necesarios para el funcionamiento y la seguridad del servicio, y "
        f"los datos que aportas al inscribirte a un evento (nombre, correo y "
        f"las respuestas del formulario de inscripción).\n\n"
        f"**Para qué**\n\n"
        f"Prestar el servicio, gestionar tu inscripción a los eventos a los "
        f"que te apuntes, autenticarte, garantizar la seguridad y cumplir "
        f"las obligaciones legales aplicables.\n\n"
        f"**Tus derechos**\n\n"
        f"Puedes ejercer tus derechos de acceso, rectificación, supresión, "
        f"oposición, limitación y portabilidad escribiendo a la dirección "
        f"de contacto de la plataforma.\n\n"
        f"**Conservación**\n\n"
        f"Conservamos los datos mientras la cuenta esté activa y, después, "
        f"durante los plazos legales aplicables.\n"
    )


def cookies_policy_template(branding: PlatformBranding, dominios: list[PlatformDomain]) -> str:
    """Política de cookies de la plataforma."""
    nombre = _nombre(branding)
    return (
        f"**¿Qué son las cookies?**\n\n"
        f"Las cookies son pequeños ficheros que esta web guarda en tu "
        f"navegador para recordar información entre visitas.\n\n"
        f"**Qué cookies usamos en {nombre}**\n\n"
        f"- **Necesarias**: imprescindibles para que la plataforma funcione "
        f"(sesión, seguridad). No se pueden rechazar porque no implican "
        f"rastreo, solo el funcionamiento básico del sitio.\n"
        f"- **Analíticas**: nos ayudan a entender cómo se usa la plataforma, "
        f"solo si las aceptas.\n"
        f"- **De marketing**: solo se activan si las aceptas.\n\n"
        f"**Cómo cambiar tu decisión**\n\n"
        f"Puedes volver a abrir el panel de cookies desde el enlace del pie "
        f"de página y cambiar tus preferencias en cualquier momento.\n\n"
        f"**Cookies de terceros**\n\n"
        f"Usamos Cloudflare Turnstile para proteger los formularios contra "
        f"automatizaciones; se declara como cookie necesaria.\n"
    )


def registration_terms_template(branding: PlatformBranding, dominios: list[PlatformDomain]) -> str:
    """Condiciones de inscripción a eventos, comunes a toda la plataforma."""
    nombre = _nombre(branding)
    return (
        f"**Condiciones de inscripción**\n\n"
        f"Al inscribirte a cualquier evento publicado en **{nombre}** "
        f"aceptas las siguientes condiciones.\n\n"
        f"**Datos aportados**\n\n"
        f"Debes aportar datos veraces en el formulario de inscripción. "
        f"{nombre} podrá anular una inscripción cuyos datos resulten falsos "
        f"o incompletos.\n\n"
        f"**Confirmación y lista de espera**\n\n"
        f"Tu plaza se confirma por correo electrónico. Si el aforo del "
        f"evento está completo, tu inscripción pasa a una lista de espera y "
        f"se te notificará si se libera una plaza.\n\n"
        f"**Cancelación**\n\n"
        f"Puedes cancelar tu inscripción en cualquier momento desde el "
        f"enlace incluido en el correo de confirmación. Cancelar una plaza "
        f"confirmada puede liberarla para la siguiente persona en lista de "
        f"espera.\n\n"
        f"**Grabación y publicación**\n\n"
        f"Si el formulario de inscripción lo indica, el evento puede ser "
        f"grabado y publicado; tu asistencia queda sujeta a las condiciones "
        f"de grabación que hayas aceptado al inscribirte.\n\n"
        f"**Contacto**\n\n"
        f"Para cualquier consulta sobre tu inscripción puedes escribir a la "
        f"dirección de contacto de la plataforma.\n"
    )


_TEMPLATES = {
    "aviso-legal": legal_notice_template,
    "privacidad": privacy_policy_template,
    "cookies": cookies_policy_template,
    "condiciones-de-inscripcion": registration_terms_template,
}


def resolve_platform_legal_page(
    branding: PlatformBranding,
    dominios: list[PlatformDomain],
    page_key: str,
    contenido_editado: str | None,
) -> str:
    """Contenido efectivo de una página legal de plataforma.

    El editado por el admin si existe; si no, la plantilla por defecto.
    """
    if contenido_editado:
        return contenido_editado
    return _TEMPLATES[page_key](branding, dominios)
