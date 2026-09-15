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
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { PageHeader } from '../../../shared/ui/page-header';
import { isoAValorLocal } from './datetime-local';
import { EventRoster, type RosterMember } from './event-roster';
import { SessionForm, type EventSession } from './session-form';
import { SessionParticipants } from './session-participants';

interface DiaDeAgenda {
  readonly fecha: string;
  readonly sesiones: readonly EventSession[];
}

/**
 * Agenda de un evento: listado de sesiones agrupadas por día (a partir de
 * `starts_at`, nunca un campo `day` aparte, para que no se pueda desincronizar
 * del horario real), con el alta y la edición en el formulario y la gestión de
 * participantes por sesión.
 *
 * Este componente compone tres piezas con estado propio —el roster del evento,
 * el listado con sus participantes y el formulario de sesión—; cada una vive
 * en su fichero para que ninguna arrastre el estado de las demás.
 */
@Component({
  selector: 'app-event-agenda',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, DatePipe, Alert, Button, Card, EventRoster, SessionForm, SessionParticipants, PageHeader],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.events.agenda.titulo')">
        {{ t('admin.events.agenda.cabeceraInicio') }}
        <span class="mark">{{ t('admin.events.agenda.cabeceraMarca') }}</span>
      </app-page-header>

      <app-event-roster [eventId]="eventId()" (cambio)="alCambiarRoster($event)" />

      <app-card [heading]="t('admin.events.agenda.titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (dias().length === 0) {
          <p>{{ t('admin.events.agenda.sinSesiones') }}</p>
        } @else {
          @for (dia of dias(); track dia.fecha) {
            <h3>{{ dia.fecha + 'T00:00:00' | date: 'fullDate' }}</h3>
            <ul class="sesiones">
              @for (sesion of dia.sesiones; track sesion.id) {
                <li>
                  <div class="fila">
                    <div>
                      <strong>{{ sesion.title }}</strong>
                      <span class="detalle">
                        {{ sesion.starts_at | date: 'shortTime' }} –
                        {{ sesion.ends_at | date: 'shortTime' }}
                        @if (sesion.room) {
                          · {{ sesion.room }}
                        }
                      </span>
                    </div>
                    <div class="acciones">
                      <app-button variant="secundario" type="button" (pulsado)="editar(sesion)">
                        {{ t('admin.events.agenda.editar') }}
                      </app-button>
                      <app-button
                        variant="secundario"
                        type="button"
                        (pulsado)="alternarParticipantes(sesion)"
                      >
                        {{ t('admin.events.agenda.participantes.gestionar') }}
                      </app-button>
                      <app-button variant="peligro" type="button" (pulsado)="borrar(sesion.id)">
                        {{ t('admin.events.agenda.eliminar') }}
                      </app-button>
                    </div>
                  </div>

                  @if (editandoParticipantesId() === sesion.id) {
                    <app-session-participants
                      [eventId]="eventId()"
                      [sessionId]="sesion.id"
                      [updatedAt]="sesion.updated_at"
                      [roster]="roster()"
                      (guardado)="alGuardarParticipantes()"
                    />
                  }
                </li>
              }
            </ul>
          }
        }

        <app-session-form
          #formulario
          [eventId]="eventId()"
          [sesion]="sesionEnEdicion()"
          (guardada)="alGuardarSesion()"
          (cancelada)="sesionEnEdicion.set(null)"
        />
      </app-card>
    </ng-container>
  `,
  styles: `
    h3 {
      margin: var(--space-md) 0 var(--space-xs);
    }
    .sesiones {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-sm);
    }
    .sesiones li {
      border-bottom: 1px solid var(--border);
      padding-bottom: var(--space-sm);
    }
    .fila {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    .detalle {
      display: block;
      color: var(--muted);
      font-size: 0.875rem;
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
    }
  `,
})
export class EventAgenda implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly formulario = viewChild<SessionForm>('formulario');

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly sesiones = signal<EventSession[]>([]);
  protected readonly sesionEnEdicion = signal<EventSession | null>(null);
  protected readonly roster = signal<readonly RosterMember[]>([]);
  protected readonly editandoParticipantesId = signal<string | null>(null);

  protected readonly dias = computed<DiaDeAgenda[]>(() => {
    const grupos = new Map<string, EventSession[]>();
    for (const sesion of this.sesiones()) {
      const fecha = isoAValorLocal(sesion.starts_at).slice(0, 10);
      const lista = grupos.get(fecha) ?? [];
      lista.push(sesion);
      grupos.set(fecha, lista);
    }
    return [...grupos.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([fecha, sesiones]) => ({ fecha, sesiones }));
  });

  ngOnInit(): void {
    void this.cargar();
  }

  protected alCambiarRoster(roster: readonly RosterMember[]): void {
    this.roster.set(roster);
  }

  protected editar(sesion: EventSession): void {
    this.sesionEnEdicion.set(sesion);
    this.formulario()?.cargarSesion(sesion);
  }

  protected alGuardarSesion(): void {
    this.sesionEnEdicion.set(null);
    void this.cargar();
  }

  protected alGuardarParticipantes(): void {
    this.editandoParticipantesId.set(null);
    void this.cargar();
  }

  protected alternarParticipantes(sesion: EventSession): void {
    this.editandoParticipantesId.set(
      this.editandoParticipantesId() === sesion.id ? null : sesion.id,
    );
  }

  protected async borrar(sessionId: string): Promise<void> {
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/sessions/${sessionId}`)),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    }
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const sesiones = await firstValueFrom(
        this.http.get<EventSession[]>(this.api.url(`/events/${this.eventId()}/sessions`)),
      );
      this.sesiones.set([...sesiones]);
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.cargando.set(false);
    }
  }

  private mensajeDeError(error: unknown): string {
    return error instanceof ApiError
      ? error.message
      : this.transloco.translate('admin.events.agenda.error');
  }
}
