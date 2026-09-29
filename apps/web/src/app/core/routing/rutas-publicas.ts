import { type UrlMatcher, type UrlMatchResult, UrlSegment } from '@angular/router';

/**
 * Único lugar que conoce la forma de las URLs públicas de un evento
 * (`/{org}/{evento}/…`) y de las llamadas al API que cuelgan de él. Ninguna
 * página construye estas rutas a mano.
 */

/** Mismo patrón que `SLUG_PATTERN` del API: sin puntos ni extensiones, para que
 * `/foo.php` o `/.env` nunca se traten como una organización. */
export const PATRON_SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/**
 * Matcher de `/:org` (página pública de una organización): un solo segmento que
 * cumpla `PATRON_SLUG`. Sin parámetros matriz, por la misma razón que el del
 * evento.
 */
export const coincideConOrganizacion: UrlMatcher = (segmentos: UrlSegment[]) => {
  if (segmentos.length !== 1 || !PATRON_SLUG.test(segmentos[0].path)) {
    return null;
  }
  const limpio = new UrlSegment(segmentos[0].path, {});
  return { consumed: [limpio], posParams: { org: limpio } };
};

/** Ruta de Angular hacia una página del evento: `rutaEvento('acme', 'iawic', 'programa')`. */
export function rutaEvento(org: string, slug: string, ...resto: (string | number)[]): string[] {
  return ['/', org, slug, ...resto.map(String)];
}

/**
 * Vuelta al evento desde las pantallas de pago. Un pago iniciado antes de que
 * la organización entrara en la URL solo trae el slug: se enlaza al formato
 * antiguo, que redirige a la URL actual.
 */
export function rutaDeVueltaAlEvento(org: string | null, slug: string): string[] {
  return org ? rutaEvento(org, slug) : ['/eventos', slug];
}

/**
 * Ruta de Angular hacia la página pública de una organización. Aún no existe
 * la ruta `/:org`: solo se enlaza cuando `page_public` es `true`, y eso ocurre
 * a partir de la página pública de organización.
 */
export function rutaOrganizacion(org: string): string[] {
  return ['/', org];
}

/** Ruta como texto (para enlaces absolutos, compartir o calendarios). */
export function urlEvento(org: string, slug: string, ...resto: (string | number)[]): string {
  return `/${[org, slug, ...resto].join('/')}`;
}

/** Ruta del API de un recurso público del evento, sin el prefijo de versión. */
export function apiEvento(org: string, slug: string, sufijo = ''): string {
  return `/public/organizations/${org}/events/${slug}${sufijo}`;
}

/**
 * Matcher de `:org/:slug/<resto>`. `resto` describe los segmentos que siguen
 * (`'sesiones/:sessionId'`); un segmento con `:` es un parámetro. Exige que
 * organización y evento cumplan `PATRON_SLUG`.
 */
export function coincideConEvento(resto = ''): UrlMatcher {
  const patron = resto === '' ? [] : resto.split('/');
  return (segmentos: UrlSegment[]): UrlMatchResult | null => {
    if (segmentos.length !== 2 + patron.length) {
      return null;
    }
    const [org, slug] = segmentos;
    if (!PATRON_SLUG.test(org.path) || !PATRON_SLUG.test(slug.path)) {
      return null;
    }
    const posParams: Record<string, UrlSegment> = { org, slug };
    for (const [indice, esperado] of patron.entries()) {
      const segmento = segmentos[2 + indice];
      if (esperado.startsWith(':')) {
        posParams[esperado.slice(1)] = segmento;
      } else if (segmento.path !== esperado) {
        return null;
      }
    }
    // Sin parámetros matriz: el router los mezcla encima de `posParams` y
    // `/acme/iawic;org=…` sustituiría la organización por un valor sin validar.
    const limpios = segmentos.map((s) => new UrlSegment(s.path, {}));
    const limpiosParams: Record<string, UrlSegment> = {};
    for (const [nombre, segmento] of Object.entries(posParams)) {
      limpiosParams[nombre] = new UrlSegment(segmento.path, {});
    }
    return { consumed: limpios, posParams: limpiosParams };
  };
}
