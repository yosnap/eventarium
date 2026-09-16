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
  {
    version: '0.21.10',
    fecha: '2026-09-15',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Ponentes del evento',
            descripcion:
              'Nueva pantalla con la ficha de cada ponente del evento, sus sesiones asignadas y sus datos de edición, siguiendo el mismo lenguaje visual que el resto del panel.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.9',
    fecha: '2026-09-15',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Contabilidad con KPIs y rieles de presupuesto',
            descripcion:
              'El libro de contabilidad del evento se rediseña con KPIs, un riel visual que compara presupuesto frente a lo ejecutado por partida, el desglose del fondo de contingencia y una previsión de cierre.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'El selector de personas del roster ya carga la organización entera',
            descripcion:
              'El backend limita cada página a 100 elementos y el selector pedía 200 de golpe: la petición no pasaba la validación y el desplegable se quedaba sin opciones. Ahora pagina hasta agotar la organización.',
          },
          {
            titulo: 'Los correos de salida viajan como texto plano',
            descripcion:
              'Los correos enviados desde la plataforma no llevaban una versión en texto plano junto a la versión en HTML, lo que degradaba su entrega y su lectura en clientes de correo que priorizan texto plano.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.7',
    fecha: '2026-09-15',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Inscripciones con embudo y motivo de rechazo',
            descripcion:
              'La pantalla de inscripciones gana KPIs, el embudo completo (formulario → verificado → aprobado → entrada emitida) y la posibilidad de rechazar una solicitud dejando escrito el motivo.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.6',
    fecha: '2026-09-15',
    secciones: [
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Marca, catálogo de componentes y check-in con los patrones nuevos',
            descripcion:
              'Estas tres pantallas pasan a usar los patrones de página compartidos que se acaban de crear, en vez de su propia maquetación suelta.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.5',
    fecha: '2026-09-15',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Patrones de página del prototipo, como componentes reutilizables',
            descripcion:
              'Arranca el pase visual del panel: los bloques recurrentes del prototipo (cabecera de página, panel con cabecera y pie de totales, tarjeta KPI) pasan a ser componentes del sistema compartido en vez de maquetarse suelto en cada pantalla.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.3',
    fecha: '2026-09-14',
    secciones: [
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'La organización deja de tener dominio propio',
            descripcion:
              'Se retira el subdominio por organización (`organization_domains`/`platform_domains`) siguiendo el modelo de directorio global ya adoptado: la home pasa a listar todas las organizaciones y el alta ya no pide un dominio. El listado público de eventos y el consentimiento de cookies dejan de depender de resolver una organización por el host visitado.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.1',
    fecha: '2026-09-14',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'La organización activa vive en la sesión, no en el dominio visitado',
            descripcion:
              'Al no haber ya un subdominio por organización, iniciar sesión valida las credenciales en toda la instalación y elige una organización activa (la única, la de acceso más reciente, o ninguna); un nuevo endpoint permite cambiarla sin volver a iniciar sesión.',
          },
          {
            titulo: 'Las páginas públicas se resuelven por el recurso, no por el dominio',
            descripcion:
              'El detalle de un evento, una sesión, un perfil de ponente o una inscripción encuentran su organización a través del propio recurso pedido (su slug único, o el token de un solo uso que llevan), no adivinándola por el host de la petición.',
          },
          {
            titulo: 'Slugs de evento y de ponente únicos en toda la instalación',
            descripcion:
              'Sin dominio propio por organización, el slug pasa a ser la única forma de encontrar un evento o un perfil público en una URL, así que deja de bastar con que sea único solo dentro de su organización.',
          },
          {
            titulo: 'Una cuenta puede dar de alta más de una organización',
            descripcion:
              'El formulario de alta de organización dejaba de funcionar para una cuenta que ya tenía una: ahora acepta también una sesión normal ya iniciada, no solo el token que se emite justo al verificar el correo por primera vez.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Las páginas legales pasan a ser solo de la plataforma',
            descripcion:
              'Eventarium es una instalación centralizada, no un conjunto de instalaciones independientes por organización: deja de poder editarse un aviso legal, una política de privacidad o unas condiciones de inscripción propios por organización, y las condiciones de inscripción se incorporan al catálogo legal de la plataforma.',
          },
          {
            titulo: 'El catálogo de componentes vuelve a ser cosa de plataforma',
            descripcion:
              'El catálogo interno de componentes visuales, con el que se construyen la landing y las plantillas que luego usan las organizaciones, pasa de estar abierto a cualquier organizador a exigir superadministración, como el resto del panel de plataforma.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: '/acceder avisa si ya hay una sesión activa',
            descripcion:
              'Un intento de inicio de sesión fallido con una cuenta ya no dejaba ver que seguía habiendo otra sesión abierta: ahora, si ya hay sesión, se redirige en vez de mostrar el formulario como si no hubiera nadie.',
          },
          {
            titulo: 'El guard de plataforma vuelve a renovar la sesión antes de rendirse',
            descripcion:
              'Entrar directamente a una URL de plataforma por enlace o tras recargar la página expulsaba a quien tenía sesión válida, porque el guard no intentaba renovarla con la cookie antes de darla por caducada — solo funcionaba si se llegaba navegando primero por el panel de organización.',
          },
          {
            titulo: 'El nombre de la organización activa se toma de la sesión',
            descripcion:
              'La pantalla de marca mostraba el nombre de una organización equivocada cuando la sesión no coincidía con la que se resolvía por el contexto antiguo.',
          },
        ],
      },
    ],
  },
  {
    version: '0.21.0',
    fecha: '2026-09-14',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Invitaciones a organización y a evento, sin necesitar cuenta previa',
            descripcion:
              'Una organización puede invitar por correo a alguien que todavía no tiene cuenta: se le crea una cuenta sin contraseña y una invitación con estado, que acepta desde una pantalla pública propia sin pasar por el mecanismo de recuperar contraseña. Si el correo ya tiene cuenta, se añade directamente, sin esperar a que acepte nada.',
          },
          {
            titulo: 'Invitar ponentes desde el propio evento',
            descripcion:
              'El roster de un evento gana su propio alta por correo: invita directamente con el rol de ponente, y al aceptar la invitación la persona entra a la organización y al roster del evento en el mismo paso.',
          },
          {
            titulo: 'El listado de miembros se agrupa por persona',
            descripcion:
              'Quien tenía dos roles en la organización aparecía dos veces en el listado, como si fueran personas distintas. Ahora es una fila por persona, con sus roles listados como chips que se pueden quitar uno a uno sin sacarla de la organización.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'La portada deja de anunciar «Próximamente» sobre eventos ya publicados',
            descripcion:
              'El hero de la portada repetía tres veces que la plataforma estaba «Próximamente» mientras debajo ya se podía listar e inscribirse a veinte eventos publicados — una contradicción para quien entraba.',
          },
        ],
      },
    ],
  },
  {
    version: '0.20.0',
    fecha: '2026-09-13',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Patrocinadores, con niveles públicos y privados',
            descripcion:
              'Un evento puede tener patrocinadores organizados en niveles (tiers), cada uno con sus propios beneficios y con visibilidad pública o solo interna; el bloque de patrocinadores aparece en la página pública del evento.',
          },
          {
            titulo: 'Páginas legales y consentimiento de cookies',
            descripcion:
              'Aviso legal, política de privacidad y política de cookies editables desde el panel, con un banner de cookies que registra la decisión de cada visitante y permite gestionarla más adelante.',
          },
          {
            titulo: 'Panel de superadministración con auditoría, RGPD y validación de copias de seguridad',
            descripcion:
              'Nace el panel de plataforma: registro diferido de auditoría, exportación RGPD de los datos de inscripción de un evento, borrado de un inscrito bajo solicitud, y un script de restauración de copias de seguridad que valida de verdad la integridad de lo restaurado.',
          },
          {
            titulo: 'Pagos con Stripe Connect',
            descripcion:
              'Cada organización conecta su propia cuenta de Stripe para cobrar sus eventos de pago: tipos de entrada, códigos de descuento, compra pública con confirmación por webhook, reembolsos (automáticos por plazo o manuales) y una pantalla de pagos por evento. Cierra los cuatro caminos que podían confirmar una inscripción de pago sin haber cobrado.',
          },
          {
            titulo: 'Sistema de diseño con tokens de color OKLCH y plantillas de tema',
            descripcion:
              'Los colores de marca dejan de ser dos campos sueltos por organización y pasan a un catálogo de plantillas de tema completas (tipografía, colores claros y oscuros) fieles al prototipo visual de referencia, con tipografías autoalojadas y conmutador de tema claro/oscuro.',
          },
          {
            titulo: 'Contabilidad del evento, con presupuesto y fondo de contingencia',
            descripcion:
              'Libro contable por evento: partidas de presupuesto, ingresos compuestos (patrocinios cobrados, entradas netas de reembolso, subvenciones manuales), gastos con IVA y aportaciones en especie de patrocinador, con un fondo de contingencia calculado automáticamente y exportación a CSV/PDF.',
          },
          {
            titulo: 'Identidad propia de la plataforma, separada de cada organización',
            descripcion:
              'Eventarium pasa a tener su propio nombre, logotipo, favicon y páginas legales de instalación, visibles en el chrome de la web pública, distintos de la identidad de cada organización que aloja.',
          },
          {
            titulo: 'Impersonación de solo lectura',
            descripcion:
              'Quien administra la plataforma puede entrar a la cuenta de una persona para ver lo que ve ella, sin poder modificar nada: la sesión caduca a los 15 minutos, queda registrada en la auditoría, y a la persona suplantada se le avisa por correo del acceso.',
          },
          {
            titulo: 'El escritorio de cada evento, organización y plataforma deja de ser un saludo',
            descripcion:
              'Las tres portadas (evento, organización, plataforma) pasaban de un simple mensaje de bienvenida a mostrar de verdad cómo va lo que administran: el embudo completo de un evento, el negocio de una organización (ordenado primero por lo que pide una decisión) y la salud de la instalación sin ver el negocio de ninguna organización.',
          },
          {
            titulo: 'Cada evento puede tener su propia plantilla visual',
            descripcion:
              'Un evento puede elegir su propio tema, heredando el de su organización si no elige ninguno — así una organización puede llevar a la vez una jornada técnica y una gala benéfica con identidades visuales distintas.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'El panel de organización deja de vivir bajo /admin',
            descripcion:
              'La ruta `/admin` la usaba el organizador para gestionar su propia organización, un nombre que decía lo contrario de lo que hacía. Pasa a `/dashboard`; `/admin` queda para quien administra la plataforma, y `/acceder` para el acceso común a los dos.',
          },
          {
            titulo: 'Los componentes compartidos se reescriben sobre el sistema de diseño nuevo',
            descripcion:
              'Botones, campos, tarjetas, tablas y el resto del catálogo interno pasan a usar los tokens visuales nuevos sin cambiar su forma de uso desde fuera, y ganan tabla accesible (`data-table`) y chip de estado por texto, no solo por color.',
          },
          {
            titulo: 'Las tablas del panel pasan a un componente común',
            descripcion:
              'Las tablas de pagos, miembros, eventos, inscripciones y auditoría, antes cada una a su manera, pasan todas al mismo componente de tabla accesible con desplazamiento alcanzable por teclado.',
          },
          {
            titulo: 'La navegación del panel se agrupa por ámbito',
            descripcion:
              'El menú del panel se reorganiza en tres grupos (organización, evento, plataforma) en vez de una lista plana de enlaces, con cada grupo visible solo para quien tiene permiso de verlo.',
          },
        ],
      },
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'La auditoría de plataforma ya no filtraba importes de las organizaciones',
            descripcion:
              'El registro de auditoría que sirve `/admin/audit-log` guarda el detalle completo de cada acción, incluidos los importes de contabilidad cuando la acción los tocaba, y se estaba devolviendo tal cual: quien administra la plataforma podía ver cifras de negocio de una organización sin que nadie lo hubiera decidido así.',
          },
          {
            titulo: 'Fidelidad visual real contra el prototipo de referencia',
            descripcion:
              'El sistema de diseño de las primeras fases no se parecía al prototipo real: tamaños de radio, sombras y tipografía de los componentes se corrigen uno a uno contra los valores literales del CSS de referencia.',
          },
        ],
      },
    ],
  },
  {
    version: '0.17.1',
    fecha: '2026-09-08',
    secciones: [
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'El check-in por QR volvía a fallar por un parámetro de ruta',
            descripcion:
              'La pantalla de control de acceso esperaba el identificador del evento con otro nombre que el que declaraba su ruta, así que ninguna llamada a la API del check-in (contador, cámara, sincronización, búsqueda) encontraba el evento.',
          },
        ],
      },
    ],
  },
  {
    version: '0.17.0',
    fecha: '2026-09-08',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Entradas con código QR y control de acceso',
            descripcion:
              'Cada inscripción confirmada emite automáticamente una entrada con QR, que se revoca si la inscripción se cancela. El panel gana una aplicación de escaneo instalable con cámara, cola sin conexión que sincroniza sola, búsqueda manual y contador en vivo; el correo de confirmación lleva el QR incrustado y hay una página pública para consultar la propia entrada.',
          },
        ],
      },
    ],
  },
  {
    version: '0.16.0',
    fecha: '2026-09-08',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Correos de inscripción y autocancelación',
            descripcion:
              'Cada paso del embudo de inscripción (confirmación, rechazo, entrada en lista de espera, promoción, cancelación) envía su propio correo con plantilla, y quien se inscribe puede cancelar su propia plaza desde un enlace de un solo uso.',
          },
        ],
      },
    ],
  },
  {
    version: '0.15.0',
    fecha: '2026-09-08',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Aprobación de inscripciones y lista de espera automática',
            descripcion:
              'El organizador puede aprobar, rechazar o cancelar una inscripción; al liberarse una plaza, la lista de espera promociona sola con un plazo para confirmar antes de pasar a la siguiente persona.',
          },
        ],
      },
    ],
  },
  {
    version: '0.14.0',
    fecha: '2026-09-08',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Formulario público de inscripción, con verificación por correo',
            descripcion:
              'Quien quiere inscribirse a un evento rellena un formulario con preguntas propias del evento y consentimientos, verifica su correo con un token de un solo uso, y la plaza se evalúa contra el aforo del evento en el mismo momento.',
          },
        ],
      },
    ],
  },
  {
    version: '0.13.0',
    fecha: '2026-09-08',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Modelo de inscripciones a eventos',
            descripcion:
              'Base de datos y permisos para que un evento tenga preguntas propias de inscripción, y para que las respuestas y los consentimientos de cada inscrito queden guardados de forma aislada por organización.',
          },
        ],
      },
    ],
  },
  {
    version: '0.12.0',
    fecha: '2026-09-08',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Alta de organización con verificación de correo',
            descripcion:
              'El registro pasa a pedir solo correo y contraseña; nombre, apellidos y organización se piden después, en el momento en que de verdad hacen falta. Una cuenta sin verificar en una semana se elimina sola.',
          },
          {
            titulo: 'Panel de organización editable, con marca propia',
            descripcion:
              'Nombre, razón social, descripción y datos de contacto de la organización pasan a poder editarse desde el panel, igual que el logotipo, los colores y las tipografías de su marca.',
          },
          {
            titulo: 'Roles a medida y gestión de miembros',
            descripcion:
              'Una organización puede crear roles propios además de los del sistema, con sus propios permisos y campos de perfil, y gestionar de alta y de baja a las personas de su equipo.',
          },
          {
            titulo: 'Cuenta propia: cambio de correo, contraseña y sesiones abiertas',
            descripcion:
              'Cualquier persona puede cambiar su correo (con aviso a la dirección antigua) o su contraseña, recuperarla si la olvida, y cerrar el resto de sus sesiones abiertas sin afectar a la actual.',
          },
          {
            titulo: 'Modelo de eventos, agenda y ponentes',
            descripcion:
              'Un evento puede tener sesiones organizadas por día y un roster de ponentes asignados a cada una, con perfil público propio para cada ponente.',
          },
          {
            titulo: 'Página pública del evento, con servidor',
            descripcion:
              'El listado y el detalle de un evento, su agenda y el perfil de cada ponente pasan a tener página pública propia, renderizada en servidor para que se indexe y comparta bien.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Política de contraseña con validación en vivo',
            descripcion:
              'El registro exige ya mayúscula, minúscula, número y símbolo, con un indicador que va marcando en el propio formulario qué requisito falta, no solo al enviarlo.',
          },
        ],
      },
    ],
  },
  {
    version: '0.7.0',
    fecha: '2026-09-07',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Registro con verificación de correo y protección Turnstile',
            descripcion:
              'Primer alta pública de cuenta: correo, contraseña, verificación por token de un solo uso y protección contra registros automatizados.',
          },
        ],
      },
      {
        categoria: 'modificado',
        items: [
          {
            titulo: 'Despliegue de producción con EasyPanel',
            descripcion:
              'El proxy inverso y el TLS de producción pasan a resolverlos EasyPanel en vez de un Caddy propio, que queda solo como herramienta de desarrollo; se documenta el modelo de un subdominio por organización.',
          },
        ],
      },
    ],
  },
  {
    version: '0.5.2',
    fecha: '2026-09-07',
    secciones: [
      {
        categoria: 'corregido',
        items: [
          {
            titulo: 'Renderizado en servidor reparado en desarrollo',
            descripcion:
              'Cuatro fallos que solo se veían leyendo el registro del proceso — Angular degradaba a renderizado en cliente en silencio — dejaban el servidor de desarrollo sirviendo la URL de producción y sin traducciones ni worker de tareas en marcha.',
          },
          {
            titulo: 'Integración continua estabilizada',
            descripcion:
              'El almacenamiento de objetos de las pruebas no era alcanzable desde el runner, y faltaba el permiso necesario para que el escáner de secretos analizara pull requests.',
          },
        ],
      },
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Arranque de la aplicación con un solo comando',
            descripcion:
              'Un único script levanta el entorno completo, junto o por partes, para no tener que recordar el orden de los servicios.',
          },
        ],
      },
    ],
  },
  {
    version: '0.5.0',
    fecha: '2026-09-07',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Integración continua y despliegue de producción',
            descripcion:
              'La API se prueba contra base de datos, caché y almacenamiento reales; el frontend comprueba que sus tipos generados no se han quedado atrás; y un tercer job busca secretos filtrados en el historial. El despliegue de producción migra la base de datos una sola vez antes de arrancar las réplicas.',
          },
        ],
      },
    ],
  },
  {
    version: '0.4.0',
    fecha: '2026-09-07',
    secciones: [
      {
        categoria: 'agregado',
        items: [
          {
            titulo: 'Arranque del proyecto: monorepo y entorno de desarrollo',
            descripcion:
              'Estructura del monorepo con PostgreSQL, almacenamiento de objetos compatible con S3, caché y proxy, levantable con un solo comando.',
          },
          {
            titulo: 'Base de la API con autenticación y multi-tenant real',
            descripcion:
              'La API resuelve cada organización por su dominio antes de tocar cualquier tabla, con aislamiento entre organizaciones garantizado por políticas de seguridad a nivel de fila: sin contexto de organización fijado, ninguna consulta devuelve una fila, ni de la organización equivocada ni de ninguna otra.',
          },
          {
            titulo: 'Aplicación Angular con marca por organización',
            descripcion:
              'Una sola aplicación sirve la web pública con servidor (porque el contenido depende del dominio visitado) y el panel de administración; los colores de marca de cada organización cambian la interfaz sin necesidad de recompilar nada.',
          },
        ],
      },
    ],
  },
];
