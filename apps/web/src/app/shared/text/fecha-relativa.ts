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

export function fechaRelativa(iso: string, ahora: Date = new Date()): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) {
    return '';
  }
  const delta = ahora.getTime() - fecha.getTime();
  if (delta < MINUTO) {
    return 'ahora';
  }
  if (delta < HORA) {
    return `hace ${Math.floor(delta / MINUTO)} min`;
  }
  if (delta < DIA) {
    return `hace ${Math.floor(delta / HORA)} h`;
  }
  if (delta < MES) {
    return `hace ${Math.floor(delta / DIA)} d`;
  }
  if (delta < ANIO) {
    const meses = Math.floor(delta / MES);
    return meses === 1 ? 'hace 1 mes' : `hace ${meses} meses`;
  }
  const anios = Math.floor(delta / ANIO);
  return anios === 1 ? 'hace 1 año' : `hace ${anios} años`;
}
