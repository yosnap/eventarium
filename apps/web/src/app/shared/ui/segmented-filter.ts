import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/**
 * Filtro segmentado: botones mono en mayúsculas dentro de un contenedor con
 * borde, uno de ellos activo con fondo de acento.
 *
 * Réplica de `.filters` del prototipo (`panel-organizador.html:23-27`). La
 * referencia no lo agrupa para lectores de pantalla; aquí sí: `role="group"`
 * con `aria-label` obligatorio, y cada botón lleva `aria-pressed` — el estado
 * activo se anuncia, no se deduce del color.
 */
@Component({
  selector: 'app-segmented-filter',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="filtros" role="group" [attr.aria-label]="etiqueta()">
      @for (opcion of opciones(); track opcion.valor) {
        <button
          type="button"
          [attr.aria-pressed]="valor() === opcion.valor"
          (click)="cambio.emit(opcion.valor)"
        >
          {{ opcion.etiqueta }}
        </button>
      }
    </div>
  `,
  styles: `
    /* En móvil el grupo entero no cabe (400-430 px con 3-4 opciones): se
       desplaza dentro de sí mismo en vez de ensanchar la página. */
    :host {
      display: block;
      max-width: 100%;
      min-width: 0;
    }
    .filtros {
      display: flex;
      gap: 4px;
      max-width: 100%;
      overflow-x: auto;
      scrollbar-width: none;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 3px;
      background-color: var(--bg);
    }
    button {
      flex-shrink: 0;
      white-space: nowrap;
      min-height: 32px;
      padding: 0 12px;
      border: 0;
      border-radius: 3px;
      background-color: transparent;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      cursor: pointer;
    }
    button:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
    button[aria-pressed='true'] {
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
    }
  `,
})
export class SegmentedFilter<T extends string> {
  /** Opciones visibles, en orden. */
  readonly opciones = input.required<readonly { valor: T; etiqueta: string }[]>();
  /** Valor activo. */
  readonly valor = input.required<T>();
  /** Nombre del grupo para lectores de pantalla (obligatorio). */
  readonly etiqueta = input.required<string>();

  readonly cambio = output<T>();
}
