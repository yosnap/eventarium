import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import { Injectable, InjectionToken, PLATFORM_ID, REQUEST, inject } from '@angular/core';

import {
  IDIOMA_POR_DEFECTO,
  Idioma,
  PREFIJO_DE_IDIOMA,
  esIdioma,
  leerIdiomaDeCookie,
  resolverIdioma,
  serializarCookieDeIdioma,
} from './idioma';

function rutaDeLaPeticion(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return '/';
  }
}

/**
 * Idioma de esta ejecución de la aplicación.
 *
 * Se decide una vez al arrancar: en SSR, con la URL y las cookies de la petición;
 * en el navegador, con `location` y `document.cookie`. Las dos vías aplican la
 * misma regla (`resolverIdioma`), así que la hidratación encuentra el mismo idioma
 * que pintó el servidor. Cambiar de idioma recarga la página.
 */
export const IDIOMA = new InjectionToken<Idioma>('IDIOMA', {
  providedIn: 'root',
  factory: () => {
    const documento = inject(DOCUMENT);
    if (isPlatformBrowser(inject(PLATFORM_ID))) {
      return resolverIdioma(documento.location.pathname, documento.cookie);
    }
    const peticion = inject(REQUEST, { optional: true });
    if (!peticion) {
      return IDIOMA_POR_DEFECTO;
    }
    return resolverIdioma(rutaDeLaPeticion(peticion.url), peticion.headers.get('cookie'));
  },
});

@Injectable({ providedIn: 'root' })
export class IdiomaService {
  private readonly documento = inject(DOCUMENT);
  private readonly esNavegador = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly activo = inject(IDIOMA);

  idioma(): Idioma {
    return this.activo;
  }

  /** Prefijo de URL del idioma activo, vacío para el idioma por defecto. */
  prefijo(): string {
    return PREFIJO_DE_IDIOMA[this.activo];
  }

  /**
   * Hace que los paneles sigan el idioma de la cuenta.
   *
   * Los paneles se pintan solo en el navegador y su idioma sale de una cookie que se
   * lee al arrancar. Si la cuenta tiene otro idioma, se guarda la cookie y se recarga
   * una vez; tras la recarga el idioma ya coincide y no se vuelve a recargar.
   * Devuelve `true` si va a recargar.
   */
  sincronizarConCuenta(localeDeCuenta: string | null | undefined): boolean {
    if (!this.esNavegador || !esIdioma(localeDeCuenta)) {
      return false;
    }
    if (leerIdiomaDeCookie(this.documento.cookie) !== localeDeCuenta) {
      this.documento.cookie = serializarCookieDeIdioma(localeDeCuenta);
    }
    // Si el navegador no guarda la cookie (bloqueo de cookies, extensiones), recargar
    // no cambiaría nada y se repetiría en cada carga del usuario: no se recarga.
    if (leerIdiomaDeCookie(this.documento.cookie) !== localeDeCuenta) {
      return false;
    }
    return this.recargarSiCambiaElIdioma(this.documento.location.pathname);
  }

  /**
   * Recarga la página si el idioma que corresponde a `url` no es el activo.
   *
   * El idioma se fija al arrancar, pero una navegación dentro de la aplicación puede
   * cruzar la frontera entre un panel (idioma de la cuenta) y una página pública
   * (idioma del prefijo). Sin recargar, la página pública saldría en el idioma del
   * panel, distinto del que sirve el servidor para esa misma URL. Devuelve `true` si
   * va a recargar.
   */
  recargarSiCambiaElIdioma(url: string): boolean {
    if (!this.esNavegador) {
      return false;
    }
    const ruta = url.split(/[?#]/, 1)[0] ?? '/';
    if (resolverIdioma(ruta, this.documento.cookie) === this.activo) {
      return false;
    }
    if (ruta === this.documento.location.pathname) {
      this.documento.location.reload();
    } else {
      this.documento.location.assign(url);
    }
    return true;
  }
}
