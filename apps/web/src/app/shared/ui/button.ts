import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

export type ButtonVariant = 'primario' | 'secundario' | 'terciario' | 'peligro';

/**
 * Botón del sistema de diseño.
 *
 * El hover nunca aclara el texto: solo cambia el fondo o el borde, y el par
 * resultante sigue cumpliendo AA en los dos temas (verificado en `ui.spec.ts`).
 * `bloque` y `compacto` son modificadores de ancho y tamaño respectivamente;
 * `compacto` reduce el padding horizontal, nunca la altura mínima táctil.
 */
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
      transition:
        background-color 0.15s ease,
        border-color 0.15s ease;
    }
    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .compacto {
      padding-left: 0.75rem;
      padding-right: 0.75rem;
    }
    .bloque {
      display: flex;
      width: 100%;
    }
    .primario {
      background-color: var(--accent);
      color: var(--on-accent);
    }
    .primario:hover:not(:disabled) {
      background-color: var(--accent-hi);
    }
    .secundario {
      background-color: transparent;
      color: var(--fg);
      border-color: var(--border-strong);
    }
    .secundario:hover:not(:disabled) {
      background-color: var(--surface-hi);
    }
    .terciario {
      background-color: transparent;
      color: var(--fg);
      border-color: transparent;
    }
    .terciario:hover:not(:disabled) {
      background-color: var(--surface-hi);
    }
    .peligro {
      background-color: transparent;
      color: var(--danger);
      border-color: var(--danger);
    }
    .peligro:hover:not(:disabled) {
      background-color: var(--danger-dim);
    }
  `,
})
export class Button {
  readonly variant = input<ButtonVariant>('primario');
  readonly type = input<'button' | 'submit'>('button');
  readonly disabled = input(false);
  readonly loading = input(false);
  /** Ancho completo del contenedor. */
  readonly bloque = input(false);
  /** Reduce el padding horizontal; no afecta a la altura mínima táctil. */
  readonly compacto = input(false);
  readonly pulsado = output<void>();

  protected clases(): string {
    const clases: string[] = [this.variant()];
    if (this.bloque()) clases.push('bloque');
    if (this.compacto()) clases.push('compacto');
    return clases.join(' ');
  }
}
