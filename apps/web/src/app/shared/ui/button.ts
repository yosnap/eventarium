import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/** Botón del sistema de diseño. */
@Component({
  selector: 'app-button',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button
      [type]="type()"
      [disabled]="disabled() || loading()"
      [attr.aria-busy]="loading() ? 'true' : null"
      [class]="clases()"
      (click)="pulsado.emit()"
    >
      <ng-content />
    </button>
  `,
  styles: `
    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: var(--space-sm);
      padding: 0.625rem 1.25rem;
      border: 1px solid transparent;
      border-radius: var(--radius-md);
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      /* 44x44 px de área táctil: WCAG 2.5.5 objetivo mínimo. */
      min-height: 2.75rem;
    }
    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .primario {
      background-color: var(--color-primary);
      color: var(--color-primary-contrast);
    }
    .secundario {
      background-color: transparent;
      color: var(--color-primary);
      border-color: var(--color-border);
    }
    .peligro {
      background-color: var(--color-danger);
      color: #fff;
    }
  `,
})
export class Button {
  readonly variant = input<'primario' | 'secundario' | 'peligro'>('primario');
  readonly type = input<'button' | 'submit'>('button');
  readonly disabled = input(false);
  readonly loading = input(false);
  readonly pulsado = output<void>();

  protected clases(): string {
    return this.variant();
  }
}
