import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { DataTable } from '../../../shared/ui/data-table';
import { Input } from '../../../shared/ui/input';
import { PageHeader } from '../../../shared/ui/page-header';
import { SegmentedFilter } from '../../../shared/ui/segmented-filter';

/** Los identificadores semi-públicos de los proveedores de analítica. */
interface AjustesDeAnalitica {
  readonly ga4_measurement_id: string | null;
  readonly meta_pixel_id: string | null;
  readonly cloudflare_analytics_token: string | null;
}

/** Una celda del agregado semanal de consentimientos (fase 1). */
interface CeldaDeConsentimientos {
  readonly semana: string;
  readonly categoria: string;
  readonly total: number | null;
}

/** Estado explícito de las estadísticas de GA4 (fase 2): nunca un 500. */
interface StatsDeGa4 {
  readonly estado:
    'datos' | 'no_configurado' | 'credencial_invalida' | 'cuota_agotada' | 'error_proveedor';
  readonly detalle: string | null;
  readonly usuarios_activos: number | null;
  readonly sesiones: number | null;
  readonly vistas_pagina: number | null;
}

const AJUSTES_URL = '/admin/analytics-settings';
const CONSENTIMIENTOS_URL = '/admin/cookie-consents/stats';
const GA4_URL = '/admin/analytics-providers/ga4-stats';

type Dias = '7' | '30';

const CATEGORIAS = ['necessary', 'analytics', 'marketing'] as const;
const CLAVE_CATEGORIA: Record<(typeof CATEGORIAS)[number], string> = {
  necessary: 'cookies.banner.necesarias',
  analytics: 'cookies.banner.analiticas',
  marketing: 'cookies.banner.marketing',
};

const DIAS: readonly { valor: Dias; etiquetaKey: string }[] = [
  { valor: '7', etiquetaKey: 'admin.plataforma.analitica.dias.ultimos7' },
  { valor: '30', etiquetaKey: 'admin.plataforma.analitica.dias.ultimos30' },
];

function hoyIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * Pantalla de analítica externa de la plataforma (fase 3 del plan de
 * cookies `260916-2246-cookies-analitica-externa`): configuración de los
 * identificadores de proveedores, agregados de consentimientos y
 * estadísticas de GA4, todo sin salir del panel.
 *
 * Lectura para todo el personal de plataforma (`require_platform_staff`);
 * la escritura de la configuración es exclusiva del superadmin — para
 * `soporte` los campos se muestran deshabilitados.
 */
