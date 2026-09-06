import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * Mensaje de estado.
 *
 * Los errores se anuncian con `role="alert"` (asertivo) y el resto con `role="status"`,
 * para que un lector de pantalla interrumpa solo cuando de verdad hace falta.
 */
@Component({
  selector: 'app-alert',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div [attr.role]="rol()" [class]="tone()">
      @if (title()) {
        <strong>{{ title() }}</strong>
      }
      <ng-content />
    </div>
  `,
  styles: `
    div {
      padding: var(--space-md);
      border-radius: var(--radius-md);
      border: 1px solid var(--color-border);
      display: grid;
      gap: var(--space-xs);
    }
    .error {
      border-color: var(--color-danger);
      color: var(--color-danger);
    }
    .exito {
      border-color: var(--color-success);
      color: var(--color-success);
    }
    .info {
      background-color: var(--color-surface-muted);
      color: var(--color-text);
    }
  `,
})
export class Alert {
  readonly tone = input<'info' | 'error' | 'exito'>('info');
  readonly title = input<string | null>(null);

  protected readonly rol = computed(() => (this.tone() === 'error' ? 'alert' : 'status'));
}
