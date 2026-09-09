import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Una columna de la tabla. `numerica` alinea a la derecha y activa cifras tabulares. */
export interface DataTableColumn {
  readonly key: string;
  readonly label: string;
  readonly numerica?: boolean;
}

/**
 * Envoltorio de una tabla de datos real, no una tabla decorativa.
 *
 * El contenido de cada celda se proyecta con `<ng-content>` desde quien consume el
 * componente (esta fase no migra ninguna de las 5 tablas existentes, solo aporta el
 * envoltorio accesible que la fase 5 usará). El contenedor de scroll horizontal es
 * navegable por teclado (`tabindex="0"` + `role="region"` + `aria-label`), que es lo
 * que hace falta a 320 px sin recortar columnas. Las cabeceras llevan rótulo mono en
 * mayúsculas con tracking; las celdas numéricas usan `font-variant-numeric:
 * tabular-nums` alineadas a la derecha, para que las cifras no bailen entre filas.
 */
@Component({
  selector: 'app-data-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="contenedor" tabindex="0" role="region" [attr.aria-label]="etiquetaEfectiva()">
      <table>
        <caption>
          {{ caption() }}
        </caption>
        <thead>
          <tr>
            @for (columna of columnas(); track columna.key) {
              <th scope="col" [class.numerica]="columna.numerica">{{ columna.label }}</th>
            }
          </tr>
        </thead>
        <tbody>
          <ng-content />
        </tbody>
      </table>
    </div>
  `,
  styles: `
    .contenedor {
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
    .contenedor:focus-visible {
      outline: 3px solid var(--accent);
      outline-offset: 2px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background-color: var(--surface);
    }
    caption {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }
    th {
      text-align: left;
      padding: var(--space-sm) var(--space-md);
      font-family: var(--font-mono);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.75rem;
      color: var(--muted);
      border-bottom: 1px solid var(--border-strong);
      white-space: nowrap;
    }
    th.numerica {
      text-align: right;
    }
    /* :host ::ng-deep, no ::ng-deep a secas: sin el :host el selector compila sin
       atributo de encapsulación y sale como "td { … }" global, repintando cualquier
       otra tabla de la app en cuanto este componente se instancia una sola vez. */
    :host ::ng-deep td {
      padding: var(--space-sm) var(--space-md);
      border-bottom: 1px solid var(--border);
      color: var(--fg);
    }
    :host ::ng-deep td.numerica {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    /* Realce de fila sin reducir el contraste del texto: solo cambia el fondo. */
    :host ::ng-deep tbody tr:hover td {
      background-color: var(--surface-hi);
    }
    :host ::ng-deep tbody tr:last-child td {
      border-bottom: none;
    }
  `,
})
export class DataTable {
  readonly caption = input.required<string>();
  readonly columnas = input.required<readonly DataTableColumn[]>();
  /** Nombre accesible del contenedor de scroll; por defecto reutiliza el `caption`. */
  readonly etiqueta = input<string>('');

  protected etiquetaEfectiva(): string {
    return this.etiqueta() || this.caption();
  }
}
