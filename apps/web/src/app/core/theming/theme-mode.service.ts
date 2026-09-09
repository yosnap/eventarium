import { isPlatformBrowser } from '@angular/common';
import {
  DOCUMENT,
  Injectable,
  PLATFORM_ID,
  REQUEST,
  afterNextRender,
  computed,
  inject,
  signal,
} from '@angular/core';

import {
  ModoDeTema,
  atributoDeTemaParaHtml,
  leerModoDeCookie,
  leerModoDeCookieOpcional,
  serializarCookieDeTema,
} from './theme-cookie';

/**
 * Modo oscuro/claro elegido por la persona que navega.
 *
 * Dimensión independiente de la plantilla de tema de la organización
 * (`ThemingService`): esta decide la paleta, este decide qué modo de esa paleta se ve.
 * Persistencia por cookie (no `localStorage`, a diferencia de
 * `CookieConsentService`) para que SSR pueda resolver el modo antes de servir el HTML,
 * igual que hace `server.ts` sobre la misma cabecera `Cookie`.
 *
 * Sin desajuste de hidratación: la plantilla del conmutador (`ThemeToggle`) mantiene
 * un árbol de nodos invariable — nada de `@if`/`@switch` sobre `modo()` — y solo la
 * sincronización tras `afterNextRender` toca el atributo real del documento, nunca la
 * estructura del propio control.
 */
@Injectable({ providedIn: 'root' })
export class ThemeModeService {
  private readonly esNavegador = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly documento = inject(DOCUMENT);
  private readonly peticion = inject(REQUEST, { optional: true });

  private readonly modoActual = signal<ModoDeTema>(this.resolverModoInicial());

  readonly modo = this.modoActual.asReadonly();
  readonly esClaro = computed(() => this.modo() === 'claro');

  constructor() {
    if (this.esNavegador) {
      // Sincroniza el atributo real del documento con el modo resuelto, sin remontar
      // ningún nodo: cubre el caso en que SSR hubiera pintado un modo distinto del que
      // indica la cookie que el propio navegador acaba de leer.
      afterNextRender(() => this.pintarAtributo(this.modoActual()));
    }
  }

  /** No hace nada en el servidor: ahí no hay nada que persistir. */
  alternar(): void {
    if (!this.esNavegador) {
      return;
    }
    const nuevo: ModoDeTema = this.modoActual() === 'oscuro' ? 'claro' : 'oscuro';
    this.modoActual.set(nuevo);
    this.documento.cookie = serializarCookieDeTema(nuevo);
    this.pintarAtributo(nuevo);
  }

  private resolverModoInicial(): ModoDeTema {
    if (this.esNavegador) {
      return this.resolverModoEnNavegador();
    }
    // En servidor no se escribe nada; a falta de cookie en la petición, oscuro.
    return leerModoDeCookie(this.peticion?.headers.get('cookie') ?? null);
  }

  /**
   * La preferencia guardada gana; si no hay ninguna, se respeta
   * `prefers-color-scheme`; a falta de todo, oscuro. Solo la cookie es anti-parpadeo
   * garantizado (la resuelve también `server.ts`): sin cookie, un navegador que
   * prefiere claro puede ver un instante el oscuro por defecto antes de que este
   * servicio se inicialice, igual que cualquier lectura de `prefers-color-scheme` que
   * SSR no puede conocer.
   */
  private resolverModoEnNavegador(): ModoDeTema {
    const deCookie = leerModoDeCookieOpcional(this.documento.cookie);
    if (deCookie) {
      return deCookie;
    }
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      return window.matchMedia('(prefers-color-scheme: light)').matches ? 'claro' : 'oscuro';
    }
    return 'oscuro';
  }

  private pintarAtributo(modo: ModoDeTema): void {
    const raiz = this.documento.documentElement;
    const atributo = atributoDeTemaParaHtml(modo);
    if (atributo) {
      raiz.setAttribute('data-theme', atributo);
    } else {
      raiz.removeAttribute('data-theme');
    }
  }
}
