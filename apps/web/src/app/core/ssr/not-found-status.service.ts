import { Injectable, RESPONSE_INIT, inject } from '@angular/core';

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

  mark(): void {
    if (this.responseInit) {
      this.responseInit.status = 404;
    }
  }
}
