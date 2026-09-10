import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

export type ButtonVariant = 'primario' | 'secundario' | 'terciario' | 'peligro';

/**
 * Botón del sistema de diseño.
 *
 * El hover no aclara el texto en `.primario`/`.secundario` (solo cambia fondo o
 * borde); `.terciario`/`.peligro` sí cambian `color` en hover (a `--fg`), y el par
 * resultante sigue cumpliendo AA en los dos temas — `ui.spec.ts` solo cubre el
 * estado deshabilitado, no verifica contraste de hover.
 * `bloque` y `compacto` son modificadores de ancho y tamaño respectivamente;
 * `compacto` reduce el padding horizontal y usa la tipografía de rótulo
 * (`--fs-label` + tracking), nunca la altura mínima táctil.
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
      /* .btn: padding:0 20px, sin relleno vertical — el centrado lo da
         min-height (eventarium.css:159-165). */
      padding: 0 1.25rem;
      border: 1px solid transparent;
      /* .btn usa --r-sm (4px), no --r-md (eventarium.css:161). */
      border-radius: var(--radius-sm);
      font: inherit;
      /* .btn base es font-weight:500; solo --primary sube a 700
         (eventarium.css:163,166). */
      font-weight: 500;
      cursor: pointer;
      /* 44x44 px de área táctil: WCAG 2.5.5 objetivo mínimo. */
      min-height: 2.75rem;
      transition:
        background-color 0.15s ease,
        color 0.15s ease,
        border-color 0.15s ease;
    }
    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .bloque {
      display: flex;
      width: 100%;
    }
    .primario {
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
    }
    .primario:hover:not(:disabled) {
      background-color: var(--accent-hi);
      color: var(--on-accent);
    }
    .secundario {
      background-color: transparent;
      color: var(--fg);
      border-color: var(--border-strong);
    }
    .secundario:hover:not(:disabled) {
      background-color: var(--surface-hi);
      border-color: var(--faint);
      color: var(--fg);
    }
    /* .btn--quiet: padding:0 8px, color muted, sin fondo ni al hover
       (eventarium.css:170-171). */
    .terciario {
      background-color: transparent;
      color: var(--muted);
      border-color: transparent;
      padding: 0 0.5rem;
    }
    .terciario:hover:not(:disabled) {
      color: var(--fg);
    }
    .peligro {
      background-color: transparent;
      color: var(--danger);
      border-color: var(--danger);
    }
    .peligro:hover:not(:disabled) {
      background-color: var(--danger-dim);
      color: var(--fg);
    }
    /* .btn--sm: padding:0 14px, font-size:var(--fs-label), letter-spacing:.06em
       (eventarium.css:172). Reduce solo el padding horizontal: la altura mínima
       táctil no se toca, es una decisión de accesibilidad de esta fase, no de la
       referencia. Declarada DESPUÉS de las variantes (misma especificidad, gana
       por orden de aparición) para que combinar variant="terciario" compacto no
       pierda el padding compacto frente a .terciario{padding:0 .5rem}. */
    .compacto {
      padding-left: 0.875rem;
      padding-right: 0.875rem;
      font-size: var(--fs-label);
      letter-spacing: 0.06em;
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
