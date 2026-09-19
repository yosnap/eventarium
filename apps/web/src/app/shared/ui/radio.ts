import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

/**
 * Grupo de opciones excluyentes, sobre la misma base que `Checkbox`
 * (`accent-color` del sistema, sin control pintado a mano) y la misma
 * semántica de `SegmentedFilter` (lista de opciones, valor en modelo) pero
 * con la apariencia de radio: para elegir UNA entre varias cuando se ven
 * las opciones juntas con su texto largo, no como filtro compacto.
 */
@Component({
  selector: 'app-radio-group',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <fieldset class="grupo">
      <legend>{{ etiqueta() }}</legend>
      @for (opcion of opciones(); track opcion.valor) {
        <label class="opcion">
          <input
            type="radio"
            [name]="nombre()"
            [value]="opcion.valor"
            [checked]="valor() === opcion.valor"
            [disabled]="disabled()"
            (change)="valor.set(opcion.valor)"
          />
          <span>{{ opcion.etiqueta }}</span>
        </label>
      }
    </fieldset>
  `,
  styles: `
    .grupo {
      display: grid;
      gap: var(--space-sm);
      margin: 0;
      padding: var(--space-md);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
    legend {
      padding: 0 var(--space-xs);
    }
    .opcion {
      display: flex;
      gap: 10px;
      align-items: center;
      font-size: var(--fs-sm);
      line-height: 1.5;
      color: var(--fg);
      cursor: pointer;
    }
    input {
      margin: 0;
      width: 18px;
      height: 18px;
      accent-color: var(--accent);
      flex: 0 0 auto;
    }
  `,
})
export class RadioGroup<T extends string> {
  /** Rótulo del grupo (`<legend>`, obligatorio: agrupa y nombra). */
  readonly etiqueta = input.required<string>();
  /** Nombre compartido por los radios del grupo (exclusión nativa). */
  readonly nombre = input.required<string>();
  readonly opciones = input.required<readonly { valor: T; etiqueta: string }[]>();
  /** La opción elegida, en doble enlace con quien la usa. */
  readonly valor = model.required<T>();
  readonly disabled = input(false);
}
