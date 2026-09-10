import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ThemingService } from '../../../core/theming/theming.service';

/** Plantilla pública «minimal»: texto alineado a la izquierda, sin bloque destacado. */
@Component({
  selector: 'app-minimal-template',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <section class="minimal">
        <p class="rotulo-seccion etiqueta-acento">{{ t('publico.proximamente') }}</p>
        <h1>{{ theming.organizationName() }}</h1>
        @if (theming.branding()?.organizer_blurb; as descripcion) {
          <p class="descripcion">{{ descripcion }}</p>
        }
      </section>
    </ng-container>
  `,
  styles: `
    .minimal {
      display: grid;
      gap: var(--space-sm);
      max-width: 42rem;
      padding: var(--space-lg) 0 var(--space-lg);
      border-bottom: 1px solid var(--border);
    }
    .etiqueta-acento {
      color: var(--accent);
    }
    h1 {
      margin: 0;
      font-size: var(--fs-h1);
    }
    .descripcion {
      margin: 0;
      color: var(--muted);
    }
  `,
})
export class MinimalTemplate {
  protected readonly theming = inject(ThemingService);
}
