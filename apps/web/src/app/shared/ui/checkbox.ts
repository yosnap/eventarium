import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

/**
 * Casilla de verificación con etiqueta y pista opcional, sobre `.check` de la
 * referencia (`eventarium.css:255-256`): `accent-color` en vez de un control
 * pintado a mano, así que respeta el tema del sistema/navegador sin CSS
 * propio para las marcas de verificación.
 *
 * Antes de este componente, cada pantalla reimplementaba su propia etiqueta
 * con clases locales (`.opcion`, `.consentimiento`…) y un `<input>` sin
 * ningún estilo — de ahí la falta de consistencia entre pantallas.
 */
@Component({
  selector: 'app-checkbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="check">
      <input
        type="checkbox"
        [id]="fieldId()"
        [checked]="checked()"
        [disabled]="disabled()"
        [attr.aria-describedby]="describedBy()"
        (change)="alCambiar($event)"
      />
      <span>
        {{ label() }}
        @if (hint()) {
          <span class="pista">{{ hint() }}</span>
        }
      </span>
    </label>
  `,
  styles: `
    .check {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      font-size: var(--fs-sm);
      line-height: 1.5;
      color: var(--fg);
    }
    input {
      margin: 3px 0 0;
      width: 18px;
      height: 18px;
      accent-color: var(--accent);
      flex: 0 0 auto;
    }
    .pista {
      display: block;
      color: var(--muted);
    }
  `,
})
export class Checkbox {
  readonly label = input.required<string>();
  readonly hint = input<string | null>(null);
  readonly disabled = input(false);
  /** Id del `<input>` real, para enlazar desde un ancla externa (p. ej.
   * `app-error-summary`) — se pasa como `[fieldId]`, nunca como `id` del
   * host: un `id` en `<app-checkbox>` no apuntaría al control real. */
  readonly fieldId = input<string | null>(null);
  /** Id de un elemento externo (p. ej. el `<p>` de error) que describe este
   * campo, para `aria-describedby` — mismo patrón que `Input`/`Textarea`. */
  readonly describedBy = input<string | null>(null);
  readonly checked = model(false);

  protected alCambiar(evento: Event): void {
    this.checked.set((evento.target as HTMLInputElement).checked);
  }
}
