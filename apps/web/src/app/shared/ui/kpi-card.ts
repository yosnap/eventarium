import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Tarjeta KPI: el número que abre una pantalla de panel.
 *
 * Réplica de `.kpi` del prototipo (`panel-organizador.html`): borde + radio +
 * superficie + `--sp-5`, rótulo mono arriba, valor en `--fs-metric` y descriptor
 * en `--fs-sm` muted. El tono semántico (`warn`, `accent`) colorea solo el valor
 * y nunca es el único portador de información: el rótulo y el descriptor dicen
 * lo que el número significa, con o sin color.
 */
@Component({
  selector: 'app-kpi-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="kpi">
      <span class="rotulo-seccion">{{ rotulo() }}</span>
      <div
        class="valor"
        [class.tono-warn]="tono() === 'warn'"
        [class.tono-accent]="tono() === 'accent'"
      >
        {{ valor() }}
      </div>
      @if (descriptor(); as texto) {
        <p class="descriptor">{{ texto }}</p>
      }
    </div>
  `,
  styles: `
    /* Sin esto, el host (sin \`display\` propio) sí se estira al alto de la fila
     * de la grid que lo contiene, pero el borde/fondo vive en \`.kpi\` por
     * dentro, que solo mide su contenido — así que dos tarjetas con distinto
     * número de líneas de descriptor se ven con alturas distintas pese a que
     * la grid ya las había igualado por debajo. */
    :host {
      display: block;
      height: 100%;
    }
    /* \`min-width: 0\`: sin esto el min-content del valor (una cifra mono sin
     * espacios, p. ej. «21.485.000,00») empujaba la tarjeta y la track de la
     * grid por encima de su \`minmax(… , 1fr)\`, ensanchando la fila de KPIs
     * y, en varios anchos, la página entera (informe 261002, H2).
     * \`container-type\`: habilita las consultas de contenedor que escalan el
     * valor según el ancho real de la tarjeta. */
    .kpi {
      box-sizing: border-box;
      height: 100%;
      min-width: 0;
      container-type: inline-size;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      padding: var(--sp-5);
    }
    .rotulo-seccion {
      display: block;
    }
    /* .kpi__v: mono, --fs-metric, line-height 1, tracking -0.02em (panel-organizador.html:25).
     * \`overflow-wrap\`: una cifra grande (sin espacios en su interior) nunca
     * debe ensanchar la tarjeta: si no cabe, rompe dentro de la caja en vez
     * de salirse. */
    .valor {
      font-family: var(--font-mono);
      font-size: var(--fs-metric);
      line-height: 1;
      letter-spacing: -0.02em;
      min-width: 0;
      overflow-wrap: break-word;
      /* El color semántico pinta solo el valor; la información no depende de él. */
      &.tono-warn {
        color: var(--warn);
      }
      &.tono-accent {
        color: var(--accent);
      }
    }
    /* --fs-metric (2–2.75rem) no cabe en una tarjeta de 4-6 columnas: con el
     * tamaño a la vista, «12.654,40 €» desbordaba la caja en todo escritorio
     * (informe 261002, H2). Se escala por el ancho real de la tarjeta, no por
     * el de la ventana. */
    @container (max-width: 239px) {
      .valor {
        font-size: 1.375rem;
      }
    }
    @container (max-width: 189px) {
      .valor {
        font-size: 1.125rem;
      }
    }
    /* .kpi__d: fs-sm muted, 8px por encima (panel-organizador.html:26). */
    .descriptor {
      font-size: var(--fs-sm);
      color: var(--muted);
      margin: 8px 0 0;
    }
  `,
})
export class KpiCard {
  /** Rótulo mono («Confirmadas», «Por aprobar»). */
  readonly rotulo = input.required<string>();
  /** Cifra ya formateada por quien la llama (unidades, moneda, %). */
  readonly valor = input.required<string>();
  /** Línea de contexto debajo del número; opcional. */
  readonly descriptor = input<string | null>(null);
  /** Tono semántico del valor; `null` = neutro. */
  readonly tono = input<'warn' | 'accent' | null>(null);
}
