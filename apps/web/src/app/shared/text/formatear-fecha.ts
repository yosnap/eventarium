/**
 * Fecha formateada en el idioma de la visita y, si se indica, en la zona horaria
 * del evento (no en la del navegador). `DatePipe` no acepta nombres IANA como
 * `Europe/Madrid` y caería en silencio a la hora local; por eso se usa `Intl`.
 * Con una zona que el navegador no conozca, se formatea en la hora local antes
 * que fallar.
 */
export function formatearFecha(
  valor: string | Date,
  idioma: string,
  opciones: Intl.DateTimeFormatOptions,
): string {
  const fecha = typeof valor === 'string' ? new Date(valor) : valor;
  try {
    return new Intl.DateTimeFormat(idioma, opciones).format(fecha);
  } catch {
    return new Intl.DateTimeFormat(idioma, { ...opciones, timeZone: undefined }).format(fecha);
  }
}
