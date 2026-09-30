import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import type { CanActivateFn, UrlMatchResult, UrlSegment } from '@angular/router';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { PATRON_SLUG } from '../../../core/routing/rutas-publicas';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';

interface EnlaceCanonico {
  readonly organization_slug: string;
  readonly slug: string;
}

/**
 * Enlaces antiguos `/eventos/{slug}/…`: consulta a qué organización y slug
 * pertenecen hoy y redirige conservando el resto de la ruta, la query y el
 * fragmento. Devolver un `UrlTree` desde un guard hace que el servidor
 * responda con una redirección real en SSR y que el navegador reemplace la
 * entrada del historial. Si el evento ya no es público, deja pasar a la
 * página 404 de la ruta.
 */
export const enlaceAntiguo: CanActivateFn = async (route, state) => {
  const slug = route.paramMap.get('slug');
  if (!slug || !PATRON_SLUG.test(slug)) {
    return true;
  }
  const http = inject(HttpClient);
  const api = inject(ApiService);
  const router = inject(Router);
  const estado = inject(NotFoundStatusService);

  try {
    const destino = await firstValueFrom(
      http.get<EnlaceCanonico>(api.url(`/public/events/${encodeURIComponent(slug)}/canonical`), {
        headers: api.serverForwardHeaders(),
      }),
    );
    // El prefijo se quita sobre la URL tal como llegó (codificada), no sobre el slug decodificado.
    const resto = state.url.replace(/^\/eventos\/[^/?#]+/, '');
    return router.parseUrl(`/${destino.organization_slug}/${destino.slug}${resto}`);
  } catch (error) {
    // Solo un 404 del API es «ya no existe». Un 429, un 500 o un corte de red
    // no lo son: no deben publicarse como 404.
    if ((error as { status?: number }).status !== 404) {
      estado.falloTemporal.set(true);
    }
    return true;
  }
};

/** `/eventos/{slug}` y todo lo que cuelga de él (no el directorio `/eventos`). */
export function coincideConEnlaceAntiguo(segmentos: UrlSegment[]): UrlMatchResult | null {
  if (segmentos.length < 2 || segmentos[0].path !== 'eventos') {
    return null;
  }
  if (!PATRON_SLUG.test(segmentos[1].path)) {
    return null;
  }
  return { consumed: segmentos, posParams: { slug: segmentos[1] } };
}
