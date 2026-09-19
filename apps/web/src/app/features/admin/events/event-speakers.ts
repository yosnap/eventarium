import { DatePipe } from '@angular/common';
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
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Chip } from '../../../shared/ui/chip';
import { DataTable, type DataTableColumn } from '../../../shared/ui/data-table';
import { Dialog } from '../../../shared/ui/dialog';
import { KpiCard } from '../../../shared/ui/kpi-card';
import { PageHeader } from '../../../shared/ui/page-header';
import { Panel } from '../../../shared/ui/panel';
import { SegmentedFilter } from '../../../shared/ui/segmented-filter';
import { TableToolbar } from '../../../shared/ui/table-toolbar';
import {
  type EventSpeakersView,
  type SpeakerHistoryItem,
  type SpeakerRow,
  monograma,
} from './speakers-types';

type SegmentoFiltro = 'todas' | 'incompletas' | 'repiten' | 'sin-sesion';

const SEGMENTOS = ['todas', 'incompletas', 'repiten', 'sin-sesion'] as const;

/**
 * Panel de ponentes del evento (`panel-ponentes.html`): la vista agregada
 * que agrupa ficha, sesión asignada y participación entre ediciones. La
 * completitud se lee por la longitud del rail y su cifra, nunca solo por el
 * color; el monograma se deriva en cliente del nombre.
 */
