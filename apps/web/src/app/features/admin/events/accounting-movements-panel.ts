import { SlicePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  type ElementRef,
  computed,
  inject,
  input,
  signal,
  viewChildren,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { Chip } from '../../../shared/ui/chip';
import { DataTable, type DataTableColumn } from '../../../shared/ui/data-table';
import { Panel } from '../../../shared/ui/panel';
import {
  type BudgetLine,
  type Expense,
  type IngresoCombinado,
  euros,
  nombreDePartida,
} from './accounting-types';

type Movimiento = 'ingresos' | 'gastos' | 'especie';

/** Orden fijo del `tablist` de movimientos — roving tabindex + flechas
 * izquierda/derecha entre estos tres, mismo patrón que
 * `event-agenda-section.ts`/`event-venues-page.ts` (WCAG 2.1.1). */
const MOVIMIENTOS: readonly Movimiento[] = ['ingresos', 'gastos', 'especie'];

const CLAVE_PESTANA: Record<Movimiento, string> = {
  ingresos: 'admin.events.accounting.movimientos.pestanaIngresos',
  gastos: 'admin.events.accounting.movimientos.pestanaGastos',
  especie: 'admin.events.accounting.movimientos.pestanaEspecie',
};

/**
 * Movimientos del libro: ingresos, gastos y aportaciones en especie, cada
 * uno en su propia pestaña con `app-data-table` y un pie de totales
 * (`.tot`, `contabilidad-evento.html:303-405`). Las tres pestañas siguen en
 * el DOM a la vez (ocultas con `[hidden]`), no condicionadas con `@if`: es
 * lo que permite que las tres tengan `id` estable para `aria-controls`.
 */
@Component({
  selector: 'app-accounting-movements-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Chip, DataTable, Panel, SlicePipe],
  template: `
    <ng-container *transloco="let t">
      <app-panel>
        <div cabecera>
          <span class="rotulo-seccion">{{ t('admin.events.accounting.movimientos.titulo') }}</span>
          <div
            role="tablist"
            [attr.aria-label]="t('admin.events.accounting.movimientos.titulo')"
            class="tabs"
          >
            @for (movimiento of MOVIMIENTOS; track movimiento; let indice = $index) {
              <button
                #pestanaBoton
                role="tab"
                type="button"
                [id]="'movimiento-tab-' + movimiento"
                [attr.aria-selected]="pestana() === movimiento"
                [attr.aria-controls]="'movimiento-panel-' + movimiento"
                [tabIndex]="pestana() === movimiento ? 0 : -1"
                (click)="seleccionarPestana(movimiento, false)"
                (keydown)="alPulsarTeclaPestana($event, indice)"
              >
                {{ t(claveEtiquetaPestana(movimiento)) }}
              </button>
            }
          </div>
        </div>

        <div class="panel-cuerpo">
          <div
            role="tabpanel"
            id="movimiento-panel-ingresos"
            [attr.aria-labelledby]="'movimiento-tab-ingresos'"
            [hidden]="pestana() !== 'ingresos'"
          >
            <app-data-table
              [columnas]="columnasDeIngresos()"
              [caption]="t('admin.events.accounting.movimientos.pestanaIngresos')"
            >
              @for (linea of ingresosCombinados(); track linea.referencia_id + linea.cobrado) {
                <tr>
                  <td>{{ t('admin.events.accounting.origen.' + linea.origen) }}</td>
                  <td>{{ linea.concepto }}</td>
                  <td>{{ linea.fecha ? (linea.fecha | slice: 0 : 10) : '—' }}</td>
                  <td>
                    <app-chip [tone]="linea.cobrado ? 'ok' : 'espera'">
                      {{
                        t(
                          linea.cobrado
                            ? 'admin.events.accounting.movimientos.estadoCobrado'
                            : 'admin.events.accounting.movimientos.estadoComprometido'
                        )
                      }}
                    </app-chip>
                  </td>
                  <td class="numerica">{{ euros(linea.importe_cents) }} €</td>
                </tr>
              }
              <span pie>{{ t('admin.events.accounting.movimientos.totalIngresos') }}</span>
              <strong pie>{{ euros(totalIngresosCents()) }} €</strong>
            </app-data-table>
          </div>

          <div
            role="tabpanel"
            id="movimiento-panel-gastos"
            [attr.aria-labelledby]="'movimiento-tab-gastos'"
            [hidden]="pestana() !== 'gastos'"
          >
            <app-data-table
              [columnas]="columnasDeGastos()"
              [caption]="t('admin.events.accounting.movimientos.pestanaGastos')"
            >
              @for (gasto of gastosMetalico(); track gasto.id) {
                <tr>
                  <td>{{ gasto.provider_name }}</td>
                  <td>{{ nombrePartida(gasto.budget_line_id) }}</td>
                  <td>{{ gasto.expense_date | slice: 0 : 10 }}</td>
                  <td class="numerica">{{ euros(gasto.base_cents) }} €</td>
                  <td class="numerica">
                    {{
                      gasto.vat_cents !== null
                        ? euros(gasto.vat_cents) + ' €'
                        : t('admin.events.accounting.movimientos.exento')
                    }}
                  </td>
                  <td class="numerica">{{ euros(gasto.total_cents) }} €</td>
                </tr>
              }
              <span pie>{{ t('admin.events.accounting.movimientos.totalGastos') }}</span>
              <strong pie>{{ euros(totalGastosMetalicoCents()) }} €</strong>
            </app-data-table>
          </div>

          <div
            role="tabpanel"
            id="movimiento-panel-especie"
            [attr.aria-labelledby]="'movimiento-tab-especie'"
            [hidden]="pestana() !== 'especie'"
          >
            <p class="hint">{{ t('admin.events.accounting.movimientos.explicacionEspecie') }}</p>
            <app-data-table
              [columnas]="columnasDeEspecie()"
              [caption]="t('admin.events.accounting.movimientos.pestanaEspecie')"
            >
              @for (gasto of gastosEnEspecie(); track gasto.id) {
                <tr>
                  <td>{{ gasto.provider_name }}</td>
                  <td>{{ nombrePartida(gasto.budget_line_id) }}</td>
                  <td class="numerica">{{ euros(gasto.total_cents) }} €</td>
                </tr>
              }
              <span pie>{{ t('admin.events.accounting.movimientos.totalEspecie') }}</span>
              <strong pie>{{ euros(totalEspecieCents()) }} €</strong>
            </app-data-table>
          </div>
        </div>
      </app-panel>
    </ng-container>
  `,
  styles: `
    /* .tabs (contabilidad-evento.html:50-55): contenedor bordeado con
       botones mono en mayúsculas, no botones sueltos. */
    .tabs {
      display: flex;
      gap: 4px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 4px;
      background-color: var(--surface-2);
      margin-left: auto;
    }
    .tabs button {
      min-height: 36px;
      padding: 0 14px;
      border: 0;
      border-radius: 3px;
      background-color: transparent;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.11em;
      text-transform: uppercase;
      cursor: pointer;
    }
    .tabs button:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
    .tabs button[aria-selected='true'] {
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
    }
    .hint {
      max-width: 70ch;
      color: var(--muted);
      font-size: var(--fs-sm);
      margin: 0 0 var(--sp-4);
    }
  `,
})
export class AccountingMovementsPanel {
  readonly ingresosCombinados = input.required<readonly IngresoCombinado[]>();
  readonly gastosMetalico = input.required<readonly Expense[]>();
  readonly gastosEnEspecie = input.required<readonly Expense[]>();
  readonly lineas = input.required<readonly BudgetLine[]>();

  private readonly transloco = inject(TranslocoService);
  private readonly botonesPestana = viewChildren<ElementRef<HTMLButtonElement>>('pestanaBoton');

  protected readonly MOVIMIENTOS = MOVIMIENTOS;
  protected readonly pestana = signal<Movimiento>('ingresos');
  protected readonly euros = euros;

  protected readonly totalIngresosCents = computed(() =>
    this.ingresosCombinados().reduce((acc, l) => acc + l.importe_cents, 0),
  );
  protected readonly totalGastosMetalicoCents = computed(() =>
    this.gastosMetalico().reduce((acc, g) => acc + g.total_cents, 0),
  );
  protected readonly totalEspecieCents = computed(() =>
    this.gastosEnEspecie().reduce((acc, g) => acc + g.total_cents, 0),
  );

  protected readonly columnasDeIngresos = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'origen', label: t('admin.events.accounting.movimientos.columnaOrigen') },
      { key: 'concepto', label: t('admin.events.accounting.movimientos.columnaConcepto') },
      { key: 'fecha', label: t('admin.events.accounting.movimientos.columnaFecha') },
      { key: 'estado', label: t('admin.events.accounting.movimientos.columnaEstado') },
      {
        key: 'importe',
        label: t('admin.events.accounting.movimientos.columnaImporte'),
        numerica: true,
      },
    ];
  });

  protected readonly columnasDeGastos = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'proveedor', label: t('admin.events.accounting.movimientos.columnaProveedor') },
      { key: 'partida', label: t('admin.events.accounting.partidas.columnaPartida') },
      { key: 'fecha', label: t('admin.events.accounting.movimientos.columnaFecha') },
      { key: 'base', label: t('admin.events.accounting.movimientos.columnaBase'), numerica: true },
      { key: 'iva', label: t('admin.events.accounting.movimientos.columnaIva'), numerica: true },
      {
        key: 'total',
        label: t('admin.events.accounting.movimientos.columnaTotal'),
        numerica: true,
      },
    ];
  });

  protected readonly columnasDeEspecie = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'proveedor', label: t('admin.events.accounting.movimientos.columnaProveedor') },
      { key: 'partida', label: t('admin.events.accounting.partidas.columnaPartida') },
      {
        key: 'total',
        label: t('admin.events.accounting.movimientos.columnaTotal'),
        numerica: true,
      },
    ];
  });

  protected nombrePartida(budgetLineId: string | null): string {
    return nombreDePartida(
      this.lineas(),
      budgetLineId,
      this.transloco.translate('admin.events.accounting.partidas.sinPartida'),
    );
  }

  protected claveEtiquetaPestana(movimiento: Movimiento): string {
    return CLAVE_PESTANA[movimiento];
  }

  protected seleccionarPestana(movimiento: Movimiento, enfocar: boolean): void {
    this.pestana.set(movimiento);
    if (enfocar) {
      const indice = MOVIMIENTOS.indexOf(movimiento);
      this.botonesPestana()[indice]?.nativeElement.focus();
    }
  }

  /** Roving tabindex del `tablist` (WCAG 2.1.1): flechas izquierda/derecha
   * mueven el foco y activan la pestaña siguiente/anterior, con vuelta al
   * principio/final. */
  protected alPulsarTeclaPestana(evento: KeyboardEvent, indice: number): void {
    const total = MOVIMIENTOS.length;
    let siguiente: number | null = null;
    if (evento.key === 'ArrowRight') {
      siguiente = (indice + 1) % total;
    } else if (evento.key === 'ArrowLeft') {
      siguiente = (indice - 1 + total) % total;
    }
    if (siguiente !== null) {
      evento.preventDefault();
      this.seleccionarPestana(MOVIMIENTOS[siguiente], true);
    }
  }
}
