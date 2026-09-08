import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';

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
  imports: [TranslocoDirective, Alert, Button, Card, Input],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.superadmin.titulo') }}</h1>
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
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
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
      border-bottom: 1px solid var(--color-border);
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
  `,
})
export class SuperadminPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

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

  constructor() {
    void this.cargarAuditoria();
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
