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
    .kpi {
      box-sizing: border-box;
      height: 100%;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      padding: var(--sp-5);
    }
    .rotulo-seccion {
      display: block;
    }
    /* .kpi__v: mono, --fs-metric, line-height 1, tracking -0.02em (panel-organizador.html:25). */
    .valor {
      font-family: var(--font-mono);
      font-size: var(--fs-metric);
      line-height: 1;
      letter-spacing: -0.02em;
      /* El color semántico pinta solo el valor; la información no depende de él. */
      &.tono-warn {
        color: var(--warn);
      }
      &.tono-accent {
        color: var(--accent);
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
