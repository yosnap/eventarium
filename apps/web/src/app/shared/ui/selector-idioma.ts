import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import {
  IDIOMAS,
  NOMBRE_DEL_IDIOMA,
  PREFIJO_DE_IDIOMA,
  ofreceCambioDeIdioma,
  urlEnIdioma,
} from '../../core/i18n/idioma';
import { urlActual } from '../../core/i18n/url-actual';
import { IdiomaService } from '../../core/i18n/idioma.service';

/**
 * Enlaces a esta misma página en cada idioma.
 *
 * Son enlaces normales (`href`), no navegación del router: cambiar de idioma recarga
 * la página para que el servidor la pinte ya en el idioma nuevo. La URL sale de la
 * ruta actual del router, nunca de un parámetro recibido.
 */
@Component({
  selector: 'app-selector-idioma',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    @if (opciones().length > 0) {
      <nav *transloco="let t" [attr.aria-label]="t('comun.idioma')" [class.compacto]="compacto()">
        <ul>
          @for (opcion of opciones(); track opcion.idioma) {
            <li>
              <a
                [attr.href]="opcion.url"
                [attr.hreflang]="opcion.idioma"
                [attr.lang]="opcion.idioma"
                [attr.aria-current]="opcion.activo ? 'true' : null"
                [attr.aria-label]="compacto() ? opcion.nombre : null"
              >
                {{ compacto() ? opcion.codigo : opcion.nombre }}
              </a>
            </li>
          }
        </ul>
      </nav>
    }
  `,
  styles: `
    ul {
      display: flex;
      gap: var(--space-2, 0.5rem);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    a {
      display: inline-flex;
      align-items: center;
      min-height: 2.75rem;
      padding-inline: var(--space-2, 0.5rem);
      color: var(--fg-muted);
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
    a[aria-current='true'] {
      color: var(--fg);
      font-weight: 600;
    }
    .compacto a {
      text-transform: uppercase;
      font-size: 0.875rem;
    }
  `,
})
export class SelectorIdioma {
  /** Códigos cortos (ES · EN) en la cabecera; nombres completos en el pie. */
  readonly compacto = input(false);

  private readonly activo = inject(IdiomaService).idioma();
  private readonly url = urlActual();

  protected readonly opciones = computed(() =>
    !ofreceCambioDeIdioma(this.url())
      ? []
      : IDIOMAS.map((idioma) => ({
          idioma,
          nombre: NOMBRE_DEL_IDIOMA[idioma],
          codigo: PREFIJO_DE_IDIOMA[idioma] || idioma.slice(0, 2),
          url: urlEnIdioma(this.url(), idioma),
          activo: idioma === this.activo,
        })),
  );
}
