import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ThemeModeService } from '../../core/theming/theme-mode.service';

/**
 * Conmutador de modo oscuro/claro.
 *
 * `<button>` real con `aria-pressed`, no un `<div>` con `click`. El árbol de nodos es
 * invariable entre los dos modos —nada de `@if`/`@switch` sobre el estado del tema—:
 * solo cambian atributos y texto, para no desincronizar la hidratación bajo
 * `withEventReplay()` ni remontar el propio control.
 */
@Component({
  selector: 'app-theme-toggle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <button
        type="button"
        [attr.aria-pressed]="modo.esClaro()"
        [attr.aria-label]="
          t(modo.esClaro() ? 'comun.tema.activarOscuro' : 'comun.tema.activarClaro')
        "
        (click)="modo.alternar()"
      >
        <span aria-hidden="true">{{ modo.esClaro() ? '☀' : '☾' }}</span>
      </button>
    </ng-container>
  `,
  styles: `
    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 2.75rem;
      min-height: 2.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
      color: var(--fg);
      font-size: 1.125rem;
      cursor: pointer;
    }
  `,
})
export class ThemeToggle {
  protected readonly modo = inject(ThemeModeService);
}
