import type { UrlMatchResult, UrlSegment } from '@angular/router';

import { PATRON_SLUG } from '../../../core/routing/rutas-publicas';

/**
 * `/eventos/{slug}` y todo lo que cuelga de él (no el directorio `/eventos`):
 * las direcciones anteriores a que la organización entrara en la URL. Ya no se
 * traducen; la ruta las manda a la portada.
 */
export function coincideConEnlaceAntiguo(segmentos: UrlSegment[]): UrlMatchResult | null {
  if (segmentos.length < 2 || segmentos[0].path !== 'eventos') {
    return null;
  }
  if (!PATRON_SLUG.test(segmentos[1].path)) {
    return null;
  }
  return { consumed: segmentos };
}
