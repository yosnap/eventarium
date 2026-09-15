import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { fechaRelativa } from '../../../shared/text/fecha-relativa';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { DataTable, type DataTableColumn } from '../../../shared/ui/data-table';
import { KpiCard } from '../../../shared/ui/kpi-card';
import { PageHeader } from '../../../shared/ui/page-header';
import { Panel } from '../../../shared/ui/panel';
import { AccountingBudgetPanel } from './accounting-budget-panel';
import { AccountingContingencyPanel } from './accounting-contingency-panel';
import { AccountingForecastPanel } from './accounting-forecast-panel';
import { AccountingMovementsPanel } from './accounting-movements-panel';
import {
  type BudgetLine,
  type BudgetSummary,
  type Expense,
  type IncomesView,
  euros,
} from './accounting-types';
import { ExpenseForm } from './expense-form';

interface KpiVisible {
  readonly rotulo: string;
  readonly valor: string;
  readonly descriptor: string | null;
  readonly tono: 'warn' | 'accent' | null;
}

/**
 * Panel de contabilidad de un evento: KPIs, presupuesto frente a ejecutado
 * por partida, fondo de contingencia, previsión de cierre, evolución
 * temporal, movimientos por pestañas y alta manual de gasto/partida — fiel
 * a `contabilidad-evento.html`, comparado campo a campo. Los cuatro paneles
 * mayores (presupuesto, contingencia, previsión, movimientos) viven en sus
 * propios componentes: reunirlos aquí habría dejado el fichero por encima
 * de las 1000 líneas.
 *
 * El bloque «Añadir gasto por documento» (OCR) queda deshabilitado con un
 * aviso: esa función no está implementada todavía y esta pantalla no
 * depende de ella para funcionar.
 */
