/** Precio en céntimos + código de moneda ISO 4217 (`price_from_cents`/
 * `price_currency` de `PublicEventSummary`/`PublicEventDetail`) a texto
 * localizado, p.ej. `1250` + `"eur"` → `"12,50 €"`. */
export function formatearPrecio(cents: number, currency: string): string {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency }).format(cents / 100);
}
