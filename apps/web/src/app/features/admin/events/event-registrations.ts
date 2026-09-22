import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { fechaRelativa } from '../../../shared/text/fecha-relativa';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { DataTable, DataTableColumn } from '../../../shared/ui/data-table';
import { Dialog } from '../../../shared/ui/dialog';
import { KpiCard } from '../../../shared/ui/kpi-card';
import { PageHeader } from '../../../shared/ui/page-header';
import { Panel } from '../../../shared/ui/panel';
import { SegmentedFilter } from '../../../shared/ui/segmented-filter';
import { TableToolbar } from '../../../shared/ui/table-toolbar';
import { RegistrationQuestions } from './registration-questions';
import {
  type RegistrationListItem,
  type RegistrationPage,
  type RegistrationStats,
  type RegistrationStatus,
  claveDeEstado,
} from './registration-types';

const LIMITE = 20;

/** Las cuatro categorías del filtro segmentado del prototipo
 * (`panel-organizador.html`), cada una mapeada al estado real que filtra en
 * el servidor, más un quinto botón («Otras») que no existe en el prototipo:
 * agrupa lo que ni el prototipo ni el backend tratan como un único estado
 * (verificación pendiente, pago pendiente, rechazadas, canceladas), para que
 * sigan siendo filtrables — el `<select>` de 7 estados que sustituye esta
 * pantalla sí los cubría uno a uno. Como el backend solo filtra por un
 * status exacto, «otras» se resuelve en cliente sobre la página cargada,
 * igual que la búsqueda. */
type SegmentoFiltro = 'todas' | 'pendientes' | 'confirmadas' | 'espera' | 'otras';

const ESTADOS_DE_OTRAS: readonly RegistrationStatus[] = [
  'pending_verification',
  'pending_payment',
  'rejected',
  'cancelled',
];

const ESTADO_POR_SEGMENTO: Record<SegmentoFiltro, RegistrationStatus | ''> = {
  todas: '',
  pendientes: 'pending_approval',
  confirmadas: 'confirmed',
  espera: 'waitlisted',
  otras: '',
};

interface KpiVisible {
  readonly rotulo: string;
  readonly valor: string;
  readonly descriptor: string | null;
  readonly tono: 'warn' | 'accent' | null;
}

interface FilaEmbudo {
  readonly etiqueta: string;
  readonly valor: number;
  readonly ancho: number;
}

/**
 * Panel de organizador para las inscripciones de un evento: estructura de
 * `panel-organizador.html` (cabecera con la cifra pendiente, 4 KPIs, embudo
 * del formulario a la entrada, tabla con toolbar y filtro segmentado) sobre
 * los datos que ya sirve `GET /events/{id}/registrations/stats` — ese
 * endpoint ya trae `approved`/`issued`, los dos escalones del embudo que
 * faltaban en el tipo del frontend.
 *
 * «Motivo declarado» (columna del prototipo) queda fuera: qué respuesta del
 * formulario dinámico mostrar es decisión de producto, no de estilos. El
 * filtro segmentado y la búsqueda cubren la tabla.
 */
