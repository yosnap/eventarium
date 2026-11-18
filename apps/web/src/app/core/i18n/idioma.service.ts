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
  sigueIdiomaDeCuenta,
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
    const enCookie = leerIdiomaDeCookie(this.documento.cookie);
    if (enCookie !== localeDeCuenta) {
      this.documento.cookie = serializarCookieDeIdioma(localeDeCuenta);
    }
    if (localeDeCuenta === this.activo || !sigueIdiomaDeCuenta(this.documento.location.pathname)) {
      return false;
    }
    this.documento.location.reload();
    return true;
  }
}