@Component({
  selector: 'app-analytics-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, DataTable, Input, PageHeader, SegmentedFilter],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.plataforma.analitica.titulo')">
        {{ t('admin.plataforma.analitica.descripcion') }}
      </app-page-header>

      @if (!esSuperadmin()) {
        <app-alert tone="info" [title]="t('admin.plataforma.analitica.soloLectura.titulo')">
          {{ t('admin.plataforma.analitica.soloLectura.texto') }}
        </app-alert>
      }

      <!-- Configuración de proveedores -->
      <form (submit)="guardar($event)">
        <app-card [heading]="t('admin.plataforma.analitica.proveedores')">
          @if (error(); as mensaje) {
            <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
          }
          @if (guardado()) {
            <app-alert tone="exito" [title]="t('comun.guardado')">
              {{ t('admin.plataforma.analitica.guardado') }}
            </app-alert>
          }

          <div class="campos">
            <app-input
              [label]="t('admin.plataforma.analitica.idGa4')"
              [hint]="t('admin.plataforma.analitica.idGa4Ayuda')"
              [disabled]="!esSuperadmin()"
              [(value)]="ga4MeasurementId"
            />
            <app-input
              [label]="t('admin.plataforma.analitica.idMeta')"
              [hint]="t('admin.plataforma.analitica.idMetaAyuda')"
              [disabled]="!esSuperadmin()"
              [(value)]="metaPixelId"
            />
            <app-input
              [label]="t('admin.plataforma.analitica.idCloudflare')"
              [hint]="t('admin.plataforma.analitica.idCloudflareAyuda')"
              [disabled]="!esSuperadmin()"
              [(value)]="cloudflareToken"
            />
          </div>

          @if (esSuperadmin()) {
            <app-button type="submit" [loading]="guardando()">
              {{ t('comun.guardar') }}
            </app-button>
          }
        </app-card>
      </form>

      <!-- Agregados de consentimientos -->
      <app-card [heading]="t('admin.plataforma.analitica.consentimientos')">
        <div class="selector">
          <app-segmented-filter
            [opciones]="opcionesDias()"
            [valor]="diasConsentimientos()"
            [etiqueta]="t('admin.plataforma.analitica.dias.etiqueta')"
            (cambio)="cambiarDiasConsentimientos($event)"
          />
        </div>

        @if (errorConsentimientos(); as mensaje) {
          <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
        } @else if (celdasConsentimientos(); as celdas) {
          @if (celdas.length === 0) {
            <p class="sin-datos">{{ t('admin.plataforma.analitica.consentimientosSinDatos') }}</p>
          } @else {
            <app-data-table
              [columnas]="columnasDeConsentimientos()"
              [etiqueta]="t('admin.plataforma.analitica.consentimientos')"
              [caption]="t('admin.plataforma.analitica.consentimientos')"
            >
              @for (fila of filasDeConsentimientos(); track fila.semana) {
                <tr>
                  <th scope="row">{{ fila.semana }}</th>
                  @for (celda of fila.celdas; track $index) {
                    <td class="numerica">{{ celda ?? '—' }}</td>
                  }
                </tr>
              }
            </app-data-table>
            <p class="nota">
              {{ t('admin.plataforma.analitica.consentimientosNota') }}
            </p>
          }
        } @else {
          <p>{{ t('comun.cargando') }}</p>
        }
      </app-card>

      <!-- Estadísticas de GA4 -->
      <app-card [heading]="t('admin.plataforma.analitica.ga4')">
        <div class="selector">
          <app-segmented-filter
            [opciones]="opcionesDias()"
            [valor]="diasGa4()"
            [etiqueta]="t('admin.plataforma.analitica.dias.etiqueta')"
            (cambio)="cambiarDiasGa4($event)"
          />
        </div>

        @if (errorGa4(); as mensaje) {
          <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
        } @else if (ga4(); as estadisticas) {
          @if (estadisticas.estado === 'datos') {
            <dl class="metricas">
              <div>
                <dt>{{ t('admin.plataforma.analitica.ga4Usuarios') }}</dt>
                <dd>{{ estadisticas.usuarios_activos }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.plataforma.analitica.ga4Sesiones') }}</dt>
                <dd>{{ estadisticas.sesiones }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.plataforma.analitica.ga4Vistas') }}</dt>
                <dd>{{ estadisticas.vistas_pagina }}</dd>
              </div>
            </dl>
          } @else {
            <!-- Estado explícito del backend (no configurado, credencial,
                 cuota…): nunca un «error inesperado» genérico. -->
            <app-alert tone="error" [title]="t('admin.plataforma.analitica.ga4SinDatos')">
              {{ estadisticas.detalle }}
            </app-alert>
          }
        } @else {
          <p>{{ t('comun.cargando') }}</p>
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    form {
      margin-block-end: 1.5rem;
    }
    .campos {
      display: grid;
      gap: 1rem;
      margin-block-end: 1rem;
    }
    .selector {
      margin-block-end: 1rem;
    }
    .sin-datos,
    .nota {
      color: var(--muted);
      font-size: 0.875rem;
    }
    .metricas {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 1rem;
      margin: 0;
    }
    .metricas dt {
      color: var(--muted);
      font-size: 0.8125rem;
    }
    .metricas dd {
      margin: 0.25rem 0 0;
      font-size: 1.5rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    @media (max-width: 640px) {
      .metricas {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class AnalyticsPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly auth = inject(AuthService);

  /** La escritura de la configuración es exclusiva del superadmin. */
  protected readonly esSuperadmin = computed(() => this.auth.currentUser()?.is_superadmin ?? false);

  protected readonly guardando = signal(false);
  protected readonly guardado = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly ga4MeasurementId = signal('');
  protected readonly metaPixelId = signal('');
  protected readonly cloudflareToken = signal('');

  protected readonly celdasConsentimientos = signal<CeldaDeConsentimientos[] | null>(null);
  protected readonly errorConsentimientos = signal<string | null>(null);
  protected readonly diasConsentimientos = signal<Dias>('30');

  protected readonly ga4 = signal<StatsDeGa4 | null>(null);
  protected readonly errorGa4 = signal<string | null>(null);
  protected readonly diasGa4 = signal<Dias>('30');

  protected readonly opcionesDias = computed(() =>
    DIAS.map((opcion) => ({
      valor: opcion.valor,
      etiqueta: this.transloco.translate(opcion.etiquetaKey),
    })),
  );

  protected readonly columnasDeConsentimientos = computed(() => [
    { key: 'semana', label: this.transloco.translate('admin.plataforma.analitica.semana') },
    ...CATEGORIAS.map((categoria) => ({
      key: categoria,
      label: this.transloco.translate(CLAVE_CATEGORIA[categoria]),
      numerica: true,
    })),
  ]);

  /** Filas semana × categoría para la tabla, semanas más recientes primero.
   * Una celda `null` es «suprimida por privacidad», no cero: se pinta «—». */
  protected readonly filasDeConsentimientos = computed(() => {
    const celdas = this.celdasConsentimientos() ?? [];
    const porSemana = new Map<string, Map<string, number | null>>();
    for (const celda of celdas) {
      let valores = porSemana.get(celda.semana);
      if (!valores) {
        valores = new Map();
        porSemana.set(celda.semana, valores);
      }
      valores.set(celda.categoria, celda.total);
    }
    return [...porSemana.entries()]
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([semana, valores]) => ({
        semana,
        celdas: CATEGORIAS.map((categoria) => valores.get(categoria) ?? null),
      }));
  });

  constructor() {
    void this.cargar();
    void this.cargarConsentimientos();
    void this.cargarGa4();
  }

  protected cambiarDiasConsentimientos(dias: Dias): void {
    this.diasConsentimientos.set(dias);
    void this.cargarConsentimientos();
  }

  protected cambiarDiasGa4(dias: Dias): void {
    this.diasGa4.set(dias);
    void this.cargarGa4();
  }

  async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    if (!this.esSuperadmin()) {
      return;
    }
    this.guardando.set(true);
    this.guardado.set(false);
    this.error.set(null);

    // Vacío = dejar el proveedor sin usar (`null` en el backend), no guardar
    // una cadena en blanco.
    const oNull = (valor: string): string | null => {
      const limpio = valor.trim();
      return limpio === '' ? null : limpio;
    };

    try {
      await firstValueFrom(
        this.http.put<AjustesDeAnalitica>(
          this.api.url(AJUSTES_URL),
          {
            ga4_measurement_id: oNull(this.ga4MeasurementId()),
            meta_pixel_id: oNull(this.metaPixelId()),
            cloudflare_analytics_token: oNull(this.cloudflareToken()),
          },
          { headers: this.api.serverForwardHeaders() },
        ),
      );
      this.guardado.set(true);
    } catch (fallo) {
      this.error.set(
        fallo instanceof ApiError
          ? fallo.message
          : this.transloco.translate('admin.plataforma.analitica.errorGuardar'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  private async cargar(): Promise<void> {
    try {
      const ajustes = await firstValueFrom(
        this.http.get<AjustesDeAnalitica>(this.api.url(AJUSTES_URL), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.ga4MeasurementId.set(ajustes.ga4_measurement_id ?? '');
      this.metaPixelId.set(ajustes.meta_pixel_id ?? '');
      this.cloudflareToken.set(ajustes.cloudflare_analytics_token ?? '');
    } catch {
      this.error.set(this.transloco.translate('admin.plataforma.analitica.errorCarga'));
    }
  }

  private async cargarConsentimientos(): Promise<void> {
    // Capturado antes de la petición: si el selector cambia mientras vuela,
    // la respuesta que llegue tarde se descarta — dos clics rápidos no
    // pueden pintar el periodo antiguo bajo el selector nuevo
    // (code-review de la fase 3, A-1).
    const diasPedidos = this.diasConsentimientos();
    this.errorConsentimientos.set(null);
    try {
      const respuesta = await firstValueFrom(
        this.http.get<{ celdas: CeldaDeConsentimientos[] }>(this.api.url(CONSENTIMIENTOS_URL), {
          headers: this.api.serverForwardHeaders(),
          params: { desde: this.fechaHaceDias(Number(diasPedidos)), hasta: hoyIso() },
        }),
      );
      if (this.diasConsentimientos() !== diasPedidos) return;
      this.celdasConsentimientos.set(respuesta.celdas);
    } catch {
      if (this.diasConsentimientos() !== diasPedidos) return;
      this.errorConsentimientos.set(
        this.transloco.translate('admin.plataforma.analitica.errorConsentimientos'),
      );
    }
  }

  private async cargarGa4(): Promise<void> {
    const diasPedidos = this.diasGa4();
    this.errorGa4.set(null);
    try {
      const respuesta = await firstValueFrom(
        this.http.get<StatsDeGa4>(this.api.url(GA4_URL), {
          headers: this.api.serverForwardHeaders(),
          params: { dias: Number(diasPedidos) },
        }),
      );
      if (this.diasGa4() !== diasPedidos) return;
      this.ga4.set(respuesta);
    } catch {
      if (this.diasGa4() !== diasPedidos) return;
      this.errorGa4.set(this.transloco.translate('admin.plataforma.analitica.errorGa4'));
    }
  }

  /** Fecha ISO de hace `dias` días (el backend redondea a lunes para el
   * agregado semanal). */
  private fechaHaceDias(dias: number): string {
    const fecha = new Date();
    fecha.setUTCDate(fecha.getUTCDate() - dias);
    return fecha.toISOString().slice(0, 10);
  }
}
