import { isPlatformBrowser } from '@angular/common';
import { Injectable, PLATFORM_ID, inject } from '@angular/core';
import type { gsap as Gsap } from 'gsap';
import type { ScrollTrigger as ScrollTriggerPlugin } from 'gsap/ScrollTrigger';

export interface GsapCargado {
  readonly gsap: typeof Gsap;
  readonly ScrollTrigger: typeof ScrollTriggerPlugin;
}

/**
 * Único punto de entrada a GSAP en la aplicación.
 *
 * Import dinámico y solo en navegador: GSAP toca `window`/`document` al
 * registrarse, y el mismo grafo de módulos se compila para el servidor SSR.
 * Fuera del navegador devuelve `null`, y el llamador no anima nada — el HTML
 * servido nunca depende de esta librería para ser visible.
 *
 * Es un servicio (y no una función suelta) para poder sustituirlo por DI en
 * los tests: el runner de Angular no permite `vi.mock` sobre módulos relativos.
 */
@Injectable({ providedIn: 'root' })
export class GsapLoader {
  private readonly enNavegador = isPlatformBrowser(inject(PLATFORM_ID));
  private carga: Promise<GsapCargado> | null = null;

  cargar(): Promise<GsapCargado | null> {
    if (!this.enNavegador) {
      return Promise.resolve(null);
    }
    this.carga ??= Promise.all([import('gsap'), import('gsap/ScrollTrigger')]).then(
      ([modulo, plugin]) => {
        modulo.gsap.registerPlugin(plugin.ScrollTrigger);
        return { gsap: modulo.gsap, ScrollTrigger: plugin.ScrollTrigger };
      },
    );
    return this.carga;
  }
}
