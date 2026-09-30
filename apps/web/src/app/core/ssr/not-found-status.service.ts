import { Injectable, RESPONSE_INIT, inject, signal } from '@angular/core';

/**
 * Traduce un "no encontrado" de una página pública al código de estado HTTP real
 * de la respuesta SSR, en vez de servir un 200 con un panel de error dentro.
 *
 * `RESPONSE_INIT` es `null` en compilación, CSR, SSG y extracción de rutas en
 * desarrollo — solo existe durante un renderizado en servidor real, así que
 * `mark()` es un no-op seguro en cualquier otro contexto.
 */
@Injectable({ providedIn: 'root' })
export class NotFoundStatusService {
  private readonly responseInit = inject(RESPONSE_INIT, { optional: true });

  /** Un guard no pudo comprobar la ruta (fallo temporal del API): la página
   * 404 debe responder 503 y no 404, para que un rastreador no des-indexe un
   * enlace válido. Se consume una sola vez. */
  readonly falloTemporal = signal(false);

  mark(): void {
    if (this.responseInit) {
      this.responseInit.status = 404;
    }
  }

  markUnavailable(): void {
    if (this.responseInit) {
      this.responseInit.status = 503;
    }
  }
}
