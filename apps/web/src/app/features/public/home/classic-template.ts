import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ThemingService } from '../../../core/theming/theming.service';

/** Plantilla pública «classic»: portada amplia con la marca del organizador. */
@Component({
  selector: 'app-classic-template',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <section class="portada">
        <h1>{{ theming.organizationName() }}</h1>
        @if (theming.branding()?.organizer_blurb; as descripcion) {
          <p class="descripcion">{{ descripcion }}</p>
        }
        <p class="aviso">{{ t('publico.proximamenteDetalle') }}</p>
      </section>
    </ng-container>
  `,
  styles: `
    .portada {
      display: grid;
      gap: var(--space-md);
      padding: var(--space-xl) var(--space-lg);
      background-color: var(--surface-2);
      border-radius: var(--radius-lg);
      text-align: center;
    }
    h1 {
      margin: 0;
      font-size: var(--fs-hero);
      color: var(--accent);
    }
    .descripcion {
      margin: 0 auto;
      max-width: 48rem;
      font-size: 1.125rem;
    }
    .aviso {
      margin: 0;
      color: var(--muted);
    }
  `,
})
export class ClassicTemplate {
  protected readonly theming = inject(ThemingService);
}
