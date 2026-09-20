import type * as Leaflet from 'leaflet';

/**
 * Marcador de mapa como `L.divIcon` (HTML/CSS puro), no el pin PNG por
 * defecto de Leaflet.
 *
 * El icono por defecto de Leaflet (`L.Icon.Default`) calcula la URL de sus
 * PNG en tiempo de ejecución (`_getIconUrl`), una técnica pensada para
 * `<script>` clásico que se rompe bajo un bundler con módulos: en esta app
 * acababa resolviendo contra `/media/marker-icon.png` (confundido con el
 * prefijo de las imágenes que sirve `core/storage`), que no existe → 404 y
 * marcador con el icono roto del navegador. Los PNG de Leaflet tampoco se
 * pueden importar como módulo sin configurar un loader de `.png` en esbuild,
 * que el proyecto no tiene. Un `divIcon` no depende de ningún fichero
 * externo, así que ninguno de los dos problemas aplica.
 */
const TAMANO = 22;

export function crearIcono(L: typeof Leaflet, color: string): Leaflet.DivIcon {
  return L.divIcon({
    className: 'marcador-punto',
    html: `<span style="background-color:${color}"></span>`,
    iconSize: [TAMANO, TAMANO],
    iconAnchor: [TAMANO / 2, TAMANO / 2],
  });
}
