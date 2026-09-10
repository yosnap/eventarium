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
        <p class="etiqueta">{{ t('publico.proximamente') }}</p>
        <h1>{{ theming.organizationName() }}</h1>
        @if (theming.branding()?.organizer_blurb; as descripcion) {
          <p>{{ descripcion }}</p>
        }
      </section>
    </ng-container>
  `,
  styles: `
    .minimal {
      display: grid;
      gap: var(--space-sm);
      max-width: 42rem;
      padding: var(--space-lg) 0;
    }
    .etiqueta {
      margin: 0;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.75rem;
      color: var(--muted);
    }
    h1 {
      margin: 0;
      font-size: var(--fs-h1);
    }
  `,
})
export class MinimalTemplate {
  protected readonly theming = inject(ThemingService);
}
