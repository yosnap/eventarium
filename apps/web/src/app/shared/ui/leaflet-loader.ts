import type * as Leaflet from 'leaflet';

/**
 * Import dinámico de `leaflet` con la interoperabilidad CommonJS resuelta.
 * Leaflet no es ESM: en la build de producción esbuild envuelve el módulo y
 * solo expone `default`, mientras que `ng serve` y Vitest dan también los
 * nombres sueltos. Usar el namespace a pelo funcionaba en desarrollo y dejaba
 * `L.map` sin definir en producción, sin mapa.
 */
export async function cargarLeaflet(): Promise<typeof Leaflet> {
  const modulo = await import('leaflet');
  // `in` antes de leer: los mocks de Vitest lanzan si se accede a un `default`
  // que no declaran.
  return 'default' in modulo && modulo.default ? (modulo.default as typeof Leaflet) : modulo;
}
