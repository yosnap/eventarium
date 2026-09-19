import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { Panel } from '../../../shared/ui/panel';
import { type BudgetLine, type ContingencyLine, euros, nombreDePartida } from './accounting-types';

interface FilaPresupuesto {
  /** Identificador de trackeo: el id de la partida, o un fijado para la fila
   * «sin partida» — el nombre no sirve porque dos partidas pueden llamarse
   * igual y el `@for` exige claves únicas. */
  readonly id: string;
  readonly nombre: string;
  readonly presupuestadoCents: number;
  readonly ejecutadoCents: number;
  readonly sobrePresupuesto: boolean;
  readonly anchoPresupuestado: number;
  readonly anchoEjecutado: number;
  readonly porcentajeTexto: string;
  readonly ariaLabel: string;
}

/**
 * Presupuesto frente a ejecutado, partida a partida: dos barras en el mismo
 * raíl (`contabilidad-evento.html`) en vez de una sola — la referencia no
 * tiene aquí una tabla `<table>`, es una rejilla de filas `.part`. El raíl
 * compara por longitud, no solo por color: la partida que se ha pasado
 * cambia el color de la barra ejecutada, pero también reordena qué segmento
 * llega al 100 % (el ejecutado, no el presupuestado), así que la lectura
 * «se ha salido del raíl» funciona igual en blanco y negro.
 */
@Component({
  selector: 'app-accounting-budget-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Panel],
  template: `
    <ng-container *transloco="let t">
      <app-panel>
        <div cabecera>
          <span class="rotulo-seccion">{{ t('admin.events.accounting.partidas.titulo') }}</span>
          @if (numeroDePasadas() > 0) {
            <span class="hint despegado">
              @if (numeroDePasadas() === 1) {
                {{ t('admin.events.accounting.partidas.pasadaUna') }}
              } @else {
                {{ t('admin.events.accounting.partidas.pasadas', { n: numeroDePasadas() }) }}
              }
            </span>
          }
        </div>

        @if (filas().length === 0) {
          <p class="panel-cuerpo">{{ t('admin.events.accounting.partidas.sinDatos') }}</p>
        } @else {
          <div class="panel-cuerpo">
            <div class="parthead" aria-hidden="true">
              <span>{{ t('admin.events.accounting.partidas.columnaPartida') }}</span>
              <span>{{ t('admin.events.accounting.partidas.columnaComparacion') }}</span>
              <span>{{ t('admin.events.accounting.partidas.columnaPresupuesto') }}</span>
              <span>{{ t('admin.events.accounting.partidas.columnaEjecutado') }}</span>
              <span>{{ t('admin.events.accounting.partidas.columnaPorcentaje') }}</span>
            </div>

            @for (fila of filas(); track fila.id) {
              <div class="part" [class.sobre]="fila.sobrePresupuesto">
                <span>{{ fila.nombre }}</span>
                <span class="rail" role="img" [attr.aria-label]="fila.ariaLabel">
                  <span class="rail-pre" [style.width.%]="fila.anchoPresupuestado"></span>
                  <span
                    class="rail-eje"
                    [class.sobre]="fila.sobrePresupuesto"
                    [style.width.%]="fila.anchoEjecutado"
                  ></span>
                </span>
                <span class="num">{{ euros(fila.presupuestadoCents) }} €</span>
                <span class="num">{{ euros(fila.ejecutadoCents) }} €</span>
                <span class="num pct" [class.sobre]="fila.sobrePresupuesto">{{
                  fila.porcentajeTexto
                }}</span>
              </div>
            }

            <div class="leyenda">
              <span
                ><i class="muestra muestra-pre"></i
                >{{ t('admin.events.accounting.partidas.leyendaPresupuestado') }}</span
              >
              <span
                ><i class="muestra muestra-eje"></i
                >{{ t('admin.events.accounting.partidas.leyendaEjecutado') }}</span
              >
              <span
                ><i class="muestra muestra-sobre"></i
                >{{ t('admin.events.accounting.partidas.leyendaSobre') }}</span
              >
            </div>
          </div>
        }

        <span pie>{{ t('admin.events.accounting.partidas.totalPartidas') }}</span>
        <span pie
          >{{
            t('admin.events.accounting.partidas.totalValores', {
              presupuesto: euros(totalPresupuestadoCents()),
              ejecutado: euros(totalEjecutadoCents()),
            })
          }}
        </span>
      </app-panel>
    </ng-container>
  `,
  styles: `
    /* .parthead / .part / .part__rail / .part__pre / .part__eje
       (contabilidad-evento.html:32-46). */
    .parthead {
      display: grid;
      grid-template-columns: 12.5rem minmax(7.5rem, 1fr) 6.5rem 6.5rem 3.875rem;
      gap: var(--sp-4);
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }
    .parthead span {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .parthead span:nth-child(n + 3) {
      text-align: right;
    }
    .part {
      display: grid;
      grid-template-columns: 12.5rem minmax(7.5rem, 1fr) 6.5rem 6.5rem 3.875rem;
      gap: var(--sp-4);
      align-items: center;
      padding: 13px 0;
      border-bottom: 1px solid var(--border);
      font-size: var(--fs-sm);
    }
    .part:last-of-type {
      border-bottom: 0;
    }
    .rail {
      position: relative;
      height: 22px;
      border: 1px solid var(--border-strong);
      border-radius: 3px;
      background-color: var(--bg);
      overflow: hidden;
    }
    .rail-pre {
      position: absolute;
      inset: 0 auto 0 0;
      background-color: var(--surface-hi);
      border-right: 1px dashed var(--faint);
    }
    .rail-eje {
      position: absolute;
      left: 0;
      top: 4px;
      bottom: 4px;
      background-color: var(--muted);
      border-radius: 2px;
    }
    .rail-eje.sobre {
      background-color: var(--warn);
    }
    .num {
      font-family: var(--font-mono);
      text-align: right;
    }
    .pct {
      color: var(--muted);
    }
    .pct.sobre {
      color: var(--warn);
    }
    .leyenda {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-5);
      margin-top: var(--sp-5);
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .muestra {
      display: inline-block;
      width: 22px;
      height: 10px;
      border-radius: 2px;
      margin-right: 8px;
      vertical-align: -1px;
    }
    .muestra-pre {
      background-color: var(--surface-hi);
      border: 1px solid var(--faint);
    }
    .muestra-eje {
      background-color: var(--muted);
    }
    .muestra-sobre {
      background-color: var(--warn);
    }
    .hint {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .despegado {
      margin-left: auto;
    }
    /* Bajo 1040px, la referencia estrecha las columnas fijas antes de
       apilar (contabilidad-evento.html:95-98). */
    @media (max-width: 1040px) {
      .parthead,
      .part {
        grid-template-columns: 9.375rem minmax(5.5rem, 1fr) 5.5rem 5.5rem 3.375rem;
        gap: var(--sp-3);
      }
    }
    /* Bajo 860px, el raíl pasa a su propia fila y la columna «Comparación»
       de cabecera se oculta (contabilidad-evento.html:104-106). */
    @media (max-width: 860px) {
      .parthead,
      .part {
        grid-template-columns: 1fr 5.25rem 5.25rem 3.375rem;
      }
      .rail {
        grid-column: 1 / -1;
        order: 2;
      }
      .parthead span:nth-child(2) {
        display: none;
      }
    }
  `,
})
export class AccountingBudgetPanel {
  readonly porPartida = input.required<readonly ContingencyLine[]>();
  readonly lineas = input.required<readonly BudgetLine[]>();

