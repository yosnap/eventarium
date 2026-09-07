/**
 * Convierte un ISO en UTC (lo que devuelve la API) al valor que espera un
 * `<input type="datetime-local">`: hora **local** del navegador, sin sufijo de
 * zona. Usar `.slice(0, 16)` directamente sobre el ISO dejaría el campo en
 * UTC en vez de en la hora local, desincronizado del valor que se envió al
 * guardar (que sí se convierte de local a UTC).
 */
export function isoAValorLocal(iso: string): string {
  const fecha = new Date(iso);
  const desplazamiento = fecha.getTimezoneOffset() * 60_000;
  return new Date(fecha.getTime() - desplazamiento).toISOString().slice(0, 16);
}
