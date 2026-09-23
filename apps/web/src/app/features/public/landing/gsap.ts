import { isPlatformBrowser } from '@angular/common';
import { PLATFORM_ID, inject } from '@angular/core';
import type { gsap as Gsap } from 'gsap';
import type { ScrollTrigger as ScrollTriggerPlugin } from 'gsap/ScrollTrigger';

export interface GsapCargado {
  readonly gsap: typeof Gsap;
  readonly ScrollTrigger: typeof ScrollTriggerPlugin;
}

let carga: Promise<GsapCargado> | null = null;

/**
 * Único punto de entrada a GSAP en la aplicación.
 *
 * Import dinámico y solo en navegador: GSAP toca `window`/`document` al
 * registrarse, y el mismo grafo de módulos se compila para el servidor SSR.
 * Fuera del navegador devuelve `null`, y el llamador no anima nada — el HTML
 * servido nunca depende de esta librería para ser visible.
 */
export function cargarGsap(): Promise<GsapCargado | null> {
  if (!isPlatformBrowser(inject(PLATFORM_ID))) {
    return Promise.resolve(null);
  }
  carga ??= Promise.all([import('gsap'), import('gsap/ScrollTrigger')]).then(([modulo, plugin]) => {
    modulo.gsap.registerPlugin(plugin.ScrollTrigger);
    return { gsap: modulo.gsap, ScrollTrigger: plugin.ScrollTrigger };
  });
  return carga;
}
