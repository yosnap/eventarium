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
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { RegistrationQuestions } from './registration-questions';
import {
  ESTADOS_DE_INSCRIPCION,
  type RegistrationListItem,
  type RegistrationPage,
  type RegistrationStats,
  type RegistrationStatus,
  claveDeEstado,
} from './registration-types';

const LIMITE = 20;

/**
 * Panel de organizador para las inscripciones de un evento: estadísticas
 * agregadas, listado paginado con filtro por estado y acciones de
 * aprobar/rechazar/cancelar según el estado de cada inscripción.
 */
@Component({
  selector: 'app-event-registrations',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, DatePipe, Alert, Button, Card, RegistrationQuestions],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.registrations.titulo')">
        @if (statsError(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (stats(); as s) {
          <dl class="estadisticas">
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.iniciados') }}</dt>
              <dd>{{ s.initiated }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.verificados') }}</dt>
              <dd>{{ s.verified }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.pendientesAprobacion') }}</dt>
              <dd>{{ s.pending_approval }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.confirmados') }}</dt>
              <dd>{{ s.confirmed }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.rechazados') }}</dt>
              <dd>{{ s.rejected }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.cancelados') }}</dt>
              <dd>{{ s.cancelled }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.listaEspera') }}</dt>
              <dd>{{ s.waitlisted }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.tasaVerificados') }}</dt>
              <dd>{{ formatearTasa(s.verified_conversion_rate) }}</dd>
            </div>
            <div>
              <dt>{{ t('admin.events.registrations.estadisticas.tasaConfirmados') }}</dt>
              <dd>{{ formatearTasa(s.confirmed_conversion_rate) }}</dd>
            </div>
          </dl>
        }

        <div class="filtro">
          <label for="registros-filtro-estado">
            {{ t('admin.events.registrations.filtrarPorEstado') }}
          </label>
          <select
            id="registros-filtro-estado"
            [value]="estadoFiltro()"
            (change)="alCambiarEstado($event)"
          >
            <option value="">{{ t('admin.events.registrations.estadoTodos') }}</option>
            @for (estado of estadosDisponibles; track estado) {
              <option [value]="estado">
                {{ t('admin.events.registrations.estado' + claveDeEstado(estado)) }}
              </option>
            }
          </select>
        </div>

        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (accionError(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (items().length === 0) {
          <p>{{ t('admin.events.registrations.sinInscripciones') }}</p>
        } @else {
          <table>
            <thead>
              <tr>
                <th scope="col">{{ t('admin.events.registrations.columnaEmail') }}</th>
                <th scope="col">{{ t('admin.events.registrations.columnaNombre') }}</th>
                <th scope="col">{{ t('admin.events.registrations.columnaEstado') }}</th>
                <th scope="col">{{ t('admin.events.registrations.columnaFecha') }}</th>
                <th scope="col">{{ t('admin.events.registrations.columnaAcciones') }}</th>
              </tr>
            </thead>
            <tbody>
              @for (item of items(); track item.id) {
                <tr>
                  <td>
                    <a [routerLink]="['/admin/events', eventId(), 'registrations', item.id]">
                      {{ item.email }}
                    </a>
                  </td>
                  <td>{{ item.full_name }}</td>
                  <td>
                    <code>{{
                      t('admin.events.registrations.estado' + claveDeEstado(item.status))
                    }}</code>
                  </td>
                  <td>{{ item.created_at | date: 'short' }}</td>
                  <td class="acciones">
                    @if (item.status === 'pending_approval') {
                      <app-button
                        variant="secundario"
                        type="button"
                        [loading]="accionPendiente() === item.id"
                        (pulsado)="aprobar(item.id)"
                      >
                        {{ t('admin.events.registrations.aprobar') }}
                      </app-button>
                      <app-button
                        variant="peligro"
                        type="button"
                        [loading]="accionPendiente() === item.id"
                        (pulsado)="rechazar(item.id)"
                      >
                        {{ t('admin.events.registrations.rechazar') }}
                      </app-button>
                    }
                    @if (item.status !== 'cancelled' && item.status !== 'rejected') {
                      <app-button
                        variant="peligro"
                        type="button"
                        [loading]="accionPendiente() === item.id"
                        (pulsado)="cancelar(item.id)"
                      >
                        {{ t('admin.events.registrations.cancelar') }}
                      </app-button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>

          @if (totalPaginas() > 1) {
            <nav [attr.aria-label]="t('admin.events.registrations.titulo')" class="paginacion">
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
      </app-card>

      <app-registration-questions [eventId]="eventId()" />
    </ng-container>
  `,
  styles: `
    .estadisticas {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
      gap: var(--space-md);
      margin: 0 0 var(--space-md);
    }
    .estadisticas dt {
      font-size: 0.8125rem;
      color: var(--color-text-muted, #6b7280);
    }
    .estadisticas dd {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 600;
    }
    .filtro {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin-bottom: var(--space-md);
    }
    .filtro select {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th,
    td {
      text-align: left;
      padding: var(--space-sm) var(--space-md);
      border-bottom: 1px solid var(--color-border);
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
      margin-top: var(--space-md);
    }
  `,
})
export class EventRegistrations implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly estadosDisponibles = ESTADOS_DE_INSCRIPCION;
  protected readonly claveDeEstado = claveDeEstado;
  protected readonly limite = LIMITE;

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly items = signal<RegistrationListItem[]>([]);
  protected readonly total = signal(0);
  protected readonly offset = signal(0);
  protected readonly estadoFiltro = signal<RegistrationStatus | ''>('');

  protected readonly stats = signal<RegistrationStats | null>(null);
  protected readonly statsError = signal<string | null>(null);

  protected readonly accionPendiente = signal<string | null>(null);
  protected readonly accionError = signal<string | null>(null);

  protected readonly totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / LIMITE)));
  protected readonly paginaActual = computed(() => Math.floor(this.offset() / LIMITE) + 1);

  ngOnInit(): void {
    void this.cargar();
    void this.cargarEstadisticas();
  }

  protected formatearTasa(valor: number | null): string {
    if (valor === null) {
      return '—';
    }
    return `${(valor * 100).toFixed(1)}%`;
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

  protected alCambiarEstado(evento: Event): void {
    this.estadoFiltro.set((evento.target as HTMLSelectElement).value as RegistrationStatus | '');
    this.offset.set(0);
    void this.cargar();
  }

  protected irAPagina(nuevoOffset: number): void {
    this.offset.set(Math.max(0, nuevoOffset));
    void this.cargar();
  }

  private async ejecutarAccion(id: string, accion: 'approve' | 'reject' | 'cancel'): Promise<void> {
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

  protected rechazar(id: string): void {
    void this.ejecutarAccion(id, 'reject');
  }

  protected cancelar(id: string): void {
    void this.ejecutarAccion(id, 'cancel');
  }
}
