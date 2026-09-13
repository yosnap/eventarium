import { SlicePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type ElementRef,
  type OnInit,
  computed,
  inject,
  input,
  signal,
  viewChildren,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ExpenseForm } from './expense-form';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Chip } from '../../../shared/ui/chip';

type Movimiento = 'ingresos' | 'gastos' | 'especie';

/** Orden fijo del `tablist` de movimientos — roving tabindex + flechas
 * izquierda/derecha entre estos tres, mismo patrón que
 * `event-agenda-section.ts`/`event-venues-page.ts` (WCAG 2.1.1, hallazgo
 * Alto A4 del code review de la fase 5: antes solo el `click` cambiaba de
 * pestaña, dejando dos de las tres inalcanzables por teclado). */
const MOVIMIENTOS: readonly Movimiento[] = ['ingresos', 'gastos', 'especie'];

const CLAVE_PESTANA: Record<Movimiento, string> = {
  ingresos: 'admin.events.accounting.movimientos.pestanaIngresos',
  gastos: 'admin.events.accounting.movimientos.pestanaGastos',
  especie: 'admin.events.accounting.movimientos.pestanaEspecie',
};

interface ContingencyLine {
  readonly budget_line_id: string | null;
  readonly ejecutado_cents: number;
  readonly budgeted_cents: number;
  readonly exceso_cents: number;
}

interface TimeSeriesPoint {
  readonly periodo: string;
  readonly ingresos_cents: number;
  readonly gastos_cents: number;
}

interface BudgetSummary {
  readonly event_id: string;
  readonly budget_approved_at: string | null;
  readonly total_budgeted_cents: number;
  readonly contingency_fund_percent: string;
  readonly contingency_fund_cents: number | null;
  readonly consumido_contingencia_cents: number;
  readonly disponible_contingencia_cents: number | null;
  readonly gasto_sin_partida_cents: number;
  readonly ejecutado_en_especie_cents: number;
  readonly por_partida: readonly ContingencyLine[];
  readonly evolucion_temporal: readonly TimeSeriesPoint[];
}

interface IncomeLine {
  readonly origen: 'patrocinio' | 'entradas' | 'subvencion';
  readonly concepto: string;
  readonly importe_cents: number;
  readonly fecha: string | null;
  readonly referencia_id: string;
}

interface IncomesView {
  readonly ingresos: readonly IncomeLine[];
  readonly comprometido: readonly IncomeLine[];
  readonly total_ingresos_cents: number;
  readonly moneda: string;
}

interface BudgetLine {
  readonly id: string;
  readonly event_id: string;
  readonly name: string;
  readonly budgeted_cents: number;
  readonly sort_order: number;
}

interface Expense {
  readonly id: string;
  readonly event_id: string;
  readonly budget_line_id: string | null;
  readonly sponsor_id: string | null;
  readonly provider_name: string;
  readonly expense_date: string;
  readonly base_cents: number;
  readonly vat_cents: number | null;
  readonly total_cents: number;
}

function euros(cents: number): string {
  return (cents / 100).toFixed(2);
}

/**
 * Panel de contabilidad de un evento (PRD fase 7, fase 5 de trabajo): KPIs,
 * presupuesto frente a ejecutado por partida (con «Sin partida»), fondo de
 * contingencia, evolución temporal, movimientos por pestañas y alta manual
 * de gasto/partida. Fiel campo a campo a `contabilidad-evento.html`
 * (comparación documentada en el report de cierre de la fase, no aquí).
 *
 * El bloque «Añadir gasto por documento» (OCR, fase 4 del plan) queda
 * deshabilitado con un aviso: esa fase no está implementada todavía y esta
 * pantalla no depende de ella para cerrarse (plan.md, Fase 5: "el flujo de
 * OCR se integra... sin reabrir esta fase para ello").
 */
