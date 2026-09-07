import { Injectable, inject } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';

/** Datos mínimos para las etiquetas Open Graph de una página pública. */
export interface DatosOg {
  readonly title: string;
  readonly description?: string | null;
  readonly image?: string | null;
  readonly type?: string;
}

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

  set(datos: DatosOg): void {
    this.title.setTitle(datos.title);
    this.meta.updateTag({ property: 'og:title', content: datos.title });
    this.meta.updateTag({ property: 'og:type', content: datos.type ?? 'website' });

    if (datos.description) {
      this.meta.updateTag({ property: 'og:description', content: datos.description });
      this.meta.updateTag({ name: 'description', content: datos.description });
    }
    if (datos.image) {
      this.meta.updateTag({ property: 'og:image', content: datos.image });
    }
  }
}
