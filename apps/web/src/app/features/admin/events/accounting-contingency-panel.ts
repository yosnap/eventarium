import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { Panel } from '../../../shared/ui/panel';
import { type BudgetLine, type ContingencyLine, euros, nombreDePartida } from './accounting-types';

interface LineaConsumo {
  readonly texto: string;
  readonly importeCents: number;
}

/**
 * Fondo de contingencia: un raíl con lo consumido a la izquierda y lo
 * disponible a la derecha —la proporción sale de las dos cifras reales, no
 * de un valor decorativo (`contabilidad-evento.html:60-69`)— y el desglose
 * de qué partida lo ha consumido y por cuánto.
 */
@Component({
  selector: 'app-accounting-contingency-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Panel],
  template: `
    <ng-container *transloco="let t">
      <app-panel>
        <div cabecera>
          <span class="rotulo-seccion">{{ t('admin.events.accounting.contingencia.titulo') }}</span>
        </div>

        <div class="panel-cuerpo">
          <p class="hint">{{ t('admin.events.accounting.contingencia.explicacion') }}</p>

          @if (fundCents() === null) {
            <p class="hint">{{ t('admin.events.accounting.contingencia.sinFondo') }}</p>
          } @else {
            <div
              class="rail"
              role="img"
              [attr.aria-label]="
                t('admin.events.accounting.contingencia.aria', {
                  consumido: euros(consumidoCents()),
                  fondo: euros(fundCents()!),
                  disponible: euros(disponibleCents() ?? 0),
                })
              "
            >
              <span class="rail-consumido" [style.width.%]="porcentajeConsumido()">
                <span>{{
                  t('admin.events.accounting.contingencia.consumidos', {
                    importe: euros(consumidoCents()),
                  })
                }}</span>
              </span>
              <span class="rail-libre" [style.width.%]="100 - porcentajeConsumido()">
                <span>{{
                  t('admin.events.accounting.contingencia.libres', {
                    importe: euros(disponibleCents() ?? 0),
                  })
                }}</span>
              </span>
            </div>

            <div class="linea">
              <span>{{
                t('admin.events.accounting.contingencia.dotacionInicial', {
                  porcentaje: porcentaje(),
                  total: euros(totalPresupuestadoCents()),
                })
              }}</span>
              <span class="num">{{ euros(fundCents()!) }} €</span>
            </div>
            @for (linea of desglose(); track linea.texto) {
              <div class="linea">
                <span>{{ linea.texto }}</span>
                <span class="num consumo">− {{ euros(linea.importeCents) }} €</span>
              </div>
            }
          }
        </div>

        @if (fundCents() !== null) {
          <div pie>
            <span>{{ t('admin.events.accounting.contingencia.disponibleAhora') }}</span>
            <strong>{{ disponibleCents() !== null ? euros(disponibleCents()!) + ' €' : '—' }}</strong>
          </div>
        }
      </app-panel>
    </ng-container>
  `,
  styles: `
    /* .cont__rail / .cont__used / .cont__free (contabilidad-evento.html:62-69). */
    .rail {
      display: flex;
      height: 26px;
      border: 1px solid var(--border-strong);
      border-radius: 3px;
      overflow: hidden;
      background-color: var(--bg);
      margin: var(--sp-4) 0 12px;
    }
    .rail-consumido {
      background-color: var(--warn-dim);
      border-right: 1px solid var(--warn);
      display: flex;
      align-items: center;
      padding: 0 10px;
    }
    .rail-libre {
      display: flex;
      align-items: center;
      padding: 0 10px;
    }
    .rail span {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.06em;
      white-space: nowrap;
    }
    .rail-consumido span {
      color: var(--warn);
    }
    .rail-libre span {
      color: var(--muted);
    }
    .linea {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: var(--sp-4);
      padding: 11px 0;
      border-bottom: 1px solid var(--border);
      font-size: var(--fs-sm);
    }
    .linea:last-of-type {
      border-bottom: 0;
    }
    .num {
      font-family: var(--font-mono);
      white-space: nowrap;
    }
    .consumo {
      color: var(--warn);
    }
    .hint {
      max-width: 70ch;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
  `,
})
export class AccountingContingencyPanel {
  readonly fundPercent = input.required<string>();
  readonly fundCents = input.required<number | null>();
  readonly consumidoCents = input.required<number>();
  readonly disponibleCents = input.required<number | null>();
  readonly totalPresupuestadoCents = input.required<number>();
  readonly porPartida = input.required<readonly ContingencyLine[]>();
  readonly lineas = input.required<readonly BudgetLine[]>();

  private readonly transloco = inject(TranslocoService);

  protected readonly euros = euros;

  protected readonly porcentaje = computed(() => this.fundPercent());

  protected readonly porcentajeConsumido = computed(() => {
    const fondo = this.fundCents();
    if (!fondo) {
      return 0;
    }
    return Math.max(0, Math.min(100, (this.consumidoCents() / fondo) * 100));
  });

  protected readonly desglose = computed<readonly LineaConsumo[]>(() => {
    const lineas = this.lineas();
    const etiquetaSinPartida = this.transloco.translate(
      'admin.events.accounting.partidas.sinPartida',
    );
    return this.porPartida()
      .filter((linea) => linea.exceso_cents > 0)
      .map((linea) => ({
        texto: this.transloco.translate('admin.events.accounting.contingencia.consumoDePartida', {
          nombre: nombreDePartida(lineas, linea.budget_line_id, etiquetaSinPartida),
          presupuesto: euros(linea.budgeted_cents),
          ejecutado: euros(linea.ejecutado_cents),
        }),
        importeCents: linea.exceso_cents,
      }));
  });
}
