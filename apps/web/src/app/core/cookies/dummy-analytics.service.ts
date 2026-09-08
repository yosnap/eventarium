import { DOCUMENT, Injectable, inject } from '@angular/core';

const ID_SCRIPT = 'dummy-analytics-script';

/**
 * Script de ejemplo de categoría no esencial (analíticas), usado solo para
 * probar de verdad el bloqueo del banner de cookies (fase 5 del PRD): nunca
 * se carga hasta que la persona acepta explícitamente la categoría
 * `analytics`, ni antes por precarga ni especulativamente.
 *
 * Cloudflare Turnstile (`turnstile-widget.ts`) es un caso aparte: se
 * clasifica como necesario y **nunca** pasa por este servicio ni por
 * `CookieConsentService` — sigue cargando decida lo que decida la persona.
 */
@Injectable({ providedIn: 'root' })
export class DummyAnalyticsService {
  private readonly documento = inject(DOCUMENT);

  activar(): void {
    if (this.documento.getElementById(ID_SCRIPT)) {
      return;
    }
    const script = this.documento.createElement('script');
    script.id = ID_SCRIPT;
    script.src = '/assets/dummy-analytics.js';
    script.defer = true;
    this.documento.head.appendChild(script);
  }
}
