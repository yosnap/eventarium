"""Plantillas por defecto de las páginas legales de la plataforma.

Mismas reglas que las de organización (`legal/templates.py`): f-strings, sin
motor de plantillas, Markdown restringido a lo que el saneado del frontend
declara en su lista blanca (párrafos, negrita/cursiva, listas y enlaces). La
diferencia es que aquí no hay una `Organization` de la que sacar los datos: el
responsable es la plataforma, así que los datos identificativos son los que el
admin haya rellenado en la identidad de plataforma.
"""

from __future__ import annotations

from app.modules.platform.models import PlatformBranding


def _nombre(branding: PlatformBranding) -> str:
    return branding.name


def legal_notice_template(branding: PlatformBranding, sitio: str) -> str:
    """Aviso legal de la plataforma (LSSI-CE)."""
    nombre = _nombre(branding)
    return (
        f"**Identificación del responsable**\n\n"
        f"En cumplimiento del deber de información de la Ley 34/2002, de "
        f"Servicios de la Sociedad de la Información y de Comercio "
        f"Electrónico (LSSI-CE), se informa de que **{nombre}** es la "
        f"plataforma que opera el sitio {sitio}.\n\n"
        f"**Qué es esta plataforma**\n\n"
        f"{nombre} es un software de gestión de eventos: cada organización "
        f"publica en él sus propios eventos y gestiona sus inscripciones. "
        f"{nombre} presta la herramienta; no organiza los eventos que se "
        f"publican en ella.\n\n"
        f"**Responsabilidad de cada organización**\n\n"
        f"Cada organización es la responsable de sus eventos: de su "
        f"celebración, de la información que publica sobre ellos y de sus "
        f"propias políticas y condiciones (precios, admisión, cancelaciones, "
        f"reembolsos o grabación, entre otras). {nombre} no es parte de la "
        f"relación entre la organización y quienes se inscriben a sus "
        f"eventos.\n\n"
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


def privacy_policy_template(branding: PlatformBranding, sitio: str) -> str:
    """Política de privacidad de la plataforma."""
    nombre = _nombre(branding)
    return (
        f"**Quién trata tus datos**\n\n"
        f"En {sitio} intervienen dos responsables distintos, según el "
        f"dato:\n\n"
        f"- **Tu cuenta**: **{nombre}**, que opera la plataforma, es "
        f"responsable de los datos de tu cuenta (nombre, correo y "
        f"credenciales) y de los datos técnicos necesarios para que el "
        f"servicio funcione y sea seguro.\n"
        f"- **Tus inscripciones**: la organización que publica cada evento "
        f"es la responsable de los datos que aportas al inscribirte a él. "
        f"Los trata según su propia política de privacidad, y {nombre} "
        f"solo los trata por su encargo, para prestarle el servicio.\n\n"
        f"**Qué datos tratamos**\n\n"
        f"Datos de cuenta, datos técnicos del servicio y, por encargo de "
        f"cada organización, los datos que aportas al inscribirte a sus "
        f"eventos (nombre, correo y las respuestas del formulario de "
        f"inscripción).\n\n"
        f"**Para qué**\n\n"
        f"Prestar el servicio, autenticarte, garantizar la seguridad, "
        f"cumplir las obligaciones legales aplicables y, por cuenta de cada "
        f"organización, gestionar tus inscripciones a sus eventos. {nombre} "
        f"no usa los datos de tus inscripciones para fines propios.\n\n"
        f"**Tus derechos**\n\n"
        f"Puedes ejercer tus derechos de acceso, rectificación, supresión, "
        f"oposición, limitación y portabilidad. Sobre tu cuenta, escribe a "
        f"la dirección de contacto de la plataforma; sobre una inscripción, "
        f"a la organización del evento. Si nos escribes por una inscripción, "
        f"trasladaremos tu solicitud a esa organización.\n\n"
        f"**Conservación**\n\n"
        f"Conservamos los datos de tu cuenta mientras esté activa y, "
        f"después, durante los plazos legales aplicables. Los datos de cada "
        f"inscripción se conservan durante el plazo que fije la organización "
        f"del evento.\n"
    )


def cookies_policy_template(branding: PlatformBranding, sitio: str) -> str:
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


def registration_terms_template(branding: PlatformBranding, sitio: str) -> str:
    """Condiciones de inscripción a eventos, comunes a toda la plataforma."""
    nombre = _nombre(branding)
    return (
        f"**Condiciones de inscripción**\n\n"
        f"Los eventos publicados en **{nombre}** los organiza cada "
        f"organización, no {nombre}. Al inscribirte a un evento aceptas "
        f"estas condiciones generales y las condiciones propias de la "
        f"organización que lo publica.\n\n"
        f"**Condiciones de cada organización**\n\n"
        f"Cada organización fija sus propias políticas y condiciones: "
        f"precio, admisión, cancelación o cambio del evento, reembolsos, "
        f"grabación y cualquier otra que aplique. Las encontrarás en la "
        f"página de políticas del evento, enlazada desde su ficha y desde el "
        f"formulario de inscripción, y tendrás que aceptarlas al "
        f"inscribirte. Si el evento no tiene condiciones propias, aplican "
        f"estas condiciones generales. Si contradicen estas condiciones "
        f"generales, prevalecen las de la organización.\n\n"
        f"**Datos aportados**\n\n"
        f"Debes aportar datos veraces en el formulario de inscripción. La "
        f"organización del evento podrá anular una inscripción cuyos datos "
        f"resulten falsos o incompletos.\n\n"
        f"**Confirmación y lista de espera**\n\n"
        f"Tu plaza se confirma por correo electrónico. Si el aforo del "
        f"evento está completo, tu inscripción pasa a una lista de espera y "
        f"se te notificará si se libera una plaza. Si la organización revisa "
        f"las solicitudes a mano, la plaza no queda confirmada hasta que la "
        f"apruebe.\n\n"
        f"**Cancelación por tu parte**\n\n"
        f"Puedes cancelar tu inscripción desde el enlace incluido en el "
        f"correo de confirmación. Cancelar una plaza confirmada puede "
        f"liberarla para la siguiente persona en lista de espera. Si pagaste "
        f"una entrada, el reembolso depende de la política de la "
        f"organización.\n\n"
        f"**Grabación y publicación**\n\n"
        f"Si el formulario de inscripción lo indica, el evento puede ser "
        f"grabado y publicado; tu asistencia queda sujeta a las condiciones "
        f"de grabación que hayas aceptado al inscribirte.\n\n"
        f"**Contacto**\n\n"
        f"Para cualquier consulta sobre un evento o tu inscripción, escribe "
        f"a la organización del evento. Para problemas con la plataforma, a "
        f"la dirección de contacto de {nombre}.\n"
    )


_TEMPLATES = {
    "aviso-legal": legal_notice_template,
    "privacidad": privacy_policy_template,
    "cookies": cookies_policy_template,
    "condiciones-de-inscripcion": registration_terms_template,
}


def resolve_platform_legal_page(
    branding: PlatformBranding,
    sitio: str,
    page_key: str,
    contenido_editado: str | None,
) -> str:
    """Contenido efectivo de una página legal de plataforma.

    El editado por el admin si existe; si no, la plantilla por defecto.
    """
    if contenido_editado:
        return contenido_editado
    return _TEMPLATES[page_key](branding, sitio)
