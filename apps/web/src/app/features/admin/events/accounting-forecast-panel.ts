import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Panel } from '../../../shared/ui/panel';
import { euros, eurosConSigno } from './accounting-types';

/**
 * Previsión de cierre: el saldo contable de hoy, presentado como resultado,
 * más la foto de caja (cobrado / pagado / caja hoy) de
 * `contabilidad-evento.html:258-299`.
 *
 * La referencia además resta «comprometido pendiente de facturar» con
 * sub-líneas por partida — una estimación que solo existe en la demo. No hay
 * ninguna fuente de datos real para «qué queda por facturar» todavía (eso
 * necesitaría OCR o compromisos declarados a mano, ninguno de los dos
 * implementado), así que ese ajuste queda fuera: el panel muestra solo lo
 * que se puede derivar de verdad, y lo dice.
 */
@Component({
  selector: 'app-accounting-forecast-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Panel],
  template: `
    <ng-container *transloco="let t">
      <app-panel>
        <div cabecera>
          <span class="rotulo-seccion">{{ t('admin.events.accounting.prevision.titulo') }}</span>
        </div>

        <div class="panel-cuerpo">
          <div class="linea resultado">
            <strong>{{ t('admin.events.accounting.prevision.saldoHoy') }}</strong>
            <strong class="num" [class.negativo]="saldoCents() < 0">{{
              eurosConSigno(saldoCents())
            }}</strong>
          </div>
          <p class="hint">{{ t('admin.events.accounting.prevision.sinCompromisos') }}</p>

          <div class="caja">
            <div class="caja-item">
              <span class="rotulo-seccion">{{ t('admin.events.accounting.prevision.cobrado') }}</span>
              <div class="caja-valor">{{ euros(cobradoCents()) }} €</div>
            </div>
            <div class="caja-item">
              <span class="rotulo-seccion">{{ t('admin.events.accounting.prevision.pagado') }}</span>
              <div class="caja-valor">{{ euros(pagadoCents()) }} €</div>
            </div>
            <div class="caja-item">
              <span class="rotulo-seccion">{{ t('admin.events.accounting.prevision.cajaHoy') }}</span>
              <div class="caja-valor" [class.negativo]="cajaHoyCents() < 0">
                {{ eurosConSigno(cajaHoyCents()) }}
              </div>
            </div>
          </div>
        </div>
      </app-panel>
    </ng-container>
  `,
  styles: `
    .linea {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: var(--sp-4);
      align-items: baseline;
      font-size: var(--fs-sm);
    }
    /* .prev__lin--res (contabilidad-evento.html:79-80). */
    .resultado strong {
      font-family: var(--font-mono);
      font-size: 1.15rem;
    }
    .num {
      font-family: var(--font-mono);
      white-space: nowrap;
    }
    .negativo {
      color: var(--warn);
    }
    .hint {
      margin: var(--sp-3) 0 0;
      max-width: 70ch;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .caja {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(12.5rem, 1fr));
      gap: var(--sp-4);
      margin-top: var(--sp-5);
    }
    .caja-item {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
      padding: var(--sp-4) var(--sp-5);
    }
    .caja-valor {
      font-family: var(--font-mono);
      font-size: 1.35rem;
      margin-top: 6px;
    }
  `,
})
export class AccountingForecastPanel {
  readonly saldoCents = input.required<number>();
  readonly cobradoCents = input.required<number>();
  readonly pagadoCents = input.required<number>();

  protected readonly euros = euros;
  protected readonly eurosConSigno = eurosConSigno;

  protected readonly cajaHoyCents = computed(() => this.cobradoCents() - this.pagadoCents());
}