@Component({
  selector: 'app-event-accounting',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Chip, ExpenseForm, SlicePipe],
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
        <div class="cabecera">
          <h2>{{ t('admin.events.accounting.titulo') }}</h2>
          <div class="acciones-exportar">
            <app-button variant="secundario" type="button" (pulsado)="exportar('csv')">
              {{ t('admin.events.accounting.exportarCsv') }}
            </app-button>
            <app-button variant="secundario" type="button" (pulsado)="exportar('pdf')">
              {{ t('admin.events.accounting.exportarPdf') }}
            </app-button>
          </div>
        </div>

        <section class="kpis" aria-label="{{ t('admin.events.accounting.kpis.titulo') }}">
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.presupuesto') }}</div>
            <div class="valor">{{ euros(r.total_budgeted_cents) }} €</div>
          </div>
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.ejecutadoMetalico') }}</div>
            <div class="valor">{{ euros(ejecutadoMetalico()) }} €</div>
          </div>
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.ejecutadoEnEspecie') }}</div>
            <div class="valor">{{ euros(r.ejecutado_en_especie_cents) }} €</div>
          </div>
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.ejecutadoTotal') }}</div>
            <div class="valor">{{ euros(ejecutadoTotal()) }} €</div>
          </div>
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.ingresos') }}</div>
            <div class="valor">{{ euros(totalIngresos()) }} €</div>
          </div>
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.comprometido') }}</div>
            <div class="valor">{{ euros(totalComprometido()) }} €</div>
          </div>
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.saldo') }}</div>
            <div class="valor" [class.positivo]="saldo() >= 0" [class.negativo]="saldo() < 0">
              {{ saldo() >= 0 ? '+' : '' }}{{ euros(saldo()) }} €
            </div>
          </div>
          <div class="kpi">
            <div class="etiqueta">{{ t('admin.events.accounting.kpis.contingencia') }}</div>
            <div class="valor">
              {{
                r.disponible_contingencia_cents !== null
                  ? euros(r.disponible_contingencia_cents) + ' €'
                  : '—'
              }}
            </div>
          </div>
        </section>

        <app-card [heading]="t('admin.events.accounting.partidas.titulo')">
          @if (r.por_partida.length === 0) {
            <p>{{ t('admin.events.accounting.partidas.sinDatos') }}</p>
          } @else {
            <table>
              <caption class="sr-only">
                {{
                  t('admin.events.accounting.partidas.titulo')
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">{{ t('admin.events.accounting.partidas.columnaPartida') }}</th>
                  <th scope="col">
                    {{ t('admin.events.accounting.partidas.columnaPresupuesto') }}
                  </th>
                  <th scope="col">{{ t('admin.events.accounting.partidas.columnaEjecutado') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.partidas.columnaPorcentaje') }}</th>
                </tr>
              </thead>
              <tbody>
                @for (linea of r.por_partida; track linea.budget_line_id ?? 'sin-partida') {
                  <tr [class.sobre]="linea.exceso_cents > 0">
                    <td>{{ nombrePartida(linea.budget_line_id) }}</td>
                    <td>{{ euros(linea.budgeted_cents) }} €</td>
                    <td>{{ euros(linea.ejecutado_cents) }} €</td>
                    <td>
                      <div class="barra" role="img" [attr.aria-label]="ariaBarra(linea)">
                        <div
                          class="barra-relleno"
                          [class.sobre]="linea.exceso_cents > 0"
                          [style.width.%]="porcentaje(linea)"
                        ></div>
                      </div>
                      {{ porcentajeTexto(linea) }}
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </app-card>

        <app-card [heading]="t('admin.events.accounting.contingencia.titulo')">
          <p>
            {{
              t('admin.events.accounting.contingencia.dotacion', {
                porcentaje: r.contingency_fund_percent,
                total: r.contingency_fund_cents !== null ? euros(r.contingency_fund_cents) : '—',
              })
            }}
          </p>
          <p>
            {{ t('admin.events.accounting.contingencia.consumido') }}:
            {{ euros(r.consumido_contingencia_cents) }} € ·
            {{ t('admin.events.accounting.contingencia.disponible') }}:
            {{
              r.disponible_contingencia_cents !== null
                ? euros(r.disponible_contingencia_cents) + ' €'
                : '—'
            }}
          </p>
        </app-card>

        <app-card [heading]="t('admin.events.accounting.evolucion.titulo')">
          @if (r.evolucion_temporal.length === 0) {
            <p>{{ t('admin.events.accounting.evolucion.sinDatos') }}</p>
          } @else {
            <table>
              <caption class="sr-only">
                {{
                  t('admin.events.accounting.evolucion.titulo')
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">{{ t('admin.events.accounting.evolucion.columnaPeriodo') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.evolucion.columnaIngresos') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.evolucion.columnaGastos') }}</th>
                </tr>
              </thead>
              <tbody>
                @for (punto of r.evolucion_temporal; track punto.periodo) {
                  <tr>
                    <td>{{ punto.periodo }}</td>
                    <td>{{ euros(punto.ingresos_cents) }} €</td>
                    <td>{{ euros(punto.gastos_cents) }} €</td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </app-card>

        <app-card [heading]="t('admin.events.accounting.movimientos.titulo')">
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

          <div
            role="tabpanel"
            id="movimiento-panel-ingresos"
            [attr.aria-labelledby]="'movimiento-tab-ingresos'"
            [hidden]="pestana() !== 'ingresos'"
          >
            <table>
              <caption class="sr-only">
                {{
                  t('admin.events.accounting.movimientos.pestanaIngresos')
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaOrigen') }}</th>
                  <th scope="col">
                    {{ t('admin.events.accounting.movimientos.columnaConcepto') }}
                  </th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaFecha') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaEstado') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaImporte') }}</th>
                </tr>
              </thead>
              <tbody>
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
                    <td>{{ euros(linea.importe_cents) }} €</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <div
            role="tabpanel"
            id="movimiento-panel-gastos"
            [attr.aria-labelledby]="'movimiento-tab-gastos'"
            [hidden]="pestana() !== 'gastos'"
          >
            <table>
              <caption class="sr-only">
                {{
                  t('admin.events.accounting.movimientos.pestanaGastos')
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">
                    {{ t('admin.events.accounting.movimientos.columnaProveedor') }}
                  </th>
                  <th scope="col">{{ t('admin.events.accounting.partidas.columnaPartida') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaFecha') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaBase') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaIva') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaTotal') }}</th>
                </tr>
              </thead>
              <tbody>
                @for (gasto of gastosMetalico(); track gasto.id) {
                  <tr>
                    <td>{{ gasto.provider_name }}</td>
                    <td>{{ nombrePartida(gasto.budget_line_id) }}</td>
                    <td>{{ gasto.expense_date | slice: 0 : 10 }}</td>
                    <td>{{ euros(gasto.base_cents) }} €</td>
                    <td>
                      {{
                        gasto.vat_cents !== null
                          ? euros(gasto.vat_cents) + ' €'
                          : t('admin.events.accounting.movimientos.exento')
                      }}
                    </td>
                    <td>{{ euros(gasto.total_cents) }} €</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <div
            role="tabpanel"
            id="movimiento-panel-especie"
            [attr.aria-labelledby]="'movimiento-tab-especie'"
            [hidden]="pestana() !== 'especie'"
          >
            <table>
              <caption class="sr-only">
                {{
                  t('admin.events.accounting.movimientos.pestanaEspecie')
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">
                    {{ t('admin.events.accounting.movimientos.columnaProveedor') }}
                  </th>
                  <th scope="col">{{ t('admin.events.accounting.partidas.columnaPartida') }}</th>
                  <th scope="col">{{ t('admin.events.accounting.movimientos.columnaTotal') }}</th>
                </tr>
              </thead>
              <tbody>
                @for (gasto of gastosEnEspecie(); track gasto.id) {
                  <tr>
                    <td>{{ gasto.provider_name }}</td>
                    <td>{{ nombrePartida(gasto.budget_line_id) }}</td>
                    <td>{{ euros(gasto.total_cents) }} €</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </app-card>

        <app-card [heading]="t('admin.events.accounting.altaPartida.titulo')">
          <form (submit)="crearPartida($event)" novalidate class="formulario">
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
        </app-card>

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
    .cabecera {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: var(--space-md);
      margin-bottom: var(--space-md);
    }
    .acciones-exportar {
      display: flex;
      gap: var(--space-sm);
    }
    .kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: var(--space-md);
      margin-bottom: var(--space-lg);
    }
    .kpi {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--surface);
      padding: var(--space-md);
    }
    .etiqueta {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
    }
    .valor {
      font-family: var(--font-mono);
      font-size: 1.5rem;
      margin-top: 6px;
    }
    .valor.positivo {
      color: var(--accent);
    }
    .valor.negativo {
      color: var(--danger);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: var(--space-md);
    }
    th,
    td {
      text-align: left;
      padding: var(--space-sm);
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }
    tr.sobre td {
      color: var(--danger);
    }
    .barra {
      display: inline-block;
      width: 100px;
      height: 10px;
      border: 1px solid var(--border);
      border-radius: 3px;
      overflow: hidden;
      vertical-align: middle;
      margin-right: 8px;
      background: var(--surface);
    }
    .barra-relleno {
      height: 100%;
      background: var(--muted);
    }
    .barra-relleno.sobre {
      background: var(--danger);
    }
    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: var(--space-md);
    }
    .tabs button {
      min-height: 2.25rem;
      padding: 0 14px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: transparent;
      cursor: pointer;
    }
    .tabs button[aria-selected='true'] {
      background: var(--accent);
      color: var(--on-accent);
      font-weight: 600;
    }
    .formulario {
      display: grid;
      gap: var(--space-sm);
      max-width: 28rem;
      margin-bottom: var(--space-md);
    }
    .campo {
      display: grid;
      gap: var(--space-xs);
    }
    .campo input,
    .campo select {
      /* La pintura del control la da la regla compartida de styles.css; aquí
         solo la densidad algo menor de este formulario. */
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

  protected readonly MOVIMIENTOS = MOVIMIENTOS;
  protected readonly pestana = signal<Movimiento>('ingresos');
  private readonly botonesPestana = viewChildren<ElementRef<HTMLButtonElement>>('pestanaBoton');

  protected readonly nombrePartidaNueva = signal('');
  protected readonly importePartidaNueva = signal('');
  protected readonly creandoPartida = signal(false);
  protected readonly errorPartida = signal<string | null>(null);


  protected readonly euros = euros;

  protected readonly totalIngresos = computed(() => this.ingresos()?.total_ingresos_cents ?? 0);
  protected readonly totalComprometido = computed(() =>
    (this.ingresos()?.comprometido ?? []).reduce((acc, l) => acc + l.importe_cents, 0),
  );
  /** Ejecutado en metálico: KPI propio (plan.md Decisión #4, hallazgo Alto
   * A1 del code review de la fase 5 — antes se fusionaba con la especie en
   * un único "Ejecutado", ocultando justo la cifra que la decisión exige
   * mantener separada). `por_partida` ya incluye la fila "sin partida"; no
   * se suma `gasto_sin_partida_cents` aparte, contaría dos veces. */
  protected readonly ejecutadoMetalico = computed(() => {
    const r = this.resumen();
    return r ? r.por_partida.reduce((acc, l) => acc + l.ejecutado_cents, 0) : 0;
  });
  /** Ejecutado total: KPI informativo que reconcilia el criterio de
   * aceptación de plan.md (suma de partidas metálico + especie == Ejecutado
   * total mostrado). No sustituye el desglose de A1, se muestra además. */
  protected readonly ejecutadoTotal = computed(
    () => this.ejecutadoMetalico() + (this.resumen()?.ejecutado_en_especie_cents ?? 0),
  );
  /** Saldo de caja: ingresos (incluida la especie, cobrada desde que se
   * valora) menos todo lo ejecutado, en metálico y en especie — misma
   * fórmula que `service.saldo_cents` en el backend (`export.py`), nunca
   * reimplementada de otro modo aquí. */
  protected readonly saldo = computed(() => this.totalIngresos() - this.ejecutadoTotal());

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

  ngOnInit(): void {
    void this.cargar();
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
   * principio/final — mismo patrón que
   * `event-agenda-section.ts#alPulsarTecla`. */
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

  protected nombrePartida(budgetLineId: string | null): string {
    if (budgetLineId === null) {
      return this.transloco.translate('admin.events.accounting.partidas.sinPartida');
    }
    return (
      this.lineas().find((l) => l.id === budgetLineId)?.name ??
      this.transloco.translate('admin.events.accounting.partidas.sinPartida')
    );
  }

  protected porcentaje(linea: ContingencyLine): number {
    if (linea.budgeted_cents <= 0) {
      return linea.ejecutado_cents > 0 ? 100 : 0;
    }
    return Math.min(100, Math.round((linea.ejecutado_cents / linea.budgeted_cents) * 100));
  }

  protected porcentajeTexto(linea: ContingencyLine): string {
    if (linea.budgeted_cents <= 0) {
      return '—';
    }
    return `${Math.round((linea.ejecutado_cents / linea.budgeted_cents) * 100)}%`;
  }

  protected ariaBarra(linea: ContingencyLine): string {
    const nombre = this.nombrePartida(linea.budget_line_id);
    return `${nombre}: ${euros(linea.ejecutado_cents)} € de ${euros(linea.budgeted_cents)} €`;
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
