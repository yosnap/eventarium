import { inject } from '@angular/core';
import type { CanActivateFn, UrlMatchResult, UrlSegment } from '@angular/router';
import { Router } from '@angular/router';

import { PATRON_SLUG } from '../../../core/routing/rutas-publicas';

/**
 * `/eventos/{slug}` y todo lo que cuelga de él (no el directorio `/eventos`):
 * las direcciones anteriores a que la organización entrara en la URL. Ya no se
 * traducen; el guard las manda a la portada.
 *
 * Es un guard y no un `redirectTo` a propósito: el extractor de rutas de Angular
 * SSR trata una ruta con `matcher` y `redirectTo` como un comodín y acaba
 * redirigiendo a la portada TODAS las URLs de uno o dos segmentos, incluidas
 * `/{org}` y `/{org}/{evento}`. Un guard que devuelve un `UrlTree` sí produce la
 * redirección real en el servidor sin afectar al resto.
 */
export const enlaceAntiguoALaPortada: CanActivateFn = () => inject(Router).parseUrl('/');

export function coincideConEnlaceAntiguo(segmentos: UrlSegment[]): UrlMatchResult | null {
  if (segmentos.length < 2 || segmentos[0].path !== 'eventos') {
    return null;
  }
  if (!PATRON_SLUG.test(segmentos[1].path)) {
    return null;
  }
  return { consumed: segmentos };
}
