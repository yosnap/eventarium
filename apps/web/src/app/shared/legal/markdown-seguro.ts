import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  PLATFORM_ID,
  afterNextRender,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';

import { markdownToSafeHtml } from './sanitize-markdown';

/**
 * Única barrera para pintar Markdown escrito por terceros (textos legales de la
 * plataforma, políticas de cada organizador): nadie bindea `[innerHTML]` con
 * ese contenido fuera de este componente.
 *
 * En el servidor se muestra como texto plano (interpolado, siempre escapado):
 * `DOMPurify` necesita un DOM de navegador real (ver `sanitize-markdown.ts`).
 * En el navegador se sustituye por el HTML saneado **después** del primer
 * render (`afterNextRender`, que nunca corre en el servidor): si lo hiciera en
 * el primero, el DOM del cliente no coincidiría con el que pintó el servidor
 * y la hidratación fallaría. Sigue siendo reactivo: si el texto llega o
 * cambia más tarde, el `computed` vuelve a sanearlo.
 */
@Component({
  selector: 'app-markdown-seguro',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (html(); as seguro) {
      <div class="markdown" [innerHTML]="seguro"></div>
    } @else {
      <p class="markdown markdown--plano">{{ texto() }}</p>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    /* Lectura larga: medida de línea acotada (65-75ch es el rango legible). */
    .markdown {
      max-width: 42rem;
      line-height: 1.7;
      font-size: var(--fs-body);
      margin: 0;
    }
    .markdown--plano {
      white-space: pre-line;
    }
    .markdown ::ng-deep ul,
    .markdown ::ng-deep ol {
      padding-inline-start: 1.5rem;
    }
    .markdown ::ng-deep h2,
    .markdown ::ng-deep h3 {
      margin-top: var(--space-lg);
    }
  `,
})
export class MarkdownSeguro {
  readonly texto = input.required<string>();

  private readonly hidratado = signal(false);

  protected readonly html = computed(() =>
    this.hidratado() ? markdownToSafeHtml(this.texto()) : null,
  );

  constructor() {
    const enNavegador = isPlatformBrowser(inject(PLATFORM_ID));
    afterNextRender(() => this.hidratado.set(enNavegador));
  }
}
