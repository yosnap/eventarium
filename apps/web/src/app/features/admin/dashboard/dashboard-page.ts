import { HttpClient } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { DataTable, DataTableColumn } from '../../../shared/ui/data-table';
import { KpiCard } from '../../../shared/ui/kpi-card';
import { PageHeader } from '../../../shared/ui/page-header';
import { Panel } from '../../../shared/ui/panel';
import { MetricasDeOrganizacion } from './organization-metrics.types';

/** Una petición pendiente, resuelta para pintar. */
interface Pendiente {
  readonly clave: string;
  readonly cantidad: number;
  readonly enlace: string;
}

/** Un KPI ya resuelto (etiqueta y valor traducidos/formateados), listo para pintar. */
interface KpiVisible {
  readonly rotulo: string;
  readonly valor: string;
  readonly descriptor: string | null;
  readonly tono: 'warn' | 'accent' | null;
}

/**
 * Escritorio de la organización: cómo va todo lo suyo y qué tiene pendiente.
 *
 * Está ordenado **por utilidad**, no por importancia: primero lo que pide una
 * decisión (solicitudes por aprobar, borradores sin publicar, Stripe a medias),
 * después la tabla de eventos —que es lo que más se usa— y al final las cifras
 * de conjunto. Un escritorio que empieza por totales obliga a leer para saber si
 * hay algo que hacer.
 *
 * **No decide permisos.** Los bloques que la API omite por falta de permiso no
 * llegan, y aquí se comprueba que existen antes de pintarlos. Duplicar la regla
 * sería tenerla en dos sitios que pueden divergir.
 */
