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
import { MetricasDeOrganizacion } from './organization-metrics.types';

/** Una petición pendiente, resuelta para pintar. */
interface Pendiente {
  readonly clave: string;
  readonly cantidad: number;
  readonly enlace: string;
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
  imports: [TranslocoDirective, RouterLink, DatePipe, Alert, Card, Chip, DataTable],
  template: `
    <ng-container *transloco="let t">
      @if (error(); as mensaje) {
        <app-alert tone="error">{{ t(mensaje) }}</app-alert>
      }

      @if (metricas(); as m) {
        @if (pendientes().length > 0) {
          <app-card [heading]="t('admin.escritorioPagina.pendiente')">
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

        <app-card [heading]="t('admin.escritorioPagina.eventos')">
          @if (m.eventos.length === 0) {
            <p>{{ t('admin.escritorioPagina.sinEventos') }}</p>
            <a routerLink="/dashboard/events/nuevo">{{
              t('admin.escritorioPagina.crearPrimerEvento')
            }}</a>
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
                      {{ evento.confirmadas }}@if (evento.aforo !== null) {<span>
                        / {{ evento.aforo }}</span
                      >}
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
        </app-card>

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
              <app-chip tone="apagado">{{ t('admin.escritorioPagina.stripeSinConectar') }}</app-chip>
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
    .cifras {
      display: grid;
      gap: var(--space-md);
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      margin-top: var(--space-lg);
    }
    .lista {
      display: grid;
      gap: var(--space-sm);
      margin: 0;
    }
    .lista > div {
      display: flex;
      justify-content: space-between;
      gap: var(--space-md);
    }
    .lista dt {
      color: var(--muted);
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
      lista.push({ clave: 'solicitudesPorAprobar', cantidad: porAprobar, enlace: '/dashboard/events' });
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
    };
    return tonos[estado] ?? 'neutro';
  }

  protected formatearCents(cents: number): string {
    return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(
      cents / 100,
    );
  }
}
