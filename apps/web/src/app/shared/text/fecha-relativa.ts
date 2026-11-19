/**
 * Fecha relativa en español («hace 2 h», «hace 3 d»), como la columna
 * «Solicitada» del prototipo (`panel-organizador.html`).
 *
 * Sin `Intl.RelativeTimeFormat` a secas: su salida («hace 2 horas») es más
 * larga de lo que una celda de tabla aguanta, y el proyecto no tiene
 * infraestructura de pluralización que reutilizar. Este formato corto es el
 * que pinta la referencia.
 */

const MINUTO = 60_000;
const HORA = 60 * MINUTO;
const DIA = 24 * HORA;
const MES = 30 * DIA;
const ANIO = 12 * MES;

export function fechaRelativa(iso: string, idioma: string, ahora: Date = new Date()): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) {
    return '';
  }
  const delta = ahora.getTime() - fecha.getTime();
  if (delta < MINUTO) {
    return new Intl.RelativeTimeFormat(idioma, { numeric: 'auto' }).format(0, 'second');
  }
  const corto = new Intl.RelativeTimeFormat(idioma, { style: 'short', numeric: 'always' });
  const largo = new Intl.RelativeTimeFormat(idioma, { numeric: 'always' });
  if (delta < HORA) {
    return corto.format(-Math.floor(delta / MINUTO), 'minute');
  }
  if (delta < DIA) {
    return corto.format(-Math.floor(delta / HORA), 'hour');
  }
  if (delta < MES) {
    return largo.format(-Math.floor(delta / DIA), 'day');
  }
  if (delta < ANIO) {
    return largo.format(-Math.floor(delta / MES), 'month');
  }
  return largo.format(-Math.floor(delta / ANIO), 'year');
}