@Component({
  selector: 'app-dashboard-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    DatePipe,
    Alert,
    Card,
    Chip,
    DataTable,
    KpiCard,
    PageHeader,
    Panel,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.escritorioPagina.rotulo')">
        @if (pendientes().length > 0) {
          {{ t('admin.escritorioPagina.cabeceraPendienteInicio') }}
          <span class="mark">{{
            t('admin.escritorioPagina.cabeceraPendienteCifra', { n: pendientes().length })
          }}</span>
          {{ t('admin.escritorioPagina.cabeceraPendienteFin') }}
        } @else {
          {{ t('admin.escritorioPagina.cabeceraAlDia') }}
        }
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ t(mensaje) }}</app-alert>
      }

      @if (metricas(); as m) {
        @if (pendientes().length > 0) {
          <app-card class="bloque" [heading]="t('admin.escritorioPagina.pendiente')">
            <ul class="pendientes">
              @for (p of pendientes(); track p.clave) {
                <li>
                  <a [routerLink]="p.enlace">{{ t('admin.escritorioPagina.' + p.clave) }}</a>
                  <strong>{{ p.cantidad }}</strong>
                </li>
              }
            </ul>
          </app-card>
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

        <app-panel class="bloque">
          <div cabecera>
            <span class="rotulo-seccion">{{ t('admin.escritorioPagina.eventos') }}</span>
          </div>
          @if (m.eventos.length === 0) {
            <div class="panel-cuerpo">
              <p>{{ t('admin.escritorioPagina.sinEventos') }}</p>
              <a routerLink="/dashboard/events/nuevo">{{
                t('admin.escritorioPagina.crearPrimerEvento')
              }}</a>
            </div>
          } @else {
            <app-data-table
              [columnas]="columnasDeEventos()"
              [caption]="t('admin.escritorioPagina.eventos')"
            >
              @for (evento of m.eventos; track evento.id) {
                <tr>
                  <td>
                    <a [routerLink]="['/dashboard/events', evento.id]">{{ evento.title }}</a>
                  </td>
                  <td>{{ evento.starts_at | date: 'shortDate' }}</td>
                  <td>
                    <app-chip [tone]="tonoDeEstado(evento.status)">{{
                      t('admin.escritorioPagina.estadoEvento.' + evento.status)
                    }}</app-chip>
                  </td>
                  @if (conInscripciones()) {
                    <td class="numerica">
                      {{ evento.confirmadas }}
                      @if (evento.aforo !== null) {
                        <span> / {{ evento.aforo }}</span>
                      }
                    </td>
                    <td class="numerica">{{ evento.por_aprobar }}</td>
                  }
                  @if (conDinero()) {
                    <td class="numerica">
                      {{
                        evento.ingresos_cents === null ? '—' : formatearCents(evento.ingresos_cents)
                      }}
                    </td>
                  }
                </tr>
              }
            </app-data-table>
          }
        </app-panel>

        <div class="cifras">
          @if (m.cifras; as c) {
            <app-card [heading]="t('admin.events.metricas.inscripciones')">
              <dl class="lista">
                <div>
                  <dt>{{ t('admin.escritorioPagina.columnaPorAprobar') }}</dt>
                  <dd>{{ c.por_aprobar }}</dd>
                </div>
                <div>
                  <dt>{{ t('admin.events.registrations.estadisticas.listaEspera') }}</dt>
                  <dd>{{ c.lista_de_espera }}</dd>
                </div>
                <div>
                  <dt>{{ t('admin.events.metricas.ocupacion') }}</dt>
                  <dd>
                    @if (c.aforo_total !== null) {
                      {{ c.reservadas }} / {{ c.aforo_total }}
                    } @else {
                      {{ c.reservadas }}
                    }
                  </dd>
                </div>
              </dl>
            </app-card>
          }

          <app-card [heading]="t('admin.escritorioPagina.estructura')">
            <dl class="lista">
              <div>
                <dt>{{ t('admin.escritorioPagina.miembros') }}</dt>
                <dd>{{ m.estructura.miembros }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.escritorioPagina.roles') }}</dt>
                <dd>{{ m.estructura.roles }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.escritorioPagina.patrocinadores') }}</dt>
                <dd>{{ m.estructura.patrocinadores }}</dd>
              </div>
            </dl>
          </app-card>

          <app-card [heading]="t('admin.escritorioPagina.cobros')">
            @if (m.stripe.charges_enabled) {
              <app-chip tone="ok">{{ t('admin.escritorioPagina.stripeListo') }}</app-chip>
            } @else if (m.stripe.conectada) {
              <app-chip tone="espera">{{ t('admin.escritorioPagina.stripeAMedias') }}</app-chip>
              <p class="nota">
                <a routerLink="/dashboard/stripe">{{
                  t('admin.escritorioPagina.terminarStripe')
                }}</a>
              </p>
            } @else {
              <app-chip tone="apagado">{{
                t('admin.escritorioPagina.stripeSinConectar')
              }}</app-chip>
              <p class="nota">
                <a routerLink="/dashboard/stripe">{{
                  t('admin.escritorioPagina.conectarStripe')
                }}</a>
              </p>
            }
          </app-card>
        </div>
      } @else if (!error()) {
        <p>{{ t('comun.cargando') }}</p>
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .pendientes {
      display: grid;
      gap: var(--space-sm);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .pendientes li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
    }
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
    .cifras {
      display: grid;
      gap: var(--space-md);
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      margin-top: var(--space-lg);
    }
    .lista {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-sm);
      margin: 0;
    }
    /* Con wrap: rótulo y cifra en una línea no cabían en móvil. */
    .lista > div {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 0 var(--space-md);
    }
    .lista dt {
      color: var(--muted);
    }
    .lista dt,
    .lista dd {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .lista dd {
      margin: 0;
      font-variant-numeric: tabular-nums;
    }
    .nota {
      margin: var(--space-xs) 0 0;
      font-size: 0.875rem;
    }
  `,
})
export class DashboardPage implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly metricas = signal<MetricasDeOrganizacion | null>(null);
  protected readonly error = signal<string | null>(null);

  /** `true` si el bloque de dinero llegó: sin permiso, la API no lo manda. */
  protected readonly conDinero = computed(() => this.metricas()?.dinero !== null);

  /**
   * `true` si llegan los conteos de inscripción. Se mira en la primera fila, no
   * en el bloque de cifras: la API omite las columnas por evento con el mismo
   * permiso, y una cabecera sin dato detrás promete algo que no va a llegar.
   */
  protected readonly conInscripciones = computed(() => {
    const eventos = this.metricas()?.eventos ?? [];
    return eventos.length > 0 && eventos[0].confirmadas !== null;
  });

  /**
   * Las columnas de la tabla, según lo que haya llegado. Se componen aquí y no
   * en la plantilla porque `app-data-table` las pinta todas: las que dependen de
   * un permiso tienen que existir solo cuando su dato existe.
   *
   * La etiqueta se traduce **aquí** y no en la plantilla: el componente compartido
   * recibe texto ya resuelto, no claves, así que la traducción tiene que ocurrir
   * al construir la lista. Por eso el `computed` depende de la señal de idioma.
   */
  protected readonly columnasDeEventos = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    const columnas: DataTableColumn[] = [
      { key: 'evento', label: t('admin.escritorioPagina.columnaEvento') },
      { key: 'fecha', label: t('admin.escritorioPagina.columnaFecha') },
      { key: 'estado', label: t('admin.escritorioPagina.columnaEstado') },
    ];
    if (this.conInscripciones()) {
      columnas.push(
        { key: 'ocupacion', label: t('admin.events.metricas.ocupacion'), numerica: true },
        { key: 'porAprobar', label: t('admin.escritorioPagina.columnaPorAprobar'), numerica: true },
      );
    }
    if (this.conDinero()) {
      columnas.push({
        key: 'ingresos',
        label: t('admin.escritorioPagina.columnaIngresos'),
        numerica: true,
      });
    }
    return columnas;
  });

  /**
   * Los KPI de cabecera: eventos publicados y próximos son siempre visibles
   * (vienen del propio listado de eventos, sin permiso adicional); inscritos y
   * dinero solo aparecen cuando `cifras`/`dinero` llegaron, exactamente igual
   * que las columnas de la tabla — la misma frontera de permiso, en dos sitios
   * distintos de la misma pantalla.
   */
  protected readonly kpis = computed<readonly KpiVisible[]>(() => {
    const m = this.metricas();
    if (!m) {
      return [];
    }
    const t = (clave: string, params?: Record<string, unknown>) =>
      this.transloco.translate(clave, params);
    const ahora = Date.now();
    const publicados = m.eventos.filter((evento) => evento.status === 'published').length;
    const proximos = m.eventos.filter(
      (evento) => evento.status === 'published' && new Date(evento.starts_at).getTime() >= ahora,
    ).length;
    const lista: KpiVisible[] = [
      {
        rotulo: t('admin.escritorioPagina.kpis.eventosPublicados'),
        valor: String(publicados),
        descriptor: null,
        tono: null,
      },
      {
        rotulo: t('admin.escritorioPagina.kpis.proximosEventos'),
        valor: String(proximos),
        descriptor: null,
        tono: null,
      },
    ];
    if (m.cifras) {
      lista.push({
        rotulo: t('admin.escritorioPagina.kpis.inscritosConfirmados'),
        valor: String(m.cifras.reservadas),
        descriptor:
          m.cifras.aforo_total !== null
            ? t('admin.escritorioPagina.kpis.inscritosConfirmadosDescriptor', {
                aforo: m.cifras.aforo_total,
              })
            : null,
        tono: null,
      });
    }
    if (m.dinero) {
      const totalCents = Object.values(m.dinero.por_moneda).reduce(
        (suma, valor) => suma + valor,
        0,
      );
      lista.push({
        rotulo: t('admin.escritorioPagina.kpis.ingresosTotales'),
        valor: this.formatearCents(totalCents),
        descriptor: null,
        tono: 'accent',
      });
    }
    return lista;
  });

  /**
   * Lo que pide una decisión, en orden de urgencia. Se compone de lo que la API
   * haya mandado: sin permiso de inscripciones no hay «por aprobar» que mostrar,
   * y sin permiso económico no se cuenta Stripe (que es una herramienta de
   * cobro, no de administración).
   */
  protected readonly pendientes = computed<readonly Pendiente[]>(() => {
    const m = this.metricas();
    if (!m) {
      return [];
    }
    const lista: Pendiente[] = [];
    const porAprobar = m.cifras?.por_aprobar ?? 0;
    if (porAprobar > 0) {
      lista.push({
        clave: 'solicitudesPorAprobar',
        cantidad: porAprobar,
        enlace: '/dashboard/events',
      });
    }
    if (m.eventos_en_borrador > 0) {
      lista.push({
        clave: 'borradores',
        cantidad: m.eventos_en_borrador,
        enlace: '/dashboard/events',
      });
    }
    if (m.dinero && !m.stripe.charges_enabled) {
      lista.push({
        clave: m.stripe.conectada ? 'stripeAMediasPendiente' : 'stripeSinConectarPendiente',
        cantidad: 1,
        enlace: '/dashboard/stripe',
      });
    }
    return lista;
  });

  // En `ngOnInit` y no en el constructor: es el ciclo en el que el resto de
  // pantallas del panel cargan sus datos, y mantiene el patrón.
  ngOnInit(): void {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const datos = await firstValueFrom(
        this.http.get<MetricasDeOrganizacion>(this.api.url('/organizations/me/metrics')),
      );
      this.metricas.set(datos);
    } catch {
      this.error.set('admin.escritorioPagina.error');
    }
  }

  protected tonoDeEstado(estado: string): ChipTone {
    const tonos: Record<string, ChipTone> = {
      published: 'ok',
      draft: 'espera',
      archived: 'apagado',
      cancelled: 'apagado',
    };
    return tonos[estado] ?? 'neutro';
  }

  protected formatearCents(cents: number): string {
    return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(
      cents / 100,
    );
  }
}
