import { DOCUMENT, DestroyRef, Injectable, inject } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';

import { IDIOMA_POR_DEFECTO, Idioma, urlEnIdioma } from '../i18n/idioma';
import { IdiomaService } from '../i18n/idioma.service';
import { DecisionDeIndexacion, decidirIndexacion } from './indexacion-por-idioma';
import { ThemingService } from '../theming/theming.service';

/** Datos mínimos para las etiquetas Open Graph de una página pública. */
export interface DatosOg {
  readonly title: string;
  readonly description?: string | null;
  readonly image?: string | null;
  readonly type?: string;
  /** Para páginas que no deben indexarse (p. ej. enlaces con token). */
  readonly noIndexar?: boolean;
  /**
   * Ruta de la página sin prefijo de idioma (`/acme/iawic`). Sin ella se usa la ruta
   * actual sin parámetros. Se publica, con el prefijo que toque, como `rel=canonical`.
   */
  readonly canonica?: string;
  /** Contenido escrito por el organizador: solo se indexa en los idiomas al día. */
  readonly contenidoDelOrganizador?: boolean;
  readonly idiomaOrigen?: Idioma;
  readonly idiomasAlDia?: readonly Idioma[];
}

/**
 * Tarjeta de la plataforma (1200×630) para las páginas sin imagen propia. Sin
 * ella, un enlace a la landing, a una sesión o a un evento sin portada se
 * comparte sin vista previa.
 */
export const IMAGEN_OG_POR_DEFECTO = 'assets/og/eventarium.jpg';

/**
 * Envuelve `Meta`/`Title` de `@angular/platform-browser` para fijar OG tags de forma
 * consistente. Primer uso de `Meta` en el proyecto: ver `docs/arquitectura.md`.
 *
 * `updateTag` crea la etiqueta si no existe y la actualiza si ya estaba — no hace
 * falta comprobar antes si la página anterior la había dejado puesta.
 */
@Injectable({ providedIn: 'root' })
export class SeoMetaService {
  private readonly meta = inject(Meta);
  private readonly title = inject(Title);
  private readonly documento = inject(DOCUMENT);
  private readonly idioma = inject(IdiomaService);
  private readonly theming = inject(ThemingService);

  set(datos: DatosOg): void {
    this.title.setTitle(datos.title);
    this.meta.updateTag({ property: 'og:title', content: datos.title });
    this.meta.updateTag({ property: 'og:type', content: datos.type ?? 'website' });

    if (datos.description) {
      this.meta.updateTag({ property: 'og:description', content: datos.description });
      this.meta.updateTag({ name: 'description', content: datos.description });
    } else {
      // Sin esto se quedaría la descripción de la página anterior.
      this.meta.removeTag('property="og:description"');
      this.meta.removeTag('name="description"');
    }
    if (datos.noIndexar) {
      this.meta.updateTag({ name: 'robots', content: 'noindex, nofollow' });
      this.fijarCanonica(undefined);
      this.fijarAlternativas([]);
      this.fijarOgLocale(this.idioma.idioma().replace('-', '_'), []);
    } else {
      this.meta.removeTag('name="robots"');
      const decision = decidirIndexacion({
        ruta: datos.canonica ?? this.rutaActualSinPrefijo(),
        activo: this.idioma.idioma(),
        contenidoDelOrganizador: datos.contenidoDelOrganizador ?? false,
        idiomaOrigen: datos.idiomaOrigen,
        idiomasAlDia: datos.idiomasAlDia,
        idiomasActivos: this.theming.idiomasActivos(),
      });
      this.fijarCanonica(decision.canonica);
      this.fijarAlternativas(decision.alternativas);
      this.fijarOgLocale(decision.ogLocale, decision.ogLocaleAlternativos);
    }

    // Siempre se fija: si solo se pusiera cuando hay imagen, al navegar desde
    // un evento con portada a otra página se quedaría la portada anterior.
    const imagen = this.absoluta(datos.image || IMAGEN_OG_POR_DEFECTO);
    this.meta.updateTag({ property: 'og:image', content: imagen });
    this.meta.updateTag({ name: 'twitter:card', content: 'summary_large_image' });
    this.meta.updateTag({ name: 'twitter:image', content: imagen });
  }

  /** `<link rel="canonical">`: se crea, se actualiza o se quita según la página. */
  private fijarCanonica(ruta: string | undefined): void {
    const cabecera = this.documento.head;
    const existente = cabecera.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!ruta) {
      existente?.remove();
      return;
    }
    const enlace = existente ?? this.documento.createElement('link');
    enlace.setAttribute('rel', 'canonical');
    enlace.setAttribute('href', this.absoluta(ruta));
    if (!existente) {
      cabecera.appendChild(enlace);
    }
  }

  /** `<link rel="alternate" hreflang>`: se sustituyen todos en cada página. */
  private fijarAlternativas(alternativas: DecisionDeIndexacion['alternativas']): void {
    const cabecera = this.documento.head;
    cabecera.querySelectorAll('link[rel="alternate"][hreflang]').forEach((e) => e.remove());
    for (const { idioma, ruta } of alternativas) {
      const enlace = this.documento.createElement('link');
      enlace.setAttribute('rel', 'alternate');
      enlace.setAttribute('hreflang', idioma);
      enlace.setAttribute('href', this.absoluta(ruta));
      cabecera.appendChild(enlace);
    }
  }

  private fijarOgLocale(actual: string, alternativos: readonly string[]): void {
    this.meta.updateTag({ property: 'og:locale', content: actual });
    while (this.meta.getTag('property="og:locale:alternate"')) {
      this.meta.removeTag('property="og:locale:alternate"');
    }
    for (const alternativo of alternativos) {
      this.meta.addTag({ property: 'og:locale:alternate', content: alternativo });
    }
  }

  /** Ruta actual sin prefijo de idioma ni parámetros. */
  private rutaActualSinPrefijo(): string {
    return urlEnIdioma(this.documento.location.pathname, IDIOMA_POR_DEFECTO);
  }

  /**
   * Los rastreadores no resuelven rutas relativas en `og:image`. En el SSR,
   * `location` sale de la URL de la petición (con `x-forwarded-host`/`-proto`
   * ya aplicados en `server.ts`), así que apunta al dominio público. Se
   * resuelve contra el origen y no contra `baseURI`: domino no lo implementa y
   * el `<base href="/">` de la app equivale a la raíz del origen.
   */
  private absoluta(url: string): string {
    return new URL(url, `${this.documento.location.origin}/`).href;
  }
}

/**
 * Lo que usan las páginas públicas en vez de inyectar `SeoMetaService`.
 * Las peticiones de datos no se cancelan al salir de la página: si la
 * respuesta llega con la página ya destruida, su título y sus OG pisarían los
 * de la página a la que se ha navegado. Se llama en el constructor (contexto
 * de inyección).
 */
export function seoDePagina(): Pick<SeoMetaService, 'set'> {
  const seo = inject(SeoMetaService);
  let viva = true;
  inject(DestroyRef).onDestroy(() => {
    viva = false;
  });
  return {
    set: (datos) => {
      if (viva) {
        seo.set(datos);
      }
    },
  };
}
