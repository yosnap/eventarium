import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter, map } from 'rxjs';
import { TranslocoDirective } from '@jsverse/transloco';

import { IDIOMAS, NOMBRE_DEL_IDIOMA, PREFIJO_DE_IDIOMA, urlEnIdioma } from '../../core/i18n/idioma';
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

  private readonly router = inject(Router);
  private readonly activo = inject(IdiomaService).idioma();

  /** La cabecera no se vuelve a crear al navegar: la URL tiene que seguir al router. */
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((evento) => evento instanceof NavigationEnd),
      map((evento) => evento.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly opciones = computed(() =>
    IDIOMAS.map((idioma) => ({
      idioma,
      nombre: NOMBRE_DEL_IDIOMA[idioma],
      codigo: PREFIJO_DE_IDIOMA[idioma] || idioma.slice(0, 2),
      url: urlEnIdioma(this.url(), idioma),
      activo: idioma === this.activo,
    })),
  );
}
