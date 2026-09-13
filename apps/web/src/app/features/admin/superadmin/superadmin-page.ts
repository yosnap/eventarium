import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { DataTable, DataTableColumn } from '../../../shared/ui/data-table';
import { Input } from '../../../shared/ui/input';
import { MetricasDePlataforma } from './platform-metrics.types';

interface AuditLogEntry {
  readonly id: string;
  readonly actor_user_id: string | null;
  readonly organization_id: string | null;
  readonly action: string;
  readonly entity_type: string;
  readonly entity_id: string | null;
  readonly detail: Record<string, unknown>;
  readonly created_at: string;
}

interface Page<T> {
  readonly items: readonly T[];
  readonly total: number;
}

const AUDIT_LOG_URL = '/admin/audit-log';

/**
 * Superadministración de la instalación (fase 5 del PRD): auditoría
 * filtrable, exportación RGPD de un evento y borrado de un inscrito bajo
 * solicitud. Ninguna de las tres acciones acepta un permiso de rol de
 * organización como alternativa a ser superadmin — el backend ya lo exige,
 * esta pantalla solo es visible en el menú para quien lo es
 * (`AuthService.currentUser().is_superadmin`).
 */
@Component({
  selector: 'app-superadmin-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Chip, DataTable, Input],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.superadmin.titulo') }}</h1>

      @if (metricas(); as m) {
        <div class="salud">
          <app-card [heading]="t('admin.plataforma.salud.titulo')">
            <ul class="estados">
              <li>
                <span>{{ t('admin.plataforma.salud.database') }}</span>
                <app-chip [tone]="tonoDeSalud(m.salud.database)">{{
                  t('admin.plataforma.salud.' + m.salud.database)
                }}</app-chip>
              </li>
              <li>
                <span>{{ t('admin.plataforma.salud.storage') }}</span>
                <app-chip [tone]="tonoDeSalud(m.salud.storage)">{{
                  t('admin.plataforma.salud.' + m.salud.storage)
                }}</app-chip>
              </li>
              <li>
                <span>{{ t('admin.plataforma.salud.redis') }}</span>
                <app-chip [tone]="tonoDeSalud(m.salud.redis)">{{
                  t('admin.plataforma.salud.' + m.salud.redis)
                }}</app-chip>
              </li>
            </ul>
          </app-card>

          <app-card [heading]="t('admin.plataforma.cifras.titulo')">
            <dl class="lista">
              <div>
                <dt>{{ t('admin.plataforma.cifras.organizaciones') }}</dt>
                <dd>{{ m.cifras.organizaciones_activas }} / {{ m.cifras.organizaciones_totales }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.plataforma.cifras.eventos') }}</dt>
                <dd>{{ m.cifras.eventos_totales }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.plataforma.cifras.publicados') }}</dt>
                <dd>{{ m.cifras.eventos_publicados }}</dd>
              </div>
              <div>
                <dt>{{ t('admin.plataforma.cifras.usuarios') }}</dt>
                <dd>{{ m.cifras.usuarios }}</dd>
              </div>
            </dl>
          </app-card>
        </div>

        <app-card [heading]="t('admin.plataforma.actividad.titulo')">
          <p class="nota">{{ t('admin.plataforma.actividad.ayuda') }}</p>
          <app-data-table
            [columnas]="columnasDeActividad()"
            [caption]="t('admin.plataforma.actividad.titulo')"
          >
            @for (org of m.organizaciones; track org.id) {
              <tr>
                <td>{{ org.name }}</td>
                <td class="numerica">{{ org.eventos }}</td>
                <td class="numerica">{{ org.inscripciones }}</td>
                <td>{{ fecha(org.evento_mas_reciente) }}</td>
                <td>{{ fecha(org.ultimo_evento_creado) }}</td>
                <td>{{ fecha(org.ultima_inscripcion) }}</td>
                <td>{{ fecha(org.ultimo_acceso) }}</td>
                <td>
                  @if (!org.is_active) {
                    <app-chip tone="apagado">{{
                      t('admin.plataforma.actividad.inactiva')
                    }}</app-chip>
                  } @else if (org.tiene_stripe_pendiente_con_eventos_de_pago) {
                    <app-chip tone="espera">{{
                      t('admin.plataforma.actividad.noCobra')
                    }}</app-chip>
                  } @else if (org.publicados_sin_inscripciones) {
                    <app-chip tone="espera">{{
                      t('admin.plataforma.actividad.sinInscripciones')
                    }}</app-chip>
                  } @else {
                    <app-chip tone="ok">{{ t('admin.plataforma.actividad.activa') }}</app-chip>
                  }
                </td>
              </tr>
            }
          </app-data-table>
        </app-card>
      } @else if (errorMetricas()) {
        <app-alert tone="error">{{ t('admin.plataforma.error') }}</app-alert>
      }

      <h2>{{ t('admin.plataforma.herramientas') }}</h2>
      <p>{{ t('admin.superadmin.descripcion') }}</p>

      <app-card [heading]="t('admin.superadmin.auditoria.titulo')">
        <form (submit)="filtrar($event)" novalidate class="filtros">
          <app-input
            fieldId="auditoria-organizacion"
            [label]="t('admin.superadmin.auditoria.organizacion')"
            [(value)]="filtroOrganizacion"
          />
          <app-input
            fieldId="auditoria-accion"
            [label]="t('admin.superadmin.auditoria.accion')"
            [(value)]="filtroAccion"
          />
          <div class="campo-fecha">
            <label for="auditoria-desde">{{ t('admin.superadmin.auditoria.desde') }}</label>
            <input
              id="auditoria-desde"
              type="datetime-local"
              [value]="filtroDesde()"
              (change)="filtroDesde.set(alValorDe($event))"
            />
          </div>
          <div class="campo-fecha">
            <label for="auditoria-hasta">{{ t('admin.superadmin.auditoria.hasta') }}</label>
            <input
              id="auditoria-hasta"
              type="datetime-local"
              [value]="filtroHasta()"
              (change)="filtroHasta.set(alValorDe($event))"
            />
          </div>
          <app-button type="submit" [loading]="cargandoAuditoria()">
            {{ t('admin.superadmin.auditoria.filtrar') }}
          </app-button>
        </form>

        @if (errorAuditoria(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (!cargandoAuditoria() && entradas().length === 0) {
          <p>{{ t('admin.superadmin.auditoria.sinResultados') }}</p>
        } @else {
          <table>
            <caption class="visualmente-oculto">
              {{
                t('admin.superadmin.auditoria.titulo')
              }}
            </caption>
            <thead>
              <tr>
                <th scope="col">{{ t('admin.superadmin.auditoria.columnaFecha') }}</th>
                <th scope="col">{{ t('admin.superadmin.auditoria.columnaAccion') }}</th>
                <th scope="col">{{ t('admin.superadmin.auditoria.columnaOrganizacion') }}</th>
                <th scope="col">{{ t('admin.superadmin.auditoria.columnaEntidad') }}</th>
                <th scope="col">{{ t('admin.superadmin.auditoria.columnaDetalle') }}</th>
              </tr>
            </thead>
            <tbody>
              @for (entrada of entradas(); track entrada.id) {
                <tr>
                  <td>{{ entrada.created_at }}</td>
                  <td>{{ entrada.action }}</td>
                  <td>{{ entrada.organization_id ?? '—' }}</td>
                  <td>{{ entrada.entity_type }} · {{ entrada.entity_id ?? '—' }}</td>
                  <td>
                    <code>{{ resumenDetalle(entrada.detail) }}</code>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </app-card>

      <app-card [heading]="t('admin.superadmin.exportar.titulo')">
        <p>{{ t('admin.superadmin.exportar.descripcion') }}</p>
        <form (submit)="exportar($event)" novalidate class="formulario">
          <app-input
            fieldId="export-event-id"
            [label]="t('admin.superadmin.exportar.eventId')"
            [required]="true"
            [(value)]="exportEventId"
          />
          <app-input
            fieldId="export-password"
            type="password"
            [label]="t('admin.superadmin.exportar.password')"
            [required]="true"
            [(value)]="exportPassword"
          />
          @if (errorExportar(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }
          @if (exportOk()) {
            <app-alert tone="exito">{{ t('admin.superadmin.exportar.correcto') }}</app-alert>
          }
          <app-button type="submit" [loading]="exportando()">
            {{ t('admin.superadmin.exportar.boton') }}
          </app-button>
        </form>
      </app-card>

      <app-card [heading]="t('admin.superadmin.borrar.titulo')">
        <p>{{ t('admin.superadmin.borrar.descripcion') }}</p>
        <form (submit)="borrar($event)" novalidate class="formulario">
          <app-input
            fieldId="borrar-event-id"
            [label]="t('admin.superadmin.borrar.eventId')"
            [required]="true"
            [(value)]="borrarEventId"
          />
          <app-input
            fieldId="borrar-email"
            type="email"
            [label]="t('admin.superadmin.borrar.email')"
            [required]="true"
            [(value)]="borrarEmail"
          />
          <app-input
            fieldId="borrar-password"
            type="password"
            [label]="t('admin.superadmin.borrar.password')"
            [required]="true"
            [(value)]="borrarPassword"
          />
          @if (errorBorrar(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }
          @if (borrarOk()) {
            <app-alert tone="exito">{{ t('admin.superadmin.borrar.correcto') }}</app-alert>
          }
          <app-button type="submit" variant="peligro" [loading]="borrando()">
            {{ t('admin.superadmin.borrar.boton') }}
          </app-button>
        </form>
      </app-card>
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    .filtros {
      display: flex;
      flex-wrap: wrap;
      align-items: end;
      gap: var(--space-md);
      margin-bottom: var(--space-md);
    }
    .campo-fecha {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-fecha input {
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      color: var(--fg);
      font: inherit;
      min-height: 2.75rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th,
    td {
      text-align: left;
      padding: var(--space-sm);
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    .visualmente-oculto {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      max-width: 34rem;
    }
    app-card {
      display: block;
      margin-bottom: var(--space-lg);
    }
    .salud {
      display: grid;
      gap: var(--space-md);
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
    }
    .estados,
    .lista {
      display: grid;
      gap: var(--space-sm);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .estados li,
    .lista > div {
      display: flex;
      align-items: center;
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
      margin: 0 0 var(--space-md);
      color: var(--muted);
      font-size: 0.875rem;
    }
  `,
})
export class SuperadminPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  /** Las columnas de la tabla de actividad, con la etiqueta ya traducida. */
  protected readonly columnasDeActividad = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'organizacion', label: t('admin.plataforma.actividad.columnaOrganizacion') },
      { key: 'eventos', label: t('admin.plataforma.actividad.columnaEventos'), numerica: true },
      {
        key: 'inscripciones',
        label: t('admin.plataforma.actividad.columnaInscripciones'),
        numerica: true,
      },
      { key: 'tocado', label: t('admin.plataforma.actividad.columnaEventoTocado') },
      { key: 'creado', label: t('admin.plataforma.actividad.columnaEventoCreado') },
      { key: 'inscripcion', label: t('admin.plataforma.actividad.columnaInscripcion') },
      { key: 'acceso', label: t('admin.plataforma.actividad.columnaAcceso') },
      { key: 'estado', label: t('admin.plataforma.actividad.columnaEstado') },
    ];
  });


  protected readonly filtroOrganizacion = signal('');
  protected readonly filtroAccion = signal('');
  protected readonly filtroDesde = signal('');
  protected readonly filtroHasta = signal('');
  protected readonly cargandoAuditoria = signal(false);
  protected readonly errorAuditoria = signal<string | null>(null);
  protected readonly entradas = signal<AuditLogEntry[]>([]);

  protected readonly exportEventId = signal('');
  protected readonly exportPassword = signal('');
  protected readonly exportando = signal(false);
  protected readonly exportOk = signal(false);
  protected readonly errorExportar = signal<string | null>(null);

  protected readonly borrarEventId = signal('');
  protected readonly borrarEmail = signal('');
  protected readonly borrarPassword = signal('');
  protected readonly borrando = signal(false);
  protected readonly borrarOk = signal(false);
  protected readonly errorBorrar = signal<string | null>(null);

  protected readonly metricas = signal<MetricasDePlataforma | null>(null);
  protected readonly errorMetricas = signal(false);

  constructor() {
    void this.cargarMetricas();
    void this.cargarAuditoria();
  }

  private async cargarMetricas(): Promise<void> {
    try {
      const datos = await firstValueFrom(
        this.http.get<MetricasDePlataforma>(this.api.url('/admin/metrics')),
      );
      this.metricas.set(datos);
    } catch {
      // El escritorio es informativo: si sus cifras no llegan, las
      // herramientas de abajo siguen siendo utilizables.
      this.errorMetricas.set(true);
    }
  }

  /** Un fallo de dependencia se marca en rojo; el resto, en verde. */
  protected tonoDeSalud(estado: string): ChipTone {
    return estado === 'ok' ? 'ok' : 'espera';
  }

  /** Una marca que no consta se dice como tal, no se deja en blanco. */
  protected fecha(valor: string | null): string {
    if (!valor) {
      return '—';
    }
    return new Intl.DateTimeFormat('es-ES', { dateStyle: 'short' }).format(new Date(valor));
  }

  protected alValorDe(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  protected resumenDetalle(detalle: Record<string, unknown>): string {
    return JSON.stringify(detalle);
  }

  protected filtrar(evento: Event): void {
    evento.preventDefault();
    void this.cargarAuditoria();
  }

  private async cargarAuditoria(): Promise<void> {
    this.cargandoAuditoria.set(true);
    this.errorAuditoria.set(null);
    try {
      const params: Record<string, string> = { limit: '50', offset: '0' };
      if (this.filtroOrganizacion().trim()) {
        params['organization_id'] = this.filtroOrganizacion().trim();
      }
      if (this.filtroAccion().trim()) {
        params['action'] = this.filtroAccion().trim();
      }
      if (this.filtroDesde()) {
        params['date_from'] = new Date(this.filtroDesde()).toISOString();
      }
      if (this.filtroHasta()) {
        params['date_to'] = new Date(this.filtroHasta()).toISOString();
      }
      const pagina = await firstValueFrom(
        this.http.get<Page<AuditLogEntry>>(this.api.url(AUDIT_LOG_URL), { params }),
      );
      this.entradas.set([...pagina.items]);
    } catch (error) {
      this.errorAuditoria.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.superadmin.auditoria.error'),
      );
    } finally {
      this.cargandoAuditoria.set(false);
    }
  }

  protected async exportar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.errorExportar.set(null);
    this.exportOk.set(false);
    this.exportando.set(true);
    try {
      const blob = await firstValueFrom(
        this.http.post(
          this.api.url(`/admin/events/${this.exportEventId().trim()}/rgpd-export`),
          { password: this.exportPassword() },
          { responseType: 'blob' },
        ),
      );
      const url = URL.createObjectURL(blob as Blob);
      const enlace = document.createElement('a');
      enlace.href = url;
      enlace.download = `${this.exportEventId().trim()}-rgpd.zip`;
      enlace.click();
      URL.revokeObjectURL(url);
      this.exportPassword.set('');
      this.exportOk.set(true);
    } catch (error) {
      this.errorExportar.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.superadmin.exportar.error'),
      );
    } finally {
      this.exportando.set(false);
    }
  }

  protected async borrar(evento: Event): Promise<void> {
    evento.preventDefault();
    if (typeof window !== 'undefined') {
      const confirmado = window.confirm(
        this.transloco.translate('admin.superadmin.borrar.confirmar'),
      );
      if (!confirmado) {
        return;
      }
    }
    this.errorBorrar.set(null);
    this.borrarOk.set(false);
    this.borrando.set(true);
    try {
      await firstValueFrom(
        this.http.request('DELETE', this.api.url('/admin/registrations/by-email'), {
          body: {
            event_id: this.borrarEventId().trim(),
            email: this.borrarEmail().trim(),
            password: this.borrarPassword(),
          },
        }),
      );
      this.borrarPassword.set('');
      this.borrarOk.set(true);
      await this.cargarAuditoria();
    } catch (error) {
      this.errorBorrar.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.superadmin.borrar.error'),
      );
    } finally {
      this.borrando.set(false);
    }
  }
}
