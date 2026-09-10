import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

let contadorDeInstancias = 0;

/**
 * Interruptor (switch), sobre `.sw-btn`/`.sw-wrap`/`.sw-state` de la
 * referencia (`assets/eventarium.css:298-311`, `assets/cookies.js:57-68`).
 *
 * Es un `<button role="switch" aria-checked>` real, no un checkbox
 * disfrazado: la referencia usa ese patrón (botón + `aria-checked`), y el
 * estado se lee por posición del pomo, por color Y por el texto de
 * `sw-state` — nunca solo por color.
 */
@Component({
  selector: 'app-toggle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="fila">
      <div class="texto">
        <h4 [id]="idEtiqueta">{{ label() }}</h4>
        @if (hint()) {
          <p class="pista">{{ hint() }}</p>
        }
      </div>
      <span class="sw-wrap">
        <span class="sw-state">{{ estado() }}</span>
        <button
          type="button"
          class="sw-btn"
          role="switch"
          [id]="fieldId()"
          [attr.aria-checked]="checked()"
          [attr.aria-labelledby]="idEtiqueta"
          [attr.aria-describedby]="describedBy()"
          [disabled]="disabled()"
          (click)="alternar()"
        >
          <span class="sw-btn__pomo" aria-hidden="true"></span>
        </button>
      </span>
    </div>
  `,
  styles: `
    .fila {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: var(--space-md);
      align-items: start;
    }
    .texto h4 {
      margin: 0 0 4px;
      font-size: var(--fs-body);
      font-weight: 500;
      color: var(--fg);
    }
    .pista {
      margin: 0;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .sw-wrap {
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 0 0 auto;
    }
    .sw-state {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      min-width: 4rem;
      text-align: right;
    }
    .sw-btn {
      width: 46px;
      height: 26px;
      flex: 0 0 auto;
      padding: 2px;
      border-radius: 13px;
      cursor: pointer;
      background-color: var(--surface-2);
      border: 1px solid var(--border-strong);
      transition:
        background-color 0.18s,
        border-color 0.18s;
    }
    .sw-btn__pomo {
      display: block;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background-color: var(--muted);
      transition:
        transform 0.18s,
        background-color 0.18s;
    }
    .sw-btn:hover:not(:disabled) {
      border-color: var(--faint);
    }
    .sw-btn[aria-checked='true'] {
      background-color: var(--accent-dim);
      border-color: var(--accent);
    }
    .sw-btn[aria-checked='true'] .sw-btn__pomo {
      transform: translateX(20px);
      background-color: var(--accent);
    }
    .sw-btn:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
  `,
})
export class Toggle {
  readonly label = input.required<string>();
  /** Estado textual junto al interruptor (p. ej. "Siempre", "No", "Sí"). */
  readonly estado = input.required<string>();
  readonly hint = input<string | null>(null);
  readonly disabled = input(false);
  readonly fieldId = input<string | null>(null);
  readonly describedBy = input<string | null>(null);
  readonly checked = model(false);

  protected readonly idEtiqueta = `toggle-etiqueta-${contadorDeInstancias++}`;

  protected alternar(): void {
    if (!this.disabled()) {
      this.checked.set(!this.checked());
    }
  }
}
