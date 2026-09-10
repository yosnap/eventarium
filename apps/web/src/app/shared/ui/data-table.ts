import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Panel } from './panel';

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
 * envoltorio accesible que la fase 5 usará). La referencia envuelve siempre la tabla
 * en `.panel` (eventarium.css:184, 258-267): aquí se reutiliza `<app-panel>` de
 * verdad en vez de duplicar su fondo/borde/radio a mano, y este componente solo
 * aporta la ranura de scroll horizontal, navegable por teclado (`tabindex="0"` +
 * `role="region"` + `aria-label`), que es lo que hace falta a 320 px sin recortar
 * columnas. Las cabeceras llevan rótulo mono en mayúsculas con tracking; las celdas
 * numéricas usan `font-variant-numeric: tabular-nums` alineadas a la derecha, para
 * que las cifras no bailen entre filas.
 */
@Component({
  selector: 'app-data-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <app-panel>
      <div
        class="ranura-scroll"
        tabindex="0"
        role="region"
        [attr.aria-label]="etiquetaEfectiva()"
      >
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
    </app-panel>
  `,
  styles: `
    /* Solo el comportamiento de scroll: el fondo/borde/radio de la referencia los
       aporta <app-panel>, que envuelve esta ranura. La tabla de dentro es
       transparente, así que no hace falta recortar esquinas aquí. */
    .ranura-scroll {
      overflow-x: auto;
    }
    .ranura-scroll:focus-visible {
      outline: 3px solid var(--accent);
      outline-offset: 2px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      /* Sin fondo propio: dentro de <app-panel>, el fondo lo da el panel. */
      background-color: transparent;
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
      /* padding:10px 14px (eventarium.css:261). */
      padding: 10px 14px;
      font-family: var(--font-mono);
      text-transform: uppercase;
      /* letter-spacing:.14em, no .08em (eventarium.css:262). */
      letter-spacing: 0.14em;
      font-size: var(--fs-label);
      font-weight: 400;
      color: var(--muted);
      /* border-bottom con --border, no --border-strong (eventarium.css:263). */
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    th.numerica {
      text-align: right;
    }
    /* :host ::ng-deep, no ::ng-deep a secas: sin el :host el selector compila sin
       atributo de encapsulación y sale como "td { … }" global, repintando cualquier
       otra tabla de la app en cuanto este componente se instancia una sola vez. */
    :host ::ng-deep td {
      /* padding:13px 14px (eventarium.css:265). */
      padding: 13px 14px;
      border-bottom: 1px solid var(--border);
      color: var(--fg);
    }
    :host ::ng-deep td.numerica {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    /* Realce de fila: la referencia usa --surface, no --surface-hi
       (eventarium.css:266) — literal, aunque no sea el mismo tono que el fondo del
       panel envolvente (--surface-2): en el tema oscuro actual --surface es
       19,13 % de luminosidad y --surface-2 es 16,84 %, así que la fila sí se
       distingue visualmente al pasar el ratón. */
    :host ::ng-deep tbody tr:hover td {
      background-color: var(--surface);
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