  private readonly transloco = inject(TranslocoService);

  protected readonly euros = euros;

  protected readonly filas = computed<readonly FilaPresupuesto[]>(() => {
    const lineas = this.lineas();
    const etiquetaSinPartida = this.transloco.translate(
      'admin.events.accounting.partidas.sinPartida',
    );
    return this.porPartida().map((linea) => {
      const nombre = nombreDePartida(lineas, linea.budget_line_id, etiquetaSinPartida);
      const sobrePresupuesto = linea.exceso_cents > 0;
      const base = Math.max(linea.budgeted_cents, linea.ejecutado_cents, 1);
      const porcentaje =
        linea.budgeted_cents > 0
          ? Math.round((linea.ejecutado_cents / linea.budgeted_cents) * 100)
          : linea.ejecutado_cents > 0
            ? 100
            : 0;
      // Con presupuesto 0 no hay porcentaje que comunicar: el aria dice lo
      // mismo que ve la vista («—»), no un «100 %» que nadie ve.
      const ariaLabel =
        linea.budgeted_cents > 0
          ? this.transloco.translate(
              sobrePresupuesto
                ? 'admin.events.accounting.partidas.ariaSobre'
                : 'admin.events.accounting.partidas.aria',
              {
                nombre,
                ejecutado: euros(linea.ejecutado_cents),
                presupuesto: euros(linea.budgeted_cents),
                porcentaje,
              },
            )
          : this.transloco.translate('admin.events.accounting.partidas.ariaSinPresupuesto', {
              nombre,
              ejecutado: euros(linea.ejecutado_cents),
            });
      return {
        id: linea.budget_line_id ?? 'sin-partida',
        nombre,
        presupuestadoCents: linea.budgeted_cents,
        ejecutadoCents: linea.ejecutado_cents,
        sobrePresupuesto,
        anchoPresupuestado: (linea.budgeted_cents / base) * 100,
        anchoEjecutado: (linea.ejecutado_cents / base) * 100,
        porcentajeTexto: linea.budgeted_cents > 0 ? `${porcentaje} %` : '—',
        ariaLabel,
      };
    });
  });

  protected readonly numeroDePasadas = computed(
    () => this.porPartida().filter((linea) => linea.exceso_cents > 0).length,
  );

  protected readonly totalPresupuestadoCents = computed(() =>
    this.porPartida().reduce((acc, l) => acc + l.budgeted_cents, 0),
  );
  protected readonly totalEjecutadoCents = computed(() =>
    this.porPartida().reduce((acc, l) => acc + l.ejecutado_cents, 0),
  );
}
