/**
 * Historial de cambios de la instalación, para `ChangelogPanel` en la portada
 * del panel de plataforma.
 *
 * Reconstruido a mano a partir del historial de git (`apps/web/package.json`
 * como reloj de versión) el 2026-09-16, agrupando los commits de cada
 * incremento de versión en cambios legibles por quien administra la
 * instalación, no por quien lee el código. Los merges y los commits
 * `chore(release)` sin sustancia propia no generan item: su contenido ya está
 * en los commits que agrupan. Mantenimiento en adelante: una entrada nueva al
 * principio del array en cada release con cambios visibles.
 */

import { CHANGELOG_ANTERIOR } from './changelog-anterior.data';

export type ChangelogCategoria = 'agregado' | 'modificado' | 'corregido';

export interface ChangelogItem {
  readonly titulo: string;
  readonly descripcion: string;
}

export interface ChangelogSeccion {
  readonly categoria: ChangelogCategoria;
  readonly items: readonly ChangelogItem[];
}

export interface ChangelogVersion {
  readonly version: string;
  readonly fecha: string;
  readonly secciones: readonly ChangelogSeccion[];
}

export const CHANGELOG: readonly ChangelogVersion[] = [
  {
    version: '0.30.0',
    fecha: '2026-11-13',
    secciones: [
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Publicar un evento de pago antes de abrir la venta',
            descripcion:
              'Un evento de pago se puede publicar aunque la venta de entradas empiece más tarde. Mientras no haya entradas a la venta, la ficha y el formulario dicen cuándo abre, o que la venta ha terminado, en lugar de mostrar un formulario gratuito. Un evento publicado se sigue pudiendo editar aunque su venta haya cerrado.',
          },
          {
            titulo: 'Reembolsos en la auditoría',
            descripcion:
              'Cada reembolso pedido desde el panel queda registrado en la auditoría con quién lo pidió, el importe y si anula la entrada.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Dependencias con avisos de seguridad',
            descripcion:
              'Se actualizan las librerías de la API y de la web con vulnerabilidades conocidas (Pillow, Angular, DOMPurify, LiteLLM, certifi, aiohttp, urllib3, entre otras).',
          },
        ],
      },
    ],
  },
  {
    version: '0.29.0',
    fecha: '2026-10-21',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Cómo llegar',
            descripcion:
              'La ficha de un evento presencial, y cada sede del programa, tienen un enlace que abre Google Maps con la ruta hasta el lugar desde donde esté la persona.',
          },
          {
            titulo: 'Qué hay cerca',
            descripcion:
              'En la ficha del evento del panel se añaden hoteles, restaurantes, bares, parkings, transporte, farmacias u otros sitios con dirección, teléfono, web y una nota, se ordenan y se copian de otro evento. La ficha pública los muestra agrupados por tipo. También por MCP.',
          },
          {
            titulo: 'Dirección y redes de la organización',
            descripcion:
              'La ficha de la organización guarda calle, código postal, ciudad y provincia (con una casilla para mostrarla o no en la página pública) y las redes: LinkedIn, Instagram, X, Facebook, YouTube, TikTok y un enlace libre con nombre. Las redes ya no se editan en «Marca».',
          },
          {
            titulo: '«Mis eventos» con la sesión iniciada',
            descripcion:
              'Quien tiene cuenta con el correo verificado ve sus inscripciones al entrar en «Mis eventos», sin pedir el enlace por correo. Se separan en Próximos y Pasados, con la hora en la zona del evento y «Añadir a mi calendario» en cada plaza confirmada.',
          },
          {
            titulo: 'Quitar la portada de un evento',
            descripcion:
              'La portada de un evento se puede quitar desde su ficha del panel; la imagen sigue en la biblioteca de medios.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Página pública de la organización renovada',
            descripcion:
              'El logo se ve grande en la mitad izquierda y los datos a la derecha (apilado en el móvil), con la dirección en líneas y las redes como botones con su icono.',
          },
          {
            titulo: 'Ficha del evento en dos columnas',
            descripcion:
              'Al editar un evento, el formulario queda a la izquierda y el estado, la cancelación, la portada y «Qué hay cerca» en una columna a la derecha.',
          },
          {
            titulo: 'Descansos visibles en la agenda',
            descripcion:
              'En la agenda pública, los descansos y servicios llevan un fondo propio para que se note la parada en el programa.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Avisos de plaza libre más fiables',
            descripcion:
              'El correo que ofrece una plaza de la lista de espera sale cuando el cambio ya está guardado, también al subir el aforo desde el asistente MCP. Y las pausas de la agenda ya no admiten ponentes tampoco por la API.',
          },
          {
            titulo: 'El enlace de «Mis eventos» ya no sale caducado',
            descripcion:
              'Al abrir el enlace del correo, la página lo daba por usado antes de mostrar las inscripciones y pedía uno nuevo.',
          },
        ],
      },
    ],
  },
  {
    version: '0.28.0',
    fecha: '2026-10-20',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Recordatorio a los inscritos antes del evento',
            descripcion:
              'Cada evento puede enviar un correo a sus inscritos confirmados de 2 horas a 3 días antes (1 día por defecto; 2 en los de pago, a tiempo de cancelar con devolución). Lleva la fecha y la hora del evento, el lugar o el enlace, la entrada con su QR y un enlace para cancelar si no se puede ir, y avisa de que las ausencias sin avisar pueden tenerse en cuenta. Se activa o desactiva en el formulario del evento.',
          },
          {
            titulo: 'Cierre de asistencia e historial de ausencias',
            descripcion:
              'Tras un evento presencial, quien hace el check-in cierra la asistencia (y puede reabrirla durante 7 días). Desde entonces, quien estaba confirmado, recibió el recordatorio y no se presentó sin cancelar aparece en las inscripciones con «Faltó a N eventos» de la organización en los últimos 12 meses. Nada se bloquea solo: decide el organizador. El formulario de inscripción lo informa.',
          },
          {
            titulo: 'Eventos «solo con enlace»',
            descripcion:
              'Además de Público y Privado, un evento puede ser «Solo con enlace»: lo abre e inscribe quien tenga la URL, pero no sale en la página de la organización, en el directorio ni en los buscadores. El formulario del evento explica cada opción y el listado del panel marca los que no son públicos.',
          },
          {
            titulo: 'El QR de la entrada, dentro del correo',
            descripcion:
              'El correo de confirmación muestra el código QR en el propio cuerpo, en vez de como adjunto.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Cancelar desde el correo pide confirmación',
            descripcion:
              'El enlace para cancelar ya no cancela al abrirse: enseña el evento y si se devolvería el pago, y solo cancela al pulsar «Sí, cancelar mi inscripción». Una vez empezado el evento ya no se puede cancelar desde el enlace ni se ofrece la plaza a la lista de espera.',
          },
          {
            titulo: 'Un reembolso total cancela la inscripción',
            descripcion:
              'Al devolver el importe completo de una entrada, desde el panel o desde Stripe, la inscripción se cancela, se revoca la entrada y la plaza pasa a la lista de espera.',
          },
          {
            titulo: 'Zona horaria validada',
            descripcion:
              'Las horas de los correos van en la zona horaria del evento, y al crear o editar un evento se rechaza una zona que no exista.',
          },
        ],
      },
    ],
  },
  {
    version: '0.27.25',
    fecha: '2026-10-20',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Tipos de sesión propios de cada organización',
            descripcion:
              'En «Tipos de sesión» cada organización renombra, ordena, colorea y desactiva sus tipos (Charla, Taller, Descanso, Servicio y Otro de serie) y crea los suyos, como Mesa redonda o Keynote. Los que son pausa se pintan apagados y no piden ponentes. La agenda pública muestra el nombre y el color de cada tipo, y el asistente por MCP los usa por su nombre.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Pagar una entrada, sin pasar antes por el correo',
            descripcion:
              'En un evento de pago, tras el formulario se va directamente a la pasarela: ya no hace falta abrir antes un enlace de verificación en el correo (pagar ya confirma a la persona).',
          },
          {
            titulo: 'La ficha de un evento con talleres ya no falla',
            descripcion:
              'Un evento con sesiones de tipo «Taller» daba error al abrir su ficha pública.',
          },
        ],
      },
    ],
  },
  {
    version: '0.27.18',
    fecha: '2026-10-20',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Asignar sesión desde la pantalla de ponentes',
            descripcion:
              'Cada ponente tiene «Asignar a sesión»: eliges una sesión de la agenda y el rol sin cambiar de pantalla, y se avisa si ya tiene otra a la misma hora.',
          },
          {
            titulo: 'Mover la agenda al cambiar las fechas del evento',
            descripcion:
              'Si cambias las fechas de un evento y alguna sesión quedaría fuera, el panel lo dice y ofrece moverlas todas con el evento (aplazar una semana mueve la agenda entera).',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Ponentes: sus sesiones y su biografía a la vista',
            descripcion:
              'La tabla de ponentes lista todas las sesiones de cada persona; «Asignar sesión» solo aparece si no tiene ninguna, y «Pedir bio» pasa a «Ver bio» en cuanto la ha escrito.',
          },
          {
            titulo: 'Editar una sesión, debajo de la sesión',
            descripcion:
              'En la agenda, «Editar» abre el formulario justo debajo de la sesión, igual que los participantes, en vez de al final de la página.',
          },
          {
            titulo: 'Sesiones dentro de las fechas del evento',
            descripcion:
              'El calendario de una sesión solo deja elegir días y horas del evento, y avisa en el momento si el fin va antes que el inicio.',
          },
          {
            titulo: 'Rol de cada participante en un desplegable',
            descripcion:
              'En «Gestionar participantes» el rol se elige de una lista (ponente, moderación, presentación) y se avisa de quien ya está en otra sesión a la misma hora.',
          },
        ],
      },
    ],
  },
  {
    version: '0.27.11',
    fecha: '2026-10-20',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Vista previa de los eventos, también en borrador',
            descripcion:
              'Desde el listado de eventos, «Vista previa» abre la ficha tal y como la verá el público, aunque el evento aún no esté publicado. Solo la ve el equipo y no aparece en buscadores.',
          },
          {
            titulo: 'Modo, precio y aforo en el listado de eventos',
            descripcion:
              'La tabla de eventos del panel muestra si la inscripción es de acceso libre, con aprobación o de pago, cuánto cuesta (o «Desde» si hay varios precios) y el aforo.',
          },
          {
            titulo: 'Aviso al organizador por cada inscripción',
            descripcion:
              'Quien gestiona las inscripciones recibe un correo con cada inscripción nueva (confirmada, en lista de espera, pendiente de aprobación o pagada), con enlace a su ficha en el panel. Si nadie del equipo puede recibirlo, va al correo de contacto de la organización.',
          },
          {
            titulo: 'Correo de «pendiente de aprobación» al participante',
            descripcion:
              'En los eventos con aprobación, quien se inscribe recibe un correo que le confirma que su solicitud está pendiente, y otro cuando se acepta o se rechaza.',
          },
          {
            titulo: 'Ficha de ponente editable',
            descripcion:
              'El ponente completa su biografía y el resto de su ficha desde «Mi cuenta», adonde lleva el correo que se la pide. El organizador también puede completarla desde Miembros.',
          },
          {
            titulo: 'Ponentes enlazados en la ficha pública del evento',
            descripcion:
              'Enlazar un ponente al evento basta para que salga en la sección de ponentes, aunque aún no tenga sesión en la agenda. Sin perfil público sale con su nombre y sin enlace.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Formulario del evento completo',
            descripcion:
              'Se pueden poner el resumen, la descripción (con editor de texto enriquecido), el modo de inscripción con sus precios y el aforo. El identificador se genera desde el título, las etiquetas se escriben como píldoras con sugerencias (hasta 10) y la fecha y la hora se piden por separado.',
          },
          {
            titulo: 'Desplegables y avisos modernos en toda la aplicación',
            descripcion:
              'Fuera los desplegables nativos y las ventanas del navegador: todo usa los desplegables y los diálogos de la propia aplicación.',
          },
          {
            titulo: 'El panel solo muestra lo que cada rol puede usar',
            descripcion:
              'El menú y las pantallas del panel se ajustan a los permisos de cada persona: un ponente solo ve su cuenta y su ficha.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Sin aviso doble al pagar desde la lista de espera',
            descripcion:
              'Quien paga su entrada tras salir de la lista de espera o tras ser aprobado ya no genera un segundo aviso al organizador.',
          },
          {
            titulo: 'Las cuentas dadas de baja dejan de anunciarse',
            descripcion:
              'Un ponente con la cuenta dada de baja ya no sale en la ficha del evento, ni en la agenda, ni conserva su perfil público.',
          },
          {
            titulo: 'Enlaces internos en los textos legales',
            descripcion:
              'Los textos legales y las políticas pueden enlazar a otras páginas del sitio (por ejemplo «/legal/cookies») o a un apartado del propio texto.',
          },
        ],
      },
    ],
  },
  {
    version: '0.27.0',
    fecha: '2026-10-02',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Vídeo de lanzamiento promocional',
            descripcion:
              'Vídeo promocional del lanzamiento con voz propia, subtítulos y versión vertical de 30 segundos, listo para compartir.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Importes con separador de miles en todo el panel',
            descripcion:
              'Todas las cifras monetarias del panel (contabilidad, pagos, KPIs…) se leen ahora en formato español con separador de miles y coma decimal («21.470,00» en vez de «21470.00»).',
          },
          {
            titulo: 'El KPI «Ejecutado total» no miente con un 0 %',
            descripcion:
              'Con un presupuesto enorme y un gasto aún pequeño, el descriptor del KPI decía «0 % del presupuesto» por el redondeo. Ahora dice «menos de 1 % del presupuesto».',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Las cifras grandes y los textos largos ya no desbordan el panel',
            descripcion:
              'Una cifra enorme (o un correo, un estado o un importe largo) podía ensanchar KPIs, el presupuesto, la contingencia, la previsión, los pagos, las inscripciones, las sedes, la agenda y la lista pública de eventos, haciendo que la página entera se saliera de la pantalla en móvil. Ahora el número o el texto se parte dentro de su propia caja y la página mantiene siempre su ancho.',
          },
        ],
      },
    ],
  },
  {
    version: '0.26.1',
    fecha: '2026-10-01',
    secciones: [
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Todos los correos llevan la plantilla de la plataforma',
            descripcion:
              'Cada correo del sistema (invitaciones, verificación, recuperación, inscripciones, pago…) se envía ahora con una plantilla con la cabecera de la plataforma (el logotipo configurado en la identidad, con un acento en el color de marca), un botón de acción destacado con el enlace principal, y un pie con los enlaces a las páginas legales (aviso legal, privacidad y cookies). El texto plano alternativo conserva el cuerpo y añade el pie.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Los diálogos cerrados no se pintan en el flujo de la página',
            descripcion:
              'Los diálogos cerrados (como los del selector de imágenes) se seguían pintando dentro de la página, flotando encima del formulario y pisando su contenido. Ahora solo se dibujan cuando están abiertos.',
          },
        ],
      },
    ],
  },
  {
    version: '0.26.0',
    fecha: '2026-09-30',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Menú de cuenta en la cabecera de la web pública',
            descripcion:
              'La cabecera de la web pública ya no dice "Iniciar sesión" cuando hay sesión viva: muestra la cuenta (nombre, «Mi cuenta», «Cerrar sesión») o las opciones de invitado según el estado real, renovando la sesión al cargar. «Cerrar sesión» vuelve a la interfaz de invitado sin navegar.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'El correo saliente lleva una versión HTML con enlaces de verdad',
            descripcion:
              'Cada correo del sistema va ahora con una alternativa HTML además del texto plano: las direcciones web son enlaces de verdad que se pueden pulsar. Antes, los clientes de correo móvil partían las direcciones largas al envolver la línea y el enlace no funcionaba; por eso las invitaciones a ponentes llegaban rotas.',
          },
          {
            titulo: 'Los diálogos del panel caben en una vista pequeña',
            descripcion:
              'Los diálogos más altos que la pantalla (como el alta de ponente en el móvil) quedaban cortados con sus botones inalcanzables. Ahora se ajustan a la altura disponible, el contenido se desplaza por sí solo y los botones de acción quedan siempre a la vista.',
          },
          {
            titulo: 'El menú de navegación del panel se repliega al elegir',
            descripcion:
              'En pantallas estrechas, el menú del panel ya no se queda abierto encima de la página elegida: se repliega al pulsar cualquier enlace de navegación, incluso si vuelves a la página en la que ya estabas.',
          },
        ],
      },
    ],
  },
  {
    version: '0.25.1',
    fecha: '2026-09-30',
    secciones: [
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Las direcciones /{organización}/{evento} llevaban a la portada',
            descripcion:
              'En la versión 0.25.0 todas las direcciones de evento y de página de organización redirigían a la portada por un fallo al servir los enlaces antiguos. Ahora abren el evento o la página de la organización, y los enlaces antiguos (/eventos/{evento}) siguen llevando a la portada.',
          },
        ],
      },
    ],
  },
  {
    version: '0.25.0',
    fecha: '2026-09-30',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Categorías y etiquetas de los eventos',
            descripcion:
              'Cada evento puede llevar una categoría (de una lista única para toda la plataforma) y hasta 5 etiquetas. Se ven en la tarjeta y en la ficha del evento, y el directorio /eventos permite filtrar por categoría y por etiqueta. La lista de categorías se gestiona desde «Categorías» en el panel de plataforma; una categoría en uso no se borra, se desactiva.',
          },
          {
            titulo: 'Eliminar un evento cancelado',
            descripcion:
              'Un evento cancelado, cuando ya ha terminado el reembolso de sus inscripciones, se puede eliminar desde su panel. Un evento activo nunca se elimina: primero se cancela. Las inscripciones, los cobros y la contabilidad se conservan.',
          },
          {
            titulo: 'Asistentes (MCP) con categoría y etiquetas',
            descripcion:
              'Los asistentes conectados por MCP pueden asignar categoría y etiquetas al crear o editar un evento, consultar las categorías disponibles y filtrar el listado por categoría y etiquetas.',
          },
        ],
      },
    ],
  },
  {
    version: '0.24.0',
    fecha: '2026-09-30',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'La organización, en la dirección del evento',
            descripcion:
              'Los eventos pasan a vivir en /{organización}/{evento}, y la ficha, el programa, las sesiones, los patrocinadores, las políticas y la inscripción muestran una miga «Inicio › Organización › Evento». Los enlaces antiguos (/eventos/{evento}) eran de prueba y ya no funcionan: llevan a la portada. El identificador de un evento solo tiene que ser único dentro de su organización.',
          },
          {
            titulo: 'Página pública de la organización',
            descripcion:
              'Cada organización puede publicar su propia página en /{organización}, con su logotipo, descripción, web, dirección, redes y sus eventos próximos y pasados. Está desactivada por defecto: se activa en «Organización», donde se ve la lista exacta de datos que se harán públicos (la razón social y el correo de contacto nunca se publican). Los eventos cancelados siguen apareciendo en ella, marcados como cancelados. Sin la página, los eventos siguen siendo públicos y la organización aparece en la miga como texto.',
          },
          {
            titulo: 'Dirección de la organización',
            descripcion:
              'La organización puede indicar una dirección postal, que solo se hace pública si activa su página.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Identificadores reservados',
            descripcion:
              'Al crear una organización ya no se pueden usar nombres que coincidan con secciones de la plataforma (eventos, legal, admin…), porque el identificador de la organización es ahora el primer tramo de la dirección.',
          },
          {
            titulo: 'Sitio web con http:// o https://',
            descripcion:
              'El sitio web de la organización debe empezar por http:// o https://. Los que estaban guardados sin ello se corrigen solos al instalar esta versión.',
          },
          {
            titulo: 'Directorio de eventos con la organización',
            descripcion:
              'Cada evento del directorio muestra el nombre de la organización que lo publica, y «Mis eventos» enlaza a la dirección nueva.',
          },
        ],
      },
    ],
  },
  {
    version: '0.23.4',
    fecha: '2026-09-29',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Añadir el evento al calendario',
            descripcion:
              'Cuando una plaza queda confirmada (al verificar el correo, al aprobarla el organizador, al confirmar desde la lista de espera o al pagar), la persona puede guardar el evento en Google Calendar, Outlook o Apple Calendar. Mientras la plaza esté pendiente de aprobación, de pago o en lista de espera, o si el evento se cancela, no se le propone.',
          },
          {
            titulo: 'Zona horaria con buscador',
            descripcion:
              'Al editar un evento, la zona horaria se elige escribiendo: la lista se filtra mientras tecleas (sin importar tildes ni mayúsculas) en lugar de obligar a recorrer cientos de opciones.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Selector de fecha y hora del evento',
            descripcion:
              'La fecha se elige en un calendario y la hora se puede escribir directamente (9, 935 o 9:35) o ajustar con las flechas del teclado y con saltos de una hora o cinco minutos.',
          },
          {
            titulo: 'Formulario de edición del evento más despejado',
            descripcion:
              'Inicio, fin y ciudad quedan en una misma fila, con modalidad y zona horaria debajo, y el formulario es más ancho para que ningún campo se pise con otro.',
          },
        ],
      },
    ],
  },
  {
    version: '0.23.3',
    fecha: '2026-09-28',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Aviso de cuenta sin verificar',
            descripcion:
              'Quien entra al panel sin haber verificado su correo ve un aviso que le explica que su cuenta está limitada, con un botón para que le reenviemos el enlace sin volver a escribir su correo.',
          },
          {
            titulo: 'Verificar o reenviar la verificación desde Usuarios',
            descripcion:
              'El listado de usuarios muestra si cada cuenta tiene el correo verificado. En las que no, el superadmin puede verificarlo a mano o reenviar el correo de verificación desde la propia fila. Ambas acciones quedan en la auditoría.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Solo vale el último enlace de verificación',
            descripcion:
              'Cada vez que se envía un enlace de verificación nuevo, los anteriores dejan de funcionar. Los reenvíos que pide la propia persona también quedan registrados en la auditoría.',
          },
        ],
      },
    ],
  },
  {
    version: '0.23.2',
    fecha: '2026-09-26',
    secciones: [
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Vuelve el apilado de la portada en móvil',
            descripcion:
              'Las tarjetas de funcionalidades de la portada vuelven a apilarse al hacer scroll también en móvil y tablet (en la 0.23.1 se habían quitado por error). Ahora cada tarjeta cabe entera bajo la cabecera, sea cual sea el alto de la pantalla.',
          },
        ],
      },
    ],
  },
  {
    version: '0.23.1',
    fecha: '2026-09-25',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Proveedor de correo configurable',
            descripcion:
              'Nueva pantalla «Correo» en el panel de la plataforma para elegir con qué servicio salen los correos (Resend, Acumbamail, Amazon SES o SMTP personalizado). La clave se guarda cifrada y nunca se vuelve a mostrar, y un correo de prueba a tu propia dirección confirma que funciona antes de guardar.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Los correos de verificación no llegaban',
            descripcion:
              'Con el puerto 587 el envío intentaba cifrar la conexión de la forma equivocada y el servidor la rechazaba, así que no salía ningún correo. Sin la verificación, quien se registraba veía «No se pudieron cargar los datos de tu organización». Ahora el cifrado se elige según el puerto.',
          },
          {
            titulo: 'Vistas en móvil',
            descripcion:
              'En Android la web pública se veía alejada y descuadrada porque la cabecera y el pie eran más anchos que la pantalla. Las funcionalidades de la portada ya no se apilan en móvil, y el panel del organizador tiene una cabecera compacta, pestañas del evento deslizables y tablas y filtros que se desplazan dentro de su caja.',
          },
        ],
      },
    ],
  },
  {
    version: '0.23.0',
    fecha: '2026-09-24',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Conectar Hermes por MCP',
            descripcion:
              'La pantalla «Asistentes (MCP)» explica cómo conectar Hermes Agent: el bloque de configuración para ~/.hermes/config.yaml con la URL de la instalación, un botón para copiarlo entero y la alternativa por inicio de sesión (auth: oauth). Lo que Hermes puede hacer —crear y editar eventos, publicar, cancelar…— depende de los ámbitos y eventos elegidos al crear la clave de API.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Tokens MCP filtrados',
            descripcion:
              'Si alguien presenta un token de renovación ya usado desde otro asistente, la conexión se revoca entera, igual que cuando lo presenta el mismo asistente.',
          },
        ],
      },
    ],
  },
  {
    version: '0.22.0',
    fecha: '2026-09-24',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Asistentes conectados por MCP',
            descripcion:
              'Claude, ChatGPT, Cursor o cualquier cliente MCP pueden conectarse a Eventarium en eventarium.org/mcp, iniciando sesión o con una clave de API de 90 días. Cada persona elige qué puede hacer la conexión (leer, editar, publicar, patrocinadores, cifras de inscripción, cancelar) y sobre qué eventos. Lo que crea el asistente queda en borrador, nunca ve datos personales de los asistentes y todo lo que hace queda en la auditoría.',
          },
          {
            titulo: 'Permiso «Conectar asistentes por MCP»',
            descripcion:
              'Solo el dueño de la organización lo tiene de entrada y decide a qué roles se lo da. Cada persona gestiona sus conexiones en «Asistentes (MCP)» y el dueño ve y revoca las de todos los miembros.',
          },
          {
            titulo: 'Eventos cancelados',
            descripcion:
              'Cancelar un evento es definitivo: se reembolsa íntegramente a quien pagó, se avisa a los inscritos, la página pública sigue visible con un aviso y el evento desaparece de los listados.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Títulos en todas las páginas',
            descripcion:
              'La inscripción, la entrada, el pago y el resto de páginas que se quedaban sin título lo tienen ya, y una respuesta tardía no pisa el título de la página siguiente.',
          },
          {
            titulo: 'Enlaces de un solo uso fuera de los buscadores',
            descripcion:
              'Las páginas a las que se llega con un enlace personal (confirmar, gestionar la inscripción) se generan en el servidor y piden a los buscadores que no las indexen.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.14',
    fecha: '2026-09-23',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Imagen para compartir en redes',
            descripcion:
              'Las páginas públicas sin imagen propia (la portada de la plataforma, el listado, las sesiones o un evento sin portada) se comparten ahora con una tarjeta de Eventarium, en lugar de aparecer sin vista previa. Los eventos con portada siguen usando la suya.',
          },
          {
            titulo: 'Compartir un evento',
            descripcion:
              'Debajo de la descripción del evento hay botones para compartirlo en X, LinkedIn, Facebook, WhatsApp, Telegram y Bluesky, enviarlo por correo o copiar el enlace. No cargan nada de las redes hasta que se pulsan.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Las páginas de un evento conservan su diseño',
            descripcion:
              'La inscripción, el programa, las sesiones, los patrocinadores y las políticas de un evento se ven con la plantilla del evento, igual que su ficha, y ya no parpadea al pasar de una a otra.',
          },
          {
            titulo: 'Mapas en producción',
            descripcion:
              'El mapa del lugar en la ficha del evento y el del editor de direcciones no llegaban a pintarse en la versión publicada.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.13',
    fecha: '2026-09-15',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Selector de organizaciones accesible',
            descripcion:
              'Quien pertenece a varias organizaciones puede cambiar de activa desde un menú de teclado en la cabecera del panel, en vez de tener que volver a iniciar sesión.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Cierre del pase visual del panel',
            descripcion:
              'Todas las pantallas de organización y de plataforma comparten ya los mismos patrones de página del prototipo, con las baterías de test y el build de producción en verde. La comprobación manual de accesibilidad y de los distintos anchos de pantalla queda documentada como recorrido pendiente.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.11',
    fecha: '2026-09-15',
    secciones: [
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Cabecera de página unificada',
            descripcion:
              'Todas las pantallas del panel pasan a compartir la misma cabecera (rótulo, título y acción principal), sustituyendo las variantes sueltas que había ido acumulando cada pantalla.',
          },
        ],
      },
    ],
  },
  ...CHANGELOG_ANTERIOR,
];
