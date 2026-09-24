import { DOCUMENT, DestroyRef, Injectable, inject } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';

/** Datos mínimos para las etiquetas Open Graph de una página pública. */
export interface DatosOg {
  readonly title: string;
  readonly description?: string | null;
  readonly image?: string | null;
  readonly type?: string;
  /** Para páginas que no deben indexarse (p. ej. enlaces con token). */
  readonly noIndexar?: boolean;
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
    } else {
      this.meta.removeTag('name="robots"');
    }

    // Siempre se fija: si solo se pusiera cuando hay imagen, al navegar desde
    // un evento con portada a otra página se quedaría la portada anterior.
    const imagen = this.absoluta(datos.image || IMAGEN_OG_POR_DEFECTO);
    this.meta.updateTag({ property: 'og:image', content: imagen });
    this.meta.updateTag({ name: 'twitter:card', content: 'summary_large_image' });
    this.meta.updateTag({ name: 'twitter:image', content: imagen });
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
