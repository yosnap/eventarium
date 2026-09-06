import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/**
 * Pantalla que se muestra cuando no se ha podido cargar el branding.
 *
 * Se enseña este error en lugar de pintar la paleta por defecto: mostrar una marca que
 * no es la de la organización sería peor que decir claramente que algo falla.
 */
@Component({
  selector: 'app-site-unavailable',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" role="main" tabindex="-1">
        <h1>{{ t('errores.sitioNoDisponible') }}</h1>
        <p>{{ t('errores.sitioNoDisponibleDetalle') }}</p>
      </main>
    </ng-container>
  `,
  styles: `
    main {
      display: grid;
      place-content: center;
      gap: var(--space-md);
      min-height: 100vh;
      padding: var(--space-lg);
      text-align: center;
    }
  `,
})
export class SiteUnavailable {}
