/** Precio en céntimos + código de moneda ISO 4217 (`price_from_cents`/
 * `price_currency` de `PublicEventSummary`/`PublicEventDetail`) a texto
 * localizado en `idioma`, p.ej. `1250` + `"eur"` + `'es-ES'` → `"12,50 €"`. */
export function formatearPrecio(cents: number, currency: string, idioma: string): string {
  return new Intl.NumberFormat(idioma, { style: 'currency', currency }).format(cents / 100);
}
