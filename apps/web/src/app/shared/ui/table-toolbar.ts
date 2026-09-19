import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

/**
 * Barra de herramientas de tabla: búsqueda y filtros como grupo de cabecera.
 *
 * Réplica de `.toolbar` + `.search` del prototipo (`panel-organizador.html:22-33`):
 * búsqueda y filtros como un grupo único, con `margin-left: auto` para que, dentro
 * de la cabecera de un panel (`[cabecera]`, junto al rótulo), quede empujado a la
 * derecha — exactamente como la referencia. La búsqueda es `model()`: quien la usa
 * decide si filtra en cliente o consulta a la API por cada pulsación.
 */
@Component({
  selector: 'app-table-toolbar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toolbar">
      <input
        type="search"
        class="busqueda"
        [attr.placeholder]="placeholderBusqueda()"
        [attr.aria-label]="placeholderBusqueda()"
        [value]="busqueda()"
        (input)="busqueda.set(alTexto($event))"
      />
      <div class="resto">
        <ng-content />
      </div>
    </div>
  `,
  styles: `
    /* .toolbar (panel-organizador.html:31): el grupo entero se pega a la
       derecha cuando comparte fila con el rótulo del panel. */
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-3);
      align-items: center;
      margin-left: auto;
    }
    /* .search (panel-organizador.html:32-34): 36px, fondo --bg, borde fuerte. */
    .busqueda {
      min-height: 36px;
      max-width: 230px;
      padding: 0 12px;
      background-color: var(--bg);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      color: var(--fg);
      font-size: var(--fs-sm);
    }
    .busqueda:focus {
      border-color: var(--accent);
      outline: none;
    }
    .resto {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-3);
      align-items: center;
    }
    .resto:empty {
      display: none;
    }
  `,
})
export class TableToolbar {
  /** Texto de búsqueda, en doble enlace con quien filtra. */
  readonly busqueda = model('');
  /** Marca de la búsqueda; sirve de placeholder y de etiqueta accesible. */
  readonly placeholderBusqueda = input.required<string>();

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }
}
