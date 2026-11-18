import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  afterNextRender,
  computed,
  inject,
  signal,
} from '@angular/core';

import { IDIOMAS, Idioma, ofreceCambioDeIdioma, urlEnIdioma } from '../../core/i18n/idioma';
import { urlActual } from '../../core/i18n/url-actual';
import { IdiomaService } from '../../core/i18n/idioma.service';
import { ThemingService } from '../../core/theming/theming.service';

/**
 * Textos del aviso en el idioma de quien visita, que no es el de la página: por eso
 * no salen de Transloco, que solo tiene cargado el idioma de la página.
 */
const TEXTOS: Readonly<Record<Idioma, { readonly ver: string; readonly cerrar: string }>> = {
  'es-ES': { ver: 'Ver esta página en español', cerrar: 'Cerrar' },
  'en-US': { ver: 'View this page in English', cerrar: 'Dismiss' },
};

const CLAVE_DESCARTE = 'eventarium.aviso-idioma-descartado';

/** Primer idioma del navegador que la plataforma ofrece, comparando sin región. */
export function idiomaPreferido(idiomasDelNavegador: readonly string[]): Idioma | null {
  for (const etiqueta of idiomasDelNavegador) {
    const base = etiqueta.toLowerCase().split('-')[0];
    const encontrado = IDIOMAS.find((idioma) => idioma.toLowerCase().split('-')[0] === base);
    if (encontrado) {
      return encontrado;
    }
  }
  return null;
}

function leerDescarte(): boolean {
  try {
    return localStorage.getItem(CLAVE_DESCARTE) === '1';
  } catch {
    return false;
  }
}

/**
 * Aviso flotante y discreto que ofrece la página en el idioma del navegador cuando no coincide
 * con el de la página. Nunca redirige. Solo existe en el navegador y después de
 * hidratar: el HTML del servidor no depende de `Accept-Language`.
 */
@Component({
  selector: 'app-aviso-idioma',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (sugerido(); as idioma) {
      <aside class="aviso" [attr.lang]="idioma" [attr.aria-label]="textos(idioma).ver">
        <a [attr.href]="url(idioma)" [attr.hreflang]="idioma">{{ textos(idioma).ver }}</a>
        <button type="button" (click)="descartar()">{{ textos(idioma).cerrar }}</button>
      </aside>
    }
  `,
  styles: `
    /* Flotante: aparece después de cargar y no debe desplazar la página. */
    .aviso {
      position: fixed;
      top: calc(var(--space-4, 1rem) * 4.5);
      right: var(--space-4, 1rem);
      z-index: 40;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-3, 0.75rem);
      max-width: calc(100vw - 2 * var(--space-4, 1rem));
      padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
      background-color: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-md);
      color: var(--fg);
      font-size: 0.9375rem;
    }
    a {
      color: var(--fg);
      font-weight: 600;
    }
    button {
      min-height: 2.75rem;
      padding-inline: var(--space-3, 0.75rem);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: transparent;
      color: var(--fg-muted);
      cursor: pointer;
    }
  `,
})
export class AvisoIdioma {
  private readonly urlDeLaPagina = urlActual();
  private readonly documento = inject(DOCUMENT);
  private readonly activo = inject(IdiomaService).idioma();
  private readonly theming = inject(ThemingService);
  private readonly preferido = signal<Idioma | null>(null);
  private readonly descartado = signal(false);

  protected readonly sugerido = computed(() => {
    const preferido = this.preferido();
    return preferido &&
      preferido !== this.activo &&
      !this.descartado() &&
      ofreceCambioDeIdioma(this.urlDeLaPagina())
      ? preferido
      : null;
  });

  constructor() {
    afterNextRender(() => {
      this.descartado.set(leerDescarte());
      const navegador = this.documento.defaultView?.navigator;
      const preferido = idiomaPreferido(navegador?.languages ?? [navegador?.language ?? '']);
      this.preferido.set(
        preferido && this.theming.idiomasActivos().includes(preferido) ? preferido : null,
      );
    });
  }

  protected textos(idioma: Idioma) {
    return TEXTOS[idioma];
  }

  protected url(idioma: Idioma): string {
    return urlEnIdioma(this.urlDeLaPagina(), idioma);
  }

  protected descartar(): void {
    this.descartado.set(true);
    try {
      localStorage.setItem(CLAVE_DESCARTE, '1');
    } catch {
      // Sin almacenamiento (modo privado, bloqueo): se descarta solo en esta visita.
    }
  }
}