@Component({
  selector: 'app-event-accounting',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    Alert,
    Button,
    DataTable,
    KpiCard,
    PageHeader,
    Panel,
    AccountingBudgetPanel,
    AccountingContingencyPanel,
    AccountingForecastPanel,
    AccountingMovementsPanel,
    ExpenseForm,
  ],
  template: `
    <ng-container *transloco="let t">
      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }
      @if (aviso(); as mensaje) {
        <p role="status" aria-live="polite">{{ mensaje }}</p>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (resumen(); as r) {
        <app-page-header [rotulo]="t('admin.events.accounting.rotulo')">
          {{
            saldo() >= 0
              ? t('admin.events.accounting.cabecera.positivoInicio')
              : t('admin.events.accounting.cabecera.negativoInicio')
          }}
          <span class="mark">{{
            t('admin.events.accounting.cabecera.saldoMarca', { saldo: euros(saldo()) })
          }}</span>
          <div acciones>
            <app-button variant="secundario" type="button" (pulsado)="exportar('csv')">
              {{ t('admin.events.accounting.exportarCsv') }}
            </app-button>
            <app-button variant="secundario" type="button" (pulsado)="exportar('pdf')">
              {{ t('admin.events.accounting.exportarPdf') }}
            </app-button>
          </div>
        </app-page-header>

        <div class="kpis" [attr.aria-label]="t('admin.events.accounting.kpis.titulo')">
          @for (kpi of kpis(); track kpi.rotulo) {
            <app-kpi-card
              [rotulo]="kpi.rotulo"
              [valor]="kpi.valor"
              [descriptor]="kpi.descriptor"
              [tono]="kpi.tono"
            />
          }
        </div>

        <app-accounting-budget-panel
          class="bloque"
          [porPartida]="r.por_partida"
          [lineas]="lineas()"
        />

        <app-accounting-contingency-panel
          class="bloque"
          [fundPercent]="r.contingency_fund_percent"
          [fundCents]="r.contingency_fund_cents"
          [consumidoCents]="r.consumido_contingencia_cents"
          [disponibleCents]="r.disponible_contingencia_cents"
          [totalPresupuestadoCents]="r.total_budgeted_cents"
          [porPartida]="r.por_partida"
          [lineas]="lineas()"
        />

        <app-accounting-forecast-panel
          class="bloque"
          [saldoCents]="saldo()"
          [cobradoCents]="totalCobrado()"
          [pagadoCents]="ejecutadoMetalico()"
        />

        <app-panel class="bloque">
          <div cabecera>
            <span class="rotulo-seccion">{{ t('admin.events.accounting.evolucion.titulo') }}</span>
          </div>
          @if (r.evolucion_temporal.length === 0) {
            <p class="panel-cuerpo">{{ t('admin.events.accounting.evolucion.sinDatos') }}</p>
          } @else {
            <app-data-table
              [columnas]="columnasDeEvolucion()"
              [caption]="t('admin.events.accounting.evolucion.titulo')"
            >
              @for (punto of r.evolucion_temporal; track punto.periodo) {
                <tr>
                  <td>{{ punto.periodo }}</td>
                  <td class="numerica">{{ euros(punto.ingresos_cents) }} €</td>
                  <td class="numerica">{{ euros(punto.gastos_cents) }} €</td>
                </tr>
              }
            </app-data-table>
          }
        </app-panel>

        <app-accounting-movements-panel
          class="bloque"
          [ingresosCombinados]="ingresosCombinados()"
          [gastosMetalico]="gastosMetalico()"
          [gastosEnEspecie]="gastosEnEspecie()"
          [lineas]="lineas()"
        />

        <app-panel class="bloque">
          <div cabecera>
            <span class="rotulo-seccion">{{ t('admin.events.accounting.altaPartida.titulo') }}</span>
          </div>
          <form (submit)="crearPartida($event)" novalidate class="panel-cuerpo formulario">
            <div class="campo">
              <label for="partida-nombre">{{
                t('admin.events.accounting.altaPartida.nombre')
              }}</label>
              <input
                id="partida-nombre"
                type="text"
                [value]="nombrePartidaNueva()"
                (input)="nombrePartidaNueva.set(alTexto($event))"
              />
            </div>
            <div class="campo">
              <label for="partida-importe">{{
                t('admin.events.accounting.altaPartida.importe')
              }}</label>
              <input
                id="partida-importe"
                type="number"
                min="0"
                step="0.01"
                [value]="importePartidaNueva()"
                (input)="importePartidaNueva.set(alTexto($event))"
              />
            </div>
            @if (errorPartida(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }
            <app-button type="submit" variant="secundario" [loading]="creandoPartida()">
              {{ t('admin.events.accounting.altaPartida.boton') }}
            </app-button>
          </form>
        </app-panel>

        <app-expense-form
          [eventId]="eventId()"
          [partidas]="lineasParaGasto()"
          (creado)="alCrearGasto($event)"
        />

        <app-alert tone="info">
          {{ t('admin.events.accounting.altaGasto.ocrDeshabilitado') }}
        </app-alert>
      }
    </ng-container>
  `,
  styles: `
    .bloque {
      display: block;
      margin-bottom: var(--sp-6);
    }
    .kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(11.125rem, 1fr));
      gap: var(--sp-4);
      margin-bottom: var(--sp-6);
    }
    .formulario {
      display: grid;
      gap: var(--space-sm);
      max-width: 28rem;
    }
    .campo {
      display: grid;
      gap: var(--space-xs);
    }
    .campo input {
      min-height: 2.5rem;
    }
  `,
})
export class EventAccounting implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly aviso = signal<string | null>(null);

  protected readonly resumen = signal<BudgetSummary | null>(null);
  protected readonly ingresos = signal<IncomesView | null>(null);
  protected readonly lineas = signal<readonly BudgetLine[]>([]);
  protected readonly gastos = signal<readonly Expense[]>([]);

  protected readonly nombrePartidaNueva = signal('');
  protected readonly importePartidaNueva = signal('');
  protected readonly creandoPartida = signal(false);
  protected readonly errorPartida = signal<string | null>(null);

  protected readonly euros = euros;

  protected readonly totalIngresos = computed(() => this.ingresos()?.total_ingresos_cents ?? 0);
  protected readonly totalComprometido = computed(() =>
    (this.ingresos()?.comprometido ?? []).reduce((acc, l) => acc + l.importe_cents, 0),
  );
  /** Ejecutado en metálico: KPI propio, separado del ejecutado en especie —
   * `por_partida` ya incluye la fila «sin partida», así que no se suma
   * `gasto_sin_partida_cents` aparte (contaría dos veces). */
  protected readonly ejecutadoMetalico = computed(() => {
    const r = this.resumen();
    return r ? r.por_partida.reduce((acc, l) => acc + l.ejecutado_cents, 0) : 0;
  });
  protected readonly ejecutadoTotal = computed(
    () => this.ejecutadoMetalico() + (this.resumen()?.ejecutado_en_especie_cents ?? 0),
  );
  /** Saldo de caja: ingresos (incluida la especie, cobrada desde que se
   * valora) menos todo lo ejecutado, en metálico y en especie — misma
   * fórmula que `service.saldo_cents` en el backend (`export.py`). */
  protected readonly saldo = computed(() => this.totalIngresos() - this.ejecutadoTotal());

  /** Lo efectivamente cobrado por el banco (no lo comprometido, no la
   * especie): la fila «Cobrado» de la foto de caja de la previsión de cierre.
   * Las valoraciones en especie cuentan como ingreso en el libro (mismo
   * importe como ingreso y como gasto), pero jamás pasan por el banco, así
   * que incluirlas aquí inflaría la caja. */
  protected readonly totalCobrado = computed(() =>
    (this.ingresos()?.ingresos ?? [])
      .filter((l) => !l.en_especie)
      .reduce((acc, l) => acc + l.importe_cents, 0),
  );

  protected readonly gastosMetalico = computed(() =>
    this.gastos().filter((g) => g.sponsor_id === null),
  );
  protected readonly gastosEnEspecie = computed(() =>
    this.gastos().filter((g) => g.sponsor_id !== null),
  );

  protected readonly ingresosCombinados = computed(() => {
    const vista = this.ingresos();
    if (!vista) {
      return [];
    }
    return [
      ...vista.ingresos.map((l) => ({ ...l, cobrado: true as const })),
      ...vista.comprometido.map((l) => ({ ...l, cobrado: false as const })),
    ];
  });

  protected readonly kpis = computed<readonly KpiVisible[]>(() => {
    const r = this.resumen();
    if (!r) {
      return [];
    }
    const t = (clave: string, params?: Record<string, unknown>) =>
      this.transloco.translate(clave, params);
    const pctEjecutado =
      r.total_budgeted_cents > 0
        ? Math.round((this.ejecutadoTotal() / r.total_budgeted_cents) * 100)
        : null;
    return [
      {
        rotulo: t('admin.events.accounting.kpis.presupuesto'),
        valor: `${euros(r.total_budgeted_cents)} €`,
        descriptor: r.budget_approved_at
          ? t('admin.events.accounting.kpis.presupuestoDescriptor', {
              fecha: fechaRelativa(r.budget_approved_at),
            })
          : null,
        tono: null,
      },
      {
        rotulo: t('admin.events.accounting.kpis.ejecutadoMetalico'),
        valor: `${euros(this.ejecutadoMetalico())} €`,
        descriptor: null,
        tono: null,
      },
      {
        rotulo: t('admin.events.accounting.kpis.ejecutadoEnEspecie'),
        valor: `${euros(r.ejecutado_en_especie_cents)} €`,
        descriptor: null,
        tono: null,
      },
      {
        rotulo: t('admin.events.accounting.kpis.ejecutadoTotal'),
        valor: `${euros(this.ejecutadoTotal())} €`,
        descriptor:
          pctEjecutado !== null
            ? t('admin.events.accounting.kpis.ejecutadoTotalDescriptor', { pct: pctEjecutado })
            : null,
        tono: pctEjecutado !== null && pctEjecutado > 100 ? 'warn' : null,
      },
      {
        rotulo: t('admin.events.accounting.kpis.ingresos'),
        valor: `${euros(this.totalIngresos())} €`,
        descriptor: null,
        tono: null,
      },
      {
        rotulo: t('admin.events.accounting.kpis.comprometido'),
        valor: `${euros(this.totalComprometido())} €`,
        descriptor: null,
        tono: null,
      },
      {
        rotulo: t('admin.events.accounting.kpis.saldo'),
        valor: euros(this.saldo()) + ' €',
        descriptor: t('admin.events.accounting.kpis.saldoDescriptor'),
        tono: this.saldo() >= 0 ? 'accent' : 'warn',
      },
      {
        rotulo: t('admin.events.accounting.kpis.contingencia'),
        valor:
          r.disponible_contingencia_cents !== null
            ? `${euros(r.disponible_contingencia_cents)} €`
            : '—',
        descriptor:
          r.contingency_fund_cents !== null
            ? t('admin.events.accounting.kpis.contingenciaDescriptor', {
                fondo: euros(r.contingency_fund_cents),
                consumido: euros(r.consumido_contingencia_cents),
              })
            : null,
        tono: r.disponible_contingencia_cents !== null && r.disponible_contingencia_cents <= 0
          ? 'warn'
          : null,
      },
    ];
  });

  protected readonly columnasDeEvolucion = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'periodo', label: t('admin.events.accounting.evolucion.columnaPeriodo') },
      {
        key: 'ingresos',
        label: t('admin.events.accounting.evolucion.columnaIngresos'),
        numerica: true,
      },
      {
        key: 'gastos',
        label: t('admin.events.accounting.evolucion.columnaGastos'),
        numerica: true,
      },
    ];
  });

  ngOnInit(): void {
    void this.cargar();
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement | HTMLSelectElement).value;
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set(null);
    try {
      const [resumen, ingresos, lineas, gastos] = await Promise.all([
        firstValueFrom(
          this.http.get<BudgetSummary>(
            this.api.url(`/accounting/events/${this.eventId()}/budget/summary`),
          ),
        ),
        firstValueFrom(
          this.http.get<IncomesView>(this.api.url(`/accounting/events/${this.eventId()}/incomes`)),
        ),
        firstValueFrom(
          this.http.get<BudgetLine[]>(
            this.api.url(`/accounting/events/${this.eventId()}/budget-lines`),
          ),
        ),
        firstValueFrom(
          this.http.get<Expense[]>(this.api.url(`/accounting/events/${this.eventId()}/expenses`)),
        ),
      ]);
      this.resumen.set(resumen);
      this.ingresos.set(ingresos);
      this.lineas.set([...lineas]);
      this.gastos.set([...gastos]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.accounting.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected async crearPartida(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    this.errorPartida.set(null);
    const nombre = this.nombrePartidaNueva().trim();
    const importeCents = Math.round(Number(this.importePartidaNueva().replace(',', '.')) * 100);
    if (!nombre) {
      this.errorPartida.set(
        this.transloco.translate('admin.events.accounting.altaPartida.nombreRequerido'),
      );
      return;
    }
    if (!Number.isFinite(importeCents) || importeCents < 0) {
      this.errorPartida.set(
        this.transloco.translate('admin.events.accounting.altaPartida.importeInvalido'),
      );
      return;
    }

    this.creandoPartida.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/accounting/events/${this.eventId()}/budget-lines`), {
          name: nombre,
          budgeted_cents: importeCents,
        }),
      );
      this.nombrePartidaNueva.set('');
      this.importePartidaNueva.set('');
      this.aviso.set(this.transloco.translate('admin.events.accounting.altaPartida.creada'));
      await this.cargar();
    } catch (error) {
      this.errorPartida.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.accounting.error'),
      );
    } finally {
      this.creandoPartida.set(false);
    }
  }

  /** Las partidas que el formulario de gasto puede ofrecer para imputar. */
  protected readonly lineasParaGasto = computed(() =>
    this.lineas().map((linea) => ({ id: linea.id, name: linea.name })),
  );

  /** El formulario ha creado un gasto: se avisa y se recargan las cifras. */
  protected async alCrearGasto(aviso: string): Promise<void> {
    this.aviso.set(aviso);
    await this.cargar();
  }

  protected async exportar(formato: 'csv' | 'pdf'): Promise<void> {
    this.error.set(null);
    try {
      const blob = await firstValueFrom(
        this.http.get(this.api.url(`/accounting/events/${this.eventId()}/export.${formato}`), {
          responseType: 'blob',
        }),
      );
      const url = URL.createObjectURL(blob);
      const enlace = document.createElement('a');
      enlace.href = url;
      enlace.download = `balance-${this.eventId()}.${formato}`;
      enlace.click();
      URL.revokeObjectURL(url);
      this.aviso.set(this.transloco.translate('admin.events.accounting.exportado'));
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.accounting.error'),
      );
    }
  }
}
