/**
 * Enlaces y archivo `.ics` para añadir un evento al calendario de quien se ha
 * inscrito. Funciones puras, sin DOM: el componente `AddToCalendar` solo decide
 * qué botón pinta y cuándo descargar.
 *
 * Todas las horas van en UTC (`...Z`). Así ninguno de los tres destinos
 * necesita declarar la zona horaria del evento (un `.ics` con hora local
 * exigiría un bloque `VTIMEZONE` completo), y cada calendario muestra la cita
 * en la zona de quien la abre — que es lo que se espera de un evento presencial
 * o en línea al que asiste alguien de fuera.
 */

/** Los datos del evento que necesita cualquier destino de calendario. */
export interface EventoParaCalendario {
  readonly slug: string;
  readonly title: string;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly timezone: string;
  readonly location: string | null;
}

/** `2026-10-01T07:00:00.000Z` → `20261001T070000Z` (formato básico de iCalendar). */
function formatoBasicoUtc(fecha: Date): string {
  return fecha
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d{3}Z$/, 'Z');
}

/** `2026-10-01T07:00:00.000Z` → `2026-10-01T07:00:00Z` (ISO sin milisegundos, para Outlook). */
function isoSinMilisegundos(fecha: Date): string {
  return fecha.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

export function urlGoogleCalendar(evento: EventoParaCalendario, urlEvento: string): string {
  const inicio = formatoBasicoUtc(new Date(evento.starts_at));
  const fin = formatoBasicoUtc(new Date(evento.ends_at));
  const partes = [
    'action=TEMPLATE',
    `text=${encodeURIComponent(evento.title)}`,
    // La barra separa inicio y fin; codificada, Google no reconoce el rango.
    `dates=${inicio}/${fin}`,
    `details=${encodeURIComponent(urlEvento)}`,
  ];
  if (evento.location) partes.push(`location=${encodeURIComponent(evento.location)}`);
  return `https://calendar.google.com/calendar/render?${partes.join('&')}`;
}

export function urlOutlook(evento: EventoParaCalendario, urlEvento: string): string {
  const parametros = new URLSearchParams({
    path: '/calendar/action/compose',
    rru: 'addevent',
    subject: evento.title,
    startdt: isoSinMilisegundos(new Date(evento.starts_at)),
    enddt: isoSinMilisegundos(new Date(evento.ends_at)),
    body: urlEvento,
  });
  if (evento.location) parametros.set('location', evento.location);
  return `https://outlook.live.com/calendar/0/deeplink/compose?${parametros.toString()}`;
}

/** Escapa un valor de texto de iCalendar (RFC 5545 §3.3.11). */
function escaparTexto(texto: string): string {
  return texto
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r?\n/g, '\\n');
}

/**
 * Pliega una línea a un máximo de 75 octetos (RFC 5545 §3.1): el resto continúa
 * en líneas que empiezan por un espacio. Se cuenta en bytes UTF-8, no en
 * caracteres — un título con tildes o emoji supera antes el límite — y nunca se
 * parte un carácter por la mitad.
 */
function plegarLinea(linea: string): string {
  const codificador = new TextEncoder();
  const lineas: string[] = [];
  let actual = '';
  let octetos = 0;
  let limite = 75;
  for (const caracter of linea) {
    const tamano = codificador.encode(caracter).length;
    if (octetos + tamano > limite) {
      lineas.push(actual);
      actual = '';
      octetos = 0;
      limite = 74; // el espacio inicial de continuación ocupa un octeto
    }
    actual += caracter;
    octetos += tamano;
  }
  lineas.push(actual);
  return lineas.join('\r\n ');
}

/**
 * Contenido de un `.ics` con un único evento. `ahora` solo existe para que los
 * tests fijen la marca de creación (`DTSTAMP`).
 */
export function contenidoIcs(
  evento: EventoParaCalendario,
  urlEvento: string,
  ahora: Date = new Date(),
): string {
  const lineas = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Eventarium//Eventarium//ES',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    // UID estable por evento: volver a añadirlo actualiza la cita en vez de duplicarla.
    `UID:${evento.slug}@eventarium`,
    `DTSTAMP:${formatoBasicoUtc(ahora)}`,
    `DTSTART:${formatoBasicoUtc(new Date(evento.starts_at))}`,
    `DTEND:${formatoBasicoUtc(new Date(evento.ends_at))}`,
    `SUMMARY:${escaparTexto(evento.title)}`,
    ...(evento.location ? [`LOCATION:${escaparTexto(evento.location)}`] : []),
    `URL:${urlEvento}`,
    `DESCRIPTION:${escaparTexto(urlEvento)}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ];
  return lineas.map(plegarLinea).join('\r\n') + '\r\n';
}

export function nombreFicheroIcs(evento: EventoParaCalendario): string {
  return `${evento.slug}.ics`;
}
