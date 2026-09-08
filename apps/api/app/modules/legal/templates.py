"""Plantillas de texto/Markdown restringido de las cuatro páginas legales.

Fase 5 del PRD, fase 3 de trabajo. Compuestas con f-strings de Python, sin
motor de plantillas nuevo (decisión #2 del plan: Jinja2 no existe en el
proyecto — los emails de `app/core/tasks.py` tampoco lo usan — y añadirlo
solo para renderizar contenido editable por el tenant abriría XSS/SSTI).

Markdown restringido a lo que el frontend sanea con una lista blanca
explícita (`marked` + `DOMPurify`, ver `apps/web/src/app/shared/legal/
sanitize-markdown.ts`): párrafos, negrita/cursiva, listas y enlaces. Sin
encabezados Markdown (`#`) — los títulos de sección se marcan en negrita en
su lugar, para no depender de una etiqueta que el saneado del frontend no
declara en su lista blanca.
"""

from __future__ import annotations

from app.modules.organizations.models import Organization


def _entidad(organizacion: Organization) -> str:
    return organizacion.legal_name or organizacion.name


def _contacto(organizacion: Organization) -> str:
    return organizacion.contact_email or "sin correo de contacto registrado"


def _direccion(organizacion: Organization) -> str:
    return organizacion.legal_address or "sin dirección postal registrada"


def _nif(organizacion: Organization) -> str:
    return organizacion.tax_id or "sin NIF/CIF registrado"


def legal_notice_template(organizacion: Organization) -> str:
    """Aviso legal (LSSI-CE)."""
    entidad = _entidad(organizacion)
    return (
        f"**Identificación del responsable**\n\n"
        f"En cumplimiento del deber de información de la Ley 34/2002, de "
        f"Servicios de la Sociedad de la Información y de Comercio "
        f"Electrónico (LSSI-CE), se informa de los siguientes datos: la "
        f"presente web es operada por **{entidad}**, con NIF/CIF "
        f"{_nif(organizacion)} y domicilio en {_direccion(organizacion)}. "
        f"Puedes contactar con nosotros en {_contacto(organizacion)}.\n\n"
        f"**Objeto**\n\n"
        f"Esta web permite la publicación de eventos organizados por "
        f"{entidad} y la gestión de las inscripciones de las personas "
        f"asistentes.\n\n"
        f"**Condiciones de uso**\n\n"
        f"El acceso y uso de esta web atribuye la condición de persona "
        f"usuaria e implica la aceptación de las condiciones aquí "
        f"recogidas. La persona usuaria se compromete a hacer un uso "
        f"adecuado de los contenidos y servicios que {entidad} ofrece a "
        f"través de esta web y a no emplearlos para incurrir en "
        f"actividades ilícitas o contrarias a la buena fe y al "
        f"ordenamiento legal.\n\n"
        f"**Propiedad intelectual**\n\n"
        f"Los contenidos de esta web (textos, imágenes y marcas) son "
        f"propiedad de {entidad} o de terceros que han autorizado su uso, "
        f"y están protegidos por la normativa de propiedad intelectual e "
        f"industrial.\n\n"
        f"**Legislación aplicable**\n\n"
        f"Las presentes condiciones se rigen por la legislación española. "
        f"Para cualquier controversia serán competentes los juzgados y "
        f"tribunales del domicilio de {entidad}, salvo que la normativa "
        f"de consumidores y usuarios establezca otro fuero."
    )


def privacy_policy_template(organizacion: Organization) -> str:
    """Política de privacidad (RGPD/LOPDGDD)."""
    entidad = _entidad(organizacion)
    return (
        f"**Responsable del tratamiento**\n\n"
        f"**{entidad}**, con NIF/CIF {_nif(organizacion)} y domicilio en "
        f"{_direccion(organizacion)}, es responsable del tratamiento de "
        f"los datos personales recogidos a través de esta web. Puedes "
        f"contactar con nosotros en {_contacto(organizacion)}.\n\n"
        f"**Datos que tratamos**\n\n"
        f"Al inscribirte a un evento tratamos tu nombre, correo "
        f"electrónico y las respuestas que aportes a las preguntas del "
        f"formulario de inscripción. Al aceptar el banner de cookies "
        f"tratamos, sin ningún dato que te identifique, las categorías de "
        f"cookies que decides aceptar o rechazar.\n\n"
        f"**Finalidad y legitimación**\n\n"
        f"- Gestionar tu inscripción a los eventos que organiza "
        f"{entidad}: base legal, la ejecución de la relación que "
        f"estableces con nosotros al inscribirte.\n"
        f"- Enviarte comunicaciones sobre el evento al que te has "
        f"inscrito: base legal, tu consentimiento explícito.\n"
        f"- Grabar y publicar el evento cuando así se indique en el "
        f"formulario de inscripción: base legal, tu consentimiento "
        f"explícito.\n\n"
        f"**Conservación**\n\n"
        f"Conservamos tus datos mientras mantengas una relación con "
        f"nosotros y, después, durante los plazos legalmente exigibles.\n\n"
        f"**Derechos**\n\n"
        f"Puedes ejercer tus derechos de acceso, rectificación, "
        f"supresión, oposición, limitación y portabilidad escribiendo a "
        f"{_contacto(organizacion)}. También puedes reclamar ante la "
        f"Agencia Española de Protección de Datos "
        f"([www.aepd.es](https://www.aepd.es))."
    )