@Component({
  selector: 'app-event-speakers',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    DatePipe,
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
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.events.speakers.rotulo')">
        @switch (bucketSinBio()) {
          @case ('cero') {
            {{ t('admin.events.speakers.cabecera.sinBio') }}
          }
          @case ('una') {
            {{ t('admin.events.speakers.cabecera.unaInicio') }}
            <span class="mark">1</span>
            {{ t('admin.events.speakers.cabecera.unaFin') }}
          }
          @default {
            {{ t('admin.events.speakers.cabecera.variasInicio') }}
            <span class="mark">{{
              t('admin.events.speakers.cabecera.cifra', { n: faltanBio() })
            }}</span>
            {{ t('admin.events.speakers.cabecera.variasFin') }}
          }
        }
        <div acciones>
          <a routerLink="/dashboard/events/{{ eventId() }}/agenda">
            <app-button variant="primario" type="button">
              {{ t('admin.events.speakers.invitarPonente') }}
            </app-button>
          </a>
        </div>
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (vista(); as v) {
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

        <app-panel>
          <div cabecera>
            <span class="rotulo-seccion">{{ t('admin.events.speakers.panelFichas') }}</span>
            <app-table-toolbar
              [busqueda]="busqueda()"
              (busquedaChange)="busqueda.set($event)"
              [placeholderBusqueda]="t('admin.events.speakers.buscarPlaceholder')"
            >
              <app-segmented-filter
                [opciones]="opcionesFiltro()"
                [valor]="segmento()"
                [etiqueta]="t('admin.events.speakers.filtroEtiqueta')"
                (cambio)="segmento.set($event)"
              />
            </app-table-toolbar>
          </div>

          @if (itemsFiltrados().length === 0) {
            <p class="panel-cuerpo vacio">
              {{ t('admin.events.speakers.sinCoincidencias') }}
            </p>
          } @else {
            <app-data-table [columnas]="columnas()" [caption]="t('admin.events.speakers.rotulo')">
              @for (fila of itemsFiltrados(); track fila.organization_member_id) {
                <tr>
                  <td>
                    <span class="ponente">
                      <span class="monograma" aria-hidden="true">{{
                        monograma(fila.first_name, fila.last_name, fila.email)
                      }}</span>
                      <span>
                        <strong>{{ nombre(fila) }}</strong>
                        <small>{{ fila.email }}</small>
                      </span>
                    </span>
                  </td>
                  <td>
                    @if (fila.sesiones.length === 0) {
                      <app-chip tone="espera">{{ t('admin.events.speakers.sinAsignar') }}</app-chip>
                    } @else {
                      {{ fila.sesiones[0].titulo }}
                      @if (fila.sesiones.length > 1) {
                        <small class="mas">
                          {{
                            t('admin.events.speakers.masSesiones', { n: fila.sesiones.length - 1 })
                          }}
                        </small>
                      }
                    }
                  </td>
                  <td>
                    <span
                      class="fill"
                      [class.fill-full]="fila.completitud.porcentaje === 100"
                      [class.fill-low]="fila.completitud.porcentaje < 50"
                      role="img"
                      [attr.aria-label]="
                        fila.completitud.porcentaje === 100
                          ? t('admin.events.speakers.fichaCompleta')
                          : t('admin.events.speakers.ariaFicha', {
                              pct: fila.completitud.porcentaje,
                              faltan: listaDeFaltantes(fila),
                            })
                      "
                    >
                      <span class="fill-rail">
                        <span [style.width.%]="fila.completitud.porcentaje"></span>
                      </span>
                      <span class="num">{{ fila.completitud.porcentaje }}%</span>
                    </span>
                  </td>
                  <td class="numerica">{{ fila.ediciones }}</td>
                  <td class="acciones">
                    @if (fila.completitud.porcentaje < 100) {
                      <app-button
                        variant="secundario"
                        type="button"
                        [compacto]="true"
                        [loading]="pidiendoBio() === fila.organization_member_id"
                        (pulsado)="pedirBio(fila)"
                      >
                        {{ t('admin.events.speakers.pedirBio') }}
                      </app-button>
                    }
                    @if (fila.sesiones.length === 0) {
                      <a class="enlace" routerLink="/dashboard/events/{{ eventId() }}/agenda">
                        {{ t('admin.events.speakers.asignarSesion') }}
                      </a>
                    }
                    <app-button
                      variant="terciario"
                      type="button"
                      [compacto]="true"
                      (pulsado)="abrirHistorial(fila)"
                    >
                      {{ t('admin.events.speakers.historial') }}
                    </app-button>
                  </td>
                </tr>
              }
            </app-data-table>
          }
        </app-panel>

        @if (aviso(); as mensaje) {
          <p class="aviso" role="status" aria-live="polite">{{ mensaje }}</p>
        }
        <p class="hint pie-pagina">
          {{ t('admin.events.speakers.piePerfil') }}
          @if (primerSlugPublico(); as slug) {
            <a href="/ponentes/{{ slug }}" class="enlace-publico">{{
              t('admin.events.speakers.verPerfilPublico')
            }}</a>
          }
        </p>
      }

      <app-dialog #dialogoHistorial (cerrado)="historialPersona.set(null)">
        <span class="rotulo-seccion">{{ t('admin.events.speakers.historialRotulo') }}</span>
        @if (historialPersona(); as persona) {
          <h3>{{ nombre(persona) }}</h3>
        }
        <p class="hint">{{ t('admin.events.speakers.historialExplicacion') }}</p>
        @if (historialCargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (historial(); as lineas) {
          @if (lineas.length === 0) {
            <p class="hint">{{ t('admin.events.speakers.historialVacio') }}</p>
          } @else {
            <div class="historial">
              @for (linea of lineas; track $index) {
                <div class="historial-item">
                  <span>{{ linea.evento_titulo }}</span>
                  <span class="num">
                    @if (linea.rol; as claveRol) {
                      {{ etiquetaDeRol(claveRol) }}
                    } @else {
                      —
                    }
                  </span>
                </div>
              }
            </div>
          }
        }
        <div pie>
          <app-button variant="secundario" type="button" (pulsado)="dialogoHistorial.cerrar()">
            {{ t('comun.cerrar') }}
          </app-button>
        </div>
      </app-dialog>
    </ng-container>
  `,
  styles: `
    .kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(10.625rem, 1fr));
      gap: var(--sp-4);
      margin-bottom: var(--sp-6);
    }
    /* .p / .p__m (panel-ponentes.html): monograma cuadrado + nombre con el
       email debajo. */
    .ponente {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .monograma {
      width: 38px;
      height: 38px;
      flex: 0 0 auto;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      display: grid;
      place-items: center;
      font-family: var(--font-display);
      font-size: 1rem;
      color: var(--muted);
      padding-top: 2px;
    }
    .ponente small {
      display: block;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    /* .fill / .fill__rail (panel-ponentes.html): la completitud se lee por
       longitud y cifra; el color solo refuerza (lleno=accent, bajo=warn). */
    .fill {
      display: flex;
      align-items: center;
      gap: 9px;
    }
    .fill-rail {
      width: 74px;
      height: 8px;
      border: 1px solid var(--border-strong);
      border-radius: 2px;
      background-color: var(--bg);
      overflow: hidden;
      display: block;
    }
    .fill-rail > span {
      display: block;
      height: 100%;
      background-color: var(--muted);
    }
    .fill-full .fill-rail > span {
      background-color: var(--accent);
    }
    .fill-low .fill-rail > span {
      background-color: var(--warn);
    }
    .mas {
      display: block;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .acciones {
      display: flex;
      gap: var(--space-xs);
      flex-wrap: wrap;
      justify-content: flex-end;
      align-items: center;
    }
    .enlace {
      font-size: var(--fs-sm);
    }
    .vacio {
      text-align: center;
      color: var(--muted);
    }
    .pie-pagina {
      margin-top: var(--sp-4);
    }
    h3 {
      margin: 10px 0 4px;
    }
    /* .hist / .hist__i (panel-ponentes.html). */
    .historial {
      display: grid;
      gap: 8px;
      margin-top: var(--sp-4);
    }
    .historial-item {
      display: flex;
      justify-content: space-between;
      gap: var(--sp-4);
      padding: 10px 13px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      font-size: var(--fs-sm);
    }
    .historial-item .num {
      font-family: var(--font-mono);
      color: var(--muted);
      white-space: nowrap;
    }
  `,
})
export class EventSpeakers implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly dialogoHistorialRef = viewChild.required(Dialog);

  protected readonly monograma = monograma;

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly vista = signal<EventSpeakersView | null>(null);
  protected readonly busqueda = signal('');
  protected readonly segmento = signal<SegmentoFiltro>('todas');

  protected readonly pidiendoBio = signal<string | null>(null);
  protected readonly aviso = signal<string | null>(null);

  protected readonly historialPersona = signal<SpeakerRow | null>(null);
  protected readonly historial = signal<readonly SpeakerHistoryItem[] | null>(null);
  protected readonly historialCargando = signal(false);

  /** Cuántas fichas tienen la bio sin rellenar: la cifra de la cabecera. */
  protected readonly faltanBio = computed(
    () =>
      this.vista()?.items.filter((fila) => fila.completitud.faltantes.includes('bio')).length ?? 0,
  );

  /** El perfil público es por persona; para el pie basta con uno. */
  protected readonly primerSlugPublico = computed(
    () => this.vista()?.items.find((fila) => fila.public_slug)?.public_slug ?? null,
  );

  protected readonly bucketSinBio = computed<'cero' | 'una' | 'varias'>(() => {
    const n = this.faltanBio();
    if (n === 0) return 'cero';
    if (n === 1) return 'una';
    return 'varias';
  });

  protected readonly kpis = computed(() => {
    const v = this.vista();
    if (!v) {
      return [];
    }
    const fichaCompleta = v.items.filter((fila) => fila.completitud.porcentaje === 100).length;
    const sinBio = v.items.filter((fila) => fila.completitud.faltantes.includes('bio')).length;
    const repiten = v.items.filter((fila) => fila.ediciones > 1).length;
    const t = (clave: string, params?: Record<string, unknown>) =>
      this.transloco.translate(clave, params);
    return [
      {
        rotulo: t('admin.events.speakers.kpis.enPrograma'),
        valor: String(v.items.length),
        descriptor: t('admin.events.speakers.kpis.enProgramaDescriptor', {
          n: v.total_sesiones,
        }),
        tono: null,
      },
      {
        rotulo: t('admin.events.speakers.kpis.fichaCompleta'),
        valor: String(fichaCompleta),
        descriptor: t('admin.events.speakers.kpis.fichaCompletaDescriptor'),
        tono: null,
      },
      {
        rotulo: t('admin.events.speakers.kpis.sinBio'),
        valor: String(sinBio),
        descriptor: t('admin.events.speakers.kpis.sinBioDescriptor'),
        tono: 'warn' as const,
      },
      {
        rotulo: t('admin.events.speakers.kpis.repiten'),
        valor: String(repiten),
        descriptor: t('admin.events.speakers.kpis.repitenDescriptor'),
        tono: null,
      },
    ];
  });

  protected readonly opcionesFiltro = computed(() => {
    const t = (clave: string) => this.transloco.translate(clave);
    return SEGMENTOS.map((valor) => ({
      valor,
      etiqueta: t(`admin.events.speakers.filtro.${valor}`),
    }));
  });

  protected readonly columnas = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'ponente', label: t('admin.events.speakers.columnaPonente') },
      { key: 'sesion', label: t('admin.events.speakers.columnaSesion') },
      { key: 'ficha', label: t('admin.events.speakers.columnaFicha') },
      { key: 'ediciones', label: t('admin.events.speakers.columnaEdiciones') },
      { key: 'acciones', label: '' },
    ];
  });

  /** Filtro en cliente sobre la lista completa: el endpoint ya trae a todos
   * los ponentes del evento, no hay paginación que romper. Los tres filtros
   * del prototipo son predicados independientes (una persona puede repetir
   * edición y tener la ficha incompleta a la vez). */
  protected readonly itemsFiltrados = computed(() => {
    const v = this.vista();
    if (!v) {
      return [] as SpeakerRow[];
    }
    const consulta = this.busqueda().trim().toLowerCase();
    const segmento = this.segmento();
    const pasaSegmento: Record<SegmentoFiltro, (fila: SpeakerRow) => boolean> = {
      todas: () => true,
      incompletas: (fila) => fila.completitud.porcentaje < 100,
      repiten: (fila) => fila.ediciones > 1,
      'sin-sesion': (fila) => fila.sesiones.length === 0,
    };
    return v.items.filter(pasaSegmento[segmento]).filter((fila) => {
      if (!consulta) {
        return true;
      }
      return (
        nombreCompleto(fila).toLowerCase().includes(consulta) ||
        fila.email.toLowerCase().includes(consulta) ||
        (fila.titular?.toLowerCase().includes(consulta) ?? false)
      );
    });
  });

  ngOnInit(): void {
    void this.cargar();
  }

  protected nombre(fila: SpeakerRow): string {
    return nombreCompleto(fila);
  }

  /** La clave del rol es texto libre en el backend: si no hay traducción,
   * el valor tal cual es mejor que ver la clave cruda. */
  protected etiquetaDeRol(clave: string): string {
    const traducida = this.transloco.translate(`admin.events.speakers.rol.${clave}`);
    return traducida === `admin.events.speakers.rol.${clave}` ? clave : traducida;
  }

  /** Lista legible de claves que faltan, para el aria del rail. */
  protected listaDeFaltantes(fila: SpeakerRow): string {
    const t = (clave: string) => this.transloco.translate(clave);
    if (fila.completitud.faltantes.length === 0) {
      return t('admin.events.speakers.fichaCompleta');
    }
    return fila.completitud.faltantes
      .map((clave) => t(`admin.events.speakers.campos.${clave}`))
      .join(', ');
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set(null);
    try {
      const vista = await firstValueFrom(
        this.http.get<EventSpeakersView>(this.api.url(`/events/${this.eventId()}/speakers`)),
      );
      this.vista.set(vista);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.speakers.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected async pedirBio(fila: SpeakerRow): Promise<void> {
    this.error.set(null);
    this.pidiendoBio.set(fila.organization_member_id);
    try {
      await firstValueFrom(
        this.http.post(
          this.api.url(
            `/events/${this.eventId()}/speakers/${fila.organization_member_id}/pedir-bio`,
          ),
          {},
        ),
      );
      this.aviso.set(this.transloco.translate('admin.events.speakers.bioPedida'));
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.speakers.error'),
      );
    } finally {
      this.pidiendoBio.set(null);
    }
  }

  protected async abrirHistorial(fila: SpeakerRow): Promise<void> {
    this.historialPersona.set(fila);
    this.historial.set(null);
    this.historialCargando.set(true);
    this.dialogoHistorialRef().abrir();
    try {
      const lineas = await firstValueFrom(
        this.http.get<readonly SpeakerHistoryItem[]>(
          this.api.url(`/events/${this.eventId()}/speakers/${fila.user_id}/historial`),
        ),
      );
      this.historial.set(lineas);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.speakers.error'),
      );
      this.dialogoHistorialRef().cerrar();
    } finally {
      this.historialCargando.set(false);
    }
  }
}

function nombreCompleto(fila: SpeakerRow): string {
  return (
    [fila.first_name, fila.last_name].filter((parte) => !!parte?.trim()).join(' ') || fila.email
  );
}