@Component({
  selector: 'app-event-registrations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    Alert,
    Button,
    Chip,
    DataTable,
    Dialog,
    KpiCard,
    PageHeader,
    Panel,
    SegmentedFilter,
    TableToolbar,
    RegistrationQuestions,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.events.registrations.titulo')">
        @switch (bucketPendientes()) {
          @case ('cero') {
            {{ t('admin.events.registrations.cabecera.sinPendientes') }}
          }
          @case ('una') {
            {{ t('admin.events.registrations.cabecera.una') }}
          }
          @default {
            {{ t('admin.events.registrations.cabecera.variasInicio') }}
            <span class="mark">{{
              t('admin.events.registrations.cabecera.variasMarca', {
                n: stats()?.pending_approval,
              })
            }}</span>
            {{ t('admin.events.registrations.cabecera.variasFin') }}
          }
        }
      </app-page-header>

      @if (statsError(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }
      @if (kpis().length > 0) {
        <div class="kpis">
          @for (kpi of kpis(); track kpi.rotulo) {
            <app-kpi-card
              [rotulo]="kpi.rotulo"
              [valor]="kpi.valor"
              [descriptor]="kpi.descriptor"
              [tono]="kpi.tono"
            />
          }
        </div>
      }

      @if (filasEmbudo().length > 0) {
        <app-panel class="bloque">
          <div cabecera>
            <span class="rotulo-seccion">{{ t('admin.events.registrations.embudo.titulo') }}</span>
          </div>
          <div class="panel-cuerpo">
            <div class="embudo">
              @for (fila of filasEmbudo(); track fila.etiqueta) {
                <div class="embudo-fila">
                  <span>{{ fila.etiqueta }}</span>
                  <span class="embudo-rail"><span [style.width.%]="fila.ancho"></span></span>
                  <span class="embudo-num">{{ fila.valor }}</span>
                </div>
              }
            </div>
            @if (stats(); as s) {
              @if (s.verified_conversion_rate !== null) {
                <p class="hint">
                  {{
                    t('admin.events.registrations.embudo.insight', {
                      tasa: formatearTasa(s.verified_conversion_rate),
                    })
                  }}
                </p>
              }
            }
          </div>
        </app-panel>
      }

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }
      @if (accionError(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      <app-panel class="bloque">
        <div cabecera>
          <span class="rotulo-seccion">{{ t('admin.events.registrations.tablaTitulo') }}</span>
          <app-table-toolbar
            [busqueda]="busqueda()"
            (busquedaChange)="busqueda.set($event)"
            [placeholderBusqueda]="t('admin.events.registrations.buscarPlaceholder')"
          >
            <app-segmented-filter
              [opciones]="opcionesFiltro()"
              [valor]="segmentoFiltro()"
              [etiqueta]="t('admin.events.registrations.filtrarPorEstado')"
              (cambio)="alCambiarSegmento($event)"
            />
          </app-table-toolbar>
        </div>

        @if (cargando()) {
          <p class="panel-cuerpo">{{ t('comun.cargando') }}</p>
        } @else if (items().length === 0) {
          <p class="panel-cuerpo vacio">{{ t('admin.events.registrations.sinInscripciones') }}</p>
        } @else {
          <app-data-table
            [columnas]="columnasDeInscripciones()"
            [caption]="t('admin.events.registrations.titulo')"
          >
            @for (item of itemsFiltrados(); track item.id) {
              <tr>
                <td>
                  <a
                    class="persona-apilada"
                    [routerLink]="['/dashboard/events', eventId(), 'registrations', item.id]"
                  >
                    <strong>{{ item.full_name }}</strong>
                    <small>{{ item.email }}</small>
                  </a>
                </td>
                <td class="num muted">{{ fechaRelativa(item.created_at) }}</td>
                <td>
                  <app-chip [tone]="tonoDeEstado(item.status)">{{
                    t('admin.events.registrations.estado' + claveDeEstado(item.status))
                  }}</app-chip>
                </td>
                <td class="acciones">
                  @if (item.status === 'pending_approval') {
                    <app-button
                      variant="secundario"
                      type="button"
                      [compacto]="true"
                      [loading]="accionPendiente() === item.id"
                      (pulsado)="aprobar(item.id)"
                    >
                      {{ t('admin.events.registrations.aprobar') }}
                    </app-button>
                    <app-button
                      variant="peligro"
                      type="button"
                      [compacto]="true"
                      [loading]="accionPendiente() === item.id"
                      (pulsado)="abrirDialogoRechazo(item)"
                    >
                      {{ t('admin.events.registrations.rechazar') }}
                    </app-button>
                  }
                  @if (item.status !== 'cancelled' && item.status !== 'rejected') {
                    <app-button
                      variant="peligro"
                      type="button"
                      [compacto]="true"
                      [loading]="accionPendiente() === item.id"
                      (pulsado)="cancelar(item.id)"
                    >
                      {{ t('admin.events.registrations.cancelar') }}
                    </app-button>
                  }
                </td>
              </tr>
            }
          </app-data-table>
          @if (itemsFiltrados().length === 0) {
            <p class="panel-cuerpo vacio">{{ t('admin.events.registrations.sinCoincidencias') }}</p>
          }

          @if (totalPaginas() > 1) {
            <nav
              [attr.aria-label]="t('admin.events.registrations.titulo')"
              class="paginacion panel-cuerpo"
            >
              <app-button
                variant="secundario"
                type="button"
                [disabled]="offset() === 0"
                (pulsado)="irAPagina(offset() - limite)"
              >
                {{ t('admin.events.registrations.anterior') }}
              </app-button>
              <span>
                {{
                  t('admin.events.registrations.paginaDe', {
                    actual: paginaActual(),
                    total: totalPaginas(),
                  })
                }}
              </span>
              <app-button
                variant="secundario"
                type="button"
                [disabled]="offset() + limite >= total()"
                (pulsado)="irAPagina(offset() + limite)"
              >
                {{ t('admin.events.registrations.siguiente') }}
              </app-button>
            </nav>
          }
        }
      </app-panel>

      <app-dialog #dialogoRechazo (cerrado)="alCerrarDialogoRechazo()">
        <span class="rotulo-seccion">{{
          t('admin.events.registrations.dialogoRechazo.rotulo')
        }}</span>
        @if (personaARechazar(); as persona) {
          <h3>{{ persona.full_name }}</h3>
        }
        <label class="campo-mensaje">
          <span>{{ t('admin.events.registrations.dialogoRechazo.mensajeLabel') }}</span>
          <textarea
            maxlength="500"
            [value]="motivoRechazo()"
            (input)="motivoRechazo.set(alTexto($event))"
          ></textarea>
        </label>
        @if (accionError(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        <app-button pie variant="secundario" type="button" (pulsado)="dialogoRechazo.cerrar()">
          {{ t('comun.cancelar') }}
        </app-button>
        <app-button
          pie
          variant="peligro"
          type="button"
          [loading]="accionPendiente() === personaARechazar()?.id"
          (pulsado)="confirmarRechazo()"
        >
          {{ t('admin.events.registrations.dialogoRechazo.confirmar') }}
        </app-button>
      </app-dialog>

      <app-registration-questions [eventId]="eventId()" />
    </ng-container>
  `,
  styles: `
    .bloque {
      display: block;
      margin-bottom: var(--sp-6);
    }
    .kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(11.25rem, 1fr));
      gap: var(--sp-4);
      margin-bottom: var(--sp-6);
    }
    /* .funnel / .funnel__row / .funnel__rail (panel-organizador.html:27-30). */
    .embudo {
      display: grid;
      gap: 12px;
      margin-top: var(--sp-3);
    }
    .embudo-fila {
      display: grid;
      grid-template-columns: 10.625rem 1fr 4.75rem;
      gap: var(--sp-4);
      align-items: center;
      font-size: var(--fs-sm);
    }
    .embudo-rail {
      height: 20px;
      border: 1px solid var(--border-strong);
      border-radius: 3px;
      background-color: var(--bg);
      overflow: hidden;
      display: block;
    }
    .embudo-rail > span {
      display: block;
      height: 100%;
      background-color: var(--surface-hi);
      border-right: 1px solid var(--faint);
    }
    .embudo-fila:first-child .embudo-rail > span {
      background-color: var(--accent-dim);
      border-right-color: var(--accent);
    }
    .embudo-num {
      font-family: var(--font-mono);
      text-align: right;
    }
    .hint {
      margin: 20px 0 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .nota-alcance {
      margin: 0;
      padding-top: 0;
      padding-bottom: var(--space-sm);
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .vacio {
      text-align: center;
      color: var(--muted);
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
      flex-wrap: wrap;
    }
    .paginacion {
      display: flex;
      align-items: center;
      gap: var(--space-md);
    }
    /* Diálogo de rechazo: mismo patrón de campo que el resto del panel. */
    h3 {
      margin: 10px 0 14px;
    }
    .campo-mensaje {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-mensaje textarea {
      min-height: 6rem;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      color: var(--fg);
      font: inherit;
      resize: vertical;
    }
    /* .funnel__row bajo 860px (panel-organizador.html): la etiqueta cede
       espacio a la cifra en vez de desbordar en pantallas estrechas. */
    @media (max-width: 860px) {
      .embudo-fila {
        grid-template-columns: 7.5rem 1fr 3.75rem;
      }
    }
  `,
})
export class EventRegistrations implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly dialogoRechazoRef = viewChild.required(Dialog);

  protected readonly claveDeEstado = claveDeEstado;
  protected readonly fechaRelativa = fechaRelativa;
  protected readonly limite = LIMITE;

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly items = signal<RegistrationListItem[]>([]);
  protected readonly total = signal(0);
  protected readonly offset = signal(0);
  protected readonly estadoFiltro = signal<RegistrationStatus | ''>('');
  protected readonly segmentoFiltro = signal<SegmentoFiltro>('todas');
  protected readonly busqueda = signal('');

  protected readonly stats = signal<RegistrationStats | null>(null);
  protected readonly statsError = signal<string | null>(null);

  protected readonly accionPendiente = signal<string | null>(null);
  protected readonly accionError = signal<string | null>(null);
  protected readonly personaARechazar = signal<RegistrationListItem | null>(null);
  protected readonly motivoRechazo = signal('');

  protected readonly totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / LIMITE)));
  protected readonly paginaActual = computed(() => Math.floor(this.offset() / LIMITE) + 1);

  /** Filtro por texto sobre la página ya cargada (nombre o email): el
   * backend no ofrece búsqueda por texto, decisión explícita del plan
   * («filtro cliente») en vez de un endpoint nuevo. */
  protected readonly itemsFiltrados = computed(() => {
    const consulta = this.busqueda().trim().toLowerCase();
    const soloOtras = this.segmentoFiltro() === 'otras';
    return this.items().filter((item) => {
      if (soloOtras && !ESTADOS_DE_OTRAS.includes(item.status)) {
        return false;
      }
      if (!consulta) {
        return true;
      }
      return (
        item.full_name.toLowerCase().includes(consulta) ||
        item.email.toLowerCase().includes(consulta)
      );
    });
  });

  protected readonly bucketPendientes = computed<'cero' | 'una' | 'varias'>(() => {
    const n = this.stats()?.pending_approval ?? 0;
    if (n === 0) return 'cero';
    if (n === 1) return 'una';
    return 'varias';
  });

  protected readonly kpis = computed<readonly KpiVisible[]>(() => {
    const s = this.stats();
    if (!s) {
      return [];
    }
    const t = (clave: string, params?: Record<string, unknown>) =>
      this.transloco.translate(clave, params);
    return [
      {
        rotulo: t('admin.events.registrations.kpis.confirmadas'),
        valor: String(s.confirmed),
        descriptor:
          s.confirmed_conversion_rate != null
            ? t('admin.events.registrations.kpis.confirmadasDescriptor', {
                tasa: this.formatearTasa(s.confirmed_conversion_rate),
              })
            : null,
        tono: null,
      },
      {
        rotulo: t('admin.events.registrations.kpis.porAprobar'),
        valor: String(s.pending_approval),
        descriptor: t('admin.events.registrations.kpis.porAprobarDescriptor'),
        tono: 'warn',
      },
      {
        rotulo: t('admin.events.registrations.kpis.listaEspera'),
        valor: String(s.waitlisted),
        descriptor: null,
        tono: null,
      },
      {
        rotulo: t('admin.events.registrations.kpis.emitidas'),
        valor: String(s.issued),
        descriptor: t('admin.events.registrations.kpis.emitidasDescriptor'),
        tono: null,
      },
    ];
  });

  /** Embudo iniciado → verificado → aprobada → entrada emitida
   * (panel-organizador.html); el rail de cada fila es relativo al primer
   * escalón, como en la referencia. */
  protected readonly filasEmbudo = computed<readonly FilaEmbudo[]>(() => {
    const s = this.stats();
    if (!s) {
      return [];
    }
    const t = (clave: string) => this.transloco.translate(clave);
    const max = Math.max(s.initiated, 1);
    return [
      {
        etiqueta: t('admin.events.registrations.embudo.iniciado'),
        valor: s.initiated,
        ancho: 100,
      },
      {
        etiqueta: t('admin.events.registrations.embudo.verificado'),
        valor: s.verified,
        ancho: (s.verified / max) * 100,
      },
      {
        etiqueta: t('admin.events.registrations.embudo.aprobada'),
        valor: s.approved,
        ancho: (s.approved / max) * 100,
      },
      {
        etiqueta: t('admin.events.registrations.embudo.emitida'),
        valor: s.issued,
        ancho: (s.issued / max) * 100,
      },
    ];
  });

  protected readonly opcionesFiltro = computed(() => {
    const t = (clave: string) => this.transloco.translate(clave);
    return [
      { valor: 'todas' as const, etiqueta: t('admin.events.registrations.filtroSegmentado.todas') },
      {
        valor: 'pendientes' as const,
        etiqueta: t('admin.events.registrations.filtroSegmentado.pendientes'),
      },
      {
        valor: 'confirmadas' as const,
        etiqueta: t('admin.events.registrations.filtroSegmentado.confirmadas'),
      },
      {
        valor: 'espera' as const,
        etiqueta: t('admin.events.registrations.filtroSegmentado.espera'),
      },
      {
        valor: 'otras' as const,
        etiqueta: t('admin.events.registrations.filtroSegmentado.otras'),
      },
    ];
  });

  /** Las columnas de la tabla de inscripciones, con la etiqueta ya traducida. */
  protected readonly columnasDeInscripciones = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'persona', label: t('admin.events.registrations.columnaPersona') },
      { key: 'fecha', label: t('admin.events.registrations.columnaFecha') },
      { key: 'estado', label: t('admin.events.registrations.columnaEstado') },
      { key: 'acciones', label: t('admin.events.registrations.columnaAcciones') },
    ];
  });

  ngOnInit(): void {
    void this.cargar();
    void this.cargarEstadisticas();
  }

  /** El estado de una inscripción se lee por su texto: el color solo lo refuerza. */
  protected tonoDeEstado(estado: RegistrationStatus): ChipTone {
    switch (estado) {
      case 'confirmed':
        return 'ok';
      case 'pending_verification':
      case 'pending_approval':
      case 'pending_payment':
      case 'waitlisted':
        return 'espera';
      case 'rejected':
      case 'cancelled':
        return 'apagado';
    }
  }

  protected formatearTasa(valor: number | null): string {
    if (valor === null) {
      return '—';
    }
    return `${(valor * 100).toFixed(1)}%`;
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLTextAreaElement).value;
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const params: Record<string, string | number> = {
        limit: LIMITE,
        offset: this.offset(),
      };
      if (this.estadoFiltro()) {
        params['status'] = this.estadoFiltro();
      }
      const pagina = await firstValueFrom(
        this.http.get<RegistrationPage>(this.api.url(`/events/${this.eventId()}/registrations`), {
          params,
        }),
      );
      this.items.set([...pagina.items]);
      this.total.set(pagina.total);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrations.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  private async cargarEstadisticas(): Promise<void> {
    try {
      const stats = await firstValueFrom(
        this.http.get<RegistrationStats>(
          this.api.url(`/events/${this.eventId()}/registrations/stats`),
        ),
      );
      this.stats.set(stats);
    } catch (error) {
      this.statsError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrations.estadisticas.error'),
      );
    }
  }

  protected alCambiarSegmento(segmento: SegmentoFiltro): void {
    this.segmentoFiltro.set(segmento);
    this.estadoFiltro.set(ESTADO_POR_SEGMENTO[segmento]);
    this.offset.set(0);
    void this.cargar();
  }

  protected irAPagina(nuevoOffset: number): void {
    this.offset.set(Math.max(0, nuevoOffset));
    void this.cargar();
  }

  private async ejecutarAccion(id: string, accion: 'approve' | 'cancel'): Promise<void> {
    this.accionError.set(null);
    this.accionPendiente.set(id);
    try {
      await firstValueFrom(
        this.http.post<RegistrationListItem>(
          this.api.url(`/events/${this.eventId()}/registrations/${id}/${accion}`),
          {},
        ),
      );
      await Promise.all([this.cargar(), this.cargarEstadisticas()]);
    } catch (error) {
      this.accionError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrations.error'),
      );
    } finally {
      this.accionPendiente.set(null);
    }
  }

  protected aprobar(id: string): void {
    void this.ejecutarAccion(id, 'approve');
  }

  protected cancelar(id: string): void {
    void this.ejecutarAccion(id, 'cancel');
  }

  /** Abre el diálogo con el mensaje por defecto ya escrito — el prototipo lo
   * prellena y siempre avisa («Rechazar y avisar»), nunca un rechazo mudo. */
  protected abrirDialogoRechazo(item: RegistrationListItem): void {
    this.personaARechazar.set(item);
    this.motivoRechazo.set(
      this.transloco.translate('admin.events.registrations.dialogoRechazo.mensajePorDefecto'),
    );
    this.accionError.set(null);
    this.dialogoRechazoRef().abrir();
  }

  protected alCerrarDialogoRechazo(): void {
    this.personaARechazar.set(null);
  }

  protected async confirmarRechazo(): Promise<void> {
    const persona = this.personaARechazar();
    if (!persona) {
      return;
    }
    this.accionError.set(null);
    this.accionPendiente.set(persona.id);
    try {
      const motivo = this.motivoRechazo().trim();
      await firstValueFrom(
        this.http.post<RegistrationListItem>(
          this.api.url(`/events/${this.eventId()}/registrations/${persona.id}/reject`),
          { reason: motivo || null },
        ),
      );
      this.dialogoRechazoRef().cerrar();
      await Promise.all([this.cargar(), this.cargarEstadisticas()]);
    } catch (error) {
      this.accionError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrations.error'),
      );
    } finally {
      this.accionPendiente.set(null);
    }
  }
}