def cookies_policy_template(organizacion: Organization) -> str:
    """Política de cookies. Declara Turnstile explícitamente como necesaria."""
    entidad = _entidad(organizacion)
    return (
        f"**¿Qué son las cookies?**\n\n"
        f"Las cookies son pequeños ficheros que esta web guarda en tu "
        f"navegador para recordar información entre visitas.\n\n"
        f"**Categorías de cookies que usamos**\n\n"
        f"- **Necesarias**: imprescindibles para que la web funcione "
        f"(navegación, seguridad). No se pueden rechazar porque no "
        f"implican rastreo, solo el funcionamiento básico del sitio.\n"
        f"- **Analíticas**: nos ayudan a entender cómo se usa la web, "
        f"solo si las aceptas.\n"
        f"- **Marketing**: se usan para mostrar contenido adaptado a tus "
        f"intereses, solo si las aceptas.\n\n"
        f"**Cloudflare Turnstile**\n\n"
        f"El formulario público de inscripción a eventos usa Cloudflare "
        f"Turnstile, un script de verificación antibot que carga "
        f"`challenges.cloudflare.com`. Lo clasificamos como **necesario**, "
        f"con base legal de **interés legítimo** (seguridad frente a "
        f"inscripciones automatizadas y abuso del formulario público): "
        f"sin él, el formulario de inscripción no puede protegerse frente "
        f"a bots, por lo que sigue cargando decidas lo que decidas sobre "
        f"el resto de categorías del banner de cookies.\n\n"
        f"**Cómo gestionar tus preferencias**\n\n"
        f"Puedes aceptar todas las cookies, rechazar todas las que no son "
        f"necesarias, o personalizar tu elección por categoría desde el "
        f"banner que aparece en tu primera visita. Puedes cambiar tu "
        f"decisión en cualquier momento borrando las cookies de tu "
        f"navegador, lo que hará que el banner vuelva a aparecer.\n\n"
        f"Para cualquier duda sobre esta política puedes escribir a "
        f"{_contacto(organizacion)} ({entidad})."
    )


def registration_terms_template(organizacion: Organization) -> str:
    """Condiciones de inscripción a eventos."""
    entidad = _entidad(organizacion)
    return (
        f"**Condiciones de inscripción**\n\n"
        f"Al inscribirte a un evento organizado por **{entidad}** aceptas "
        f"las siguientes condiciones.\n\n"
        f"**Datos aportados**\n\n"
        f"Debes aportar datos veraces en el formulario de inscripción. "
        f"{entidad} podrá anular una inscripción cuyos datos resulten "
        f"falsos o incompletos.\n\n"
        f"**Confirmación y lista de espera**\n\n"
        f"Tu plaza se confirma por correo electrónico. Si el aforo del "
        f"evento está completo, tu inscripción pasa a una lista de "
        f"espera y se te notificará si se libera una plaza.\n\n"
        f"**Cancelación**\n\n"
        f"Puedes cancelar tu inscripción en cualquier momento desde el "
        f"enlace incluido en el correo de confirmación. Cancelar una "
        f"plaza confirmada puede liberarla para la siguiente persona en "
        f"lista de espera.\n\n"
        f"**Grabación y publicación**\n\n"
        f"Si el formulario de inscripción lo indica, el evento puede ser "
        f"grabado y publicado; tu asistencia queda sujeta a las "
        f"condiciones de grabación que hayas aceptado al inscribirte.\n\n"
        f"**Contacto**\n\n"
        f"Para cualquier consulta sobre tu inscripción puedes escribir a "
        f"{_contacto(organizacion)}."
    )


#: Mapa de clave pública → función de plantilla y campo de `Organization`.
LEGAL_PAGES: dict[str, tuple[str, str]] = {
    "aviso-legal": ("legal_notice_content", "legal_notice_template"),
    "privacidad": ("privacy_policy_content", "privacy_policy_template"),
    "cookies": ("cookies_policy_content", "cookies_policy_template"),
    "condiciones-de-inscripcion": (
        "registration_terms_content",
        "registration_terms_template",
    ),
}

_TEMPLATE_FUNCTIONS = {
    "legal_notice_template": legal_notice_template,
    "privacy_policy_template": privacy_policy_template,
    "cookies_policy_template": cookies_policy_template,
    "registration_terms_template": registration_terms_template,
}


def resolve_legal_page(organizacion: Organization, page_key: str) -> str:
    """Contenido efectivo de una página legal: el editado, o la plantilla."""
    campo, funcion_nombre = LEGAL_PAGES[page_key]
    editado: str | None = getattr(organizacion, campo)
    if editado:
        return editado
    return _TEMPLATE_FUNCTIONS[funcion_nombre](organizacion)
