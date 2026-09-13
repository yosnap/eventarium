import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { displayName } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Input } from '../../../shared/ui/input';
import type { RosterMember } from './event-roster';

interface SessionParticipant {
  readonly id: string;
  readonly event_member_id: string;
  readonly role_key: string;
}

/**
 * Editor de los participantes de una sesión concreta: qué miembros del roster
 * intervienen y con qué roles (separados por comas).
 *
 * Se abre en línea desde el listado de sesiones y solo tiene estado propio
 * (los roles por persona mientras el editor está abierto), por eso vive
 * aparte del editor de agenda.
 */
@Component({
  selector: 'app-session-participants',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Input],
  template: `
    <ng-container *transloco="let t">
      <div class="participantes-editor">
        @if (roster().length === 0) {
          <p>{{ t('admin.events.agenda.participantes.sinRoster') }}</p>
        } @else {
          @for (persona of roster(); track persona.id) {
            <app-input
              [fieldId]="'participante-' + sessionId() + '-' + persona.id"
              [label]="nombreDe(persona)"
              [hint]="t('admin.events.agenda.participantes.rolesAyuda')"
              [value]="rolesDePersona()[persona.id] || ''"
              (valueChange)="fijarRolesDePersona(persona.id, $event)"
            />
          }
        }
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        <app-button type="button" [loading]="guardando()" (pulsado)="guardar()">
          {{ t('admin.events.agenda.participantes.guardar') }}
        </app-button>
      </div>
    </ng-container>
  `,
  styles: `
    .participantes-editor {
      display: grid;
      gap: var(--space-sm);
      margin-top: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      background-color: var(--surface-2);
      border-radius: var(--radius-md);
    }
  `,
})
export class SessionParticipants implements OnInit {
  readonly eventId = input.required<string>();
  readonly sessionId = input.required<string>();
  /** La versión de la sesión que se está editando, para el control optimista. */
  readonly updatedAt = input.required<string>();
  readonly roster = input.required<readonly RosterMember[]>();

  /** Se emite cuando hay que recargar la agenda (guardado correcto o conflicto). */
  readonly guardado = output<void>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly rolesDePersona = signal<Record<string, string>>({});
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly nombreDe = displayName;

  constructor() {
    // El editor se monta solo cuando su sesión está desplegada, así que sus
    // `input.required` ya están enlazados al inicializarse: la carga puede ir
    // en `ngOnInit` sin riesgo de pedir con la URL a medio formar.
  }

  ngOnInit(): void {
    void this.cargar();
  }

  protected fijarRolesDePersona(eventMemberId: string, valor: string): void {
    this.rolesDePersona.set({ ...this.rolesDePersona(), [eventMemberId]: valor });
  }

  protected async guardar(): Promise<void> {
    this.error.set(null);
    this.guardando.set(true);
    try {
      await firstValueFrom(
        this.http.put(
          this.api.url(`/events/${this.eventId()}/sessions/${this.sessionId()}/participants`),
          {
            expected_updated_at: this.updatedAt(),
            participants: this.comoLista(),
          },
        ),
      );
      this.guardado.emit();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // La agenda cambió desde que se abrió el editor: se recarga en vez de
        // reintentar a ciegas, para no pisar el trabajo de otra persona.
        this.guardado.emit();
      }
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.agenda.participantes.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  private async cargar(): Promise<void> {
    try {
      const participantes = await firstValueFrom(
        this.http.get<SessionParticipant[]>(
          this.api.url(`/events/${this.eventId()}/sessions/${this.sessionId()}/participants`),
        ),
      );
      const porPersona = new Map<string, string[]>();
      for (const participante of participantes) {
        const lista = porPersona.get(participante.event_member_id) ?? [];
        lista.push(participante.role_key);
        porPersona.set(participante.event_member_id, lista);
      }
      this.rolesDePersona.set(
        Object.fromEntries([...porPersona.entries()].map(([id, roles]) => [id, roles.join(', ')])),
      );
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.agenda.participantes.error'),
      );
    }
  }

  private comoLista(): { event_member_id: string; role_key: string }[] {
    const entradas: { event_member_id: string; role_key: string }[] = [];
    for (const [eventMemberId, valor] of Object.entries(this.rolesDePersona())) {
      const roles = valor
        .split(',')
        .map((rol) => rol.trim())
        .filter((rol) => rol.length > 0);
      for (const role_key of new Set(roles)) {
        entradas.push({ event_member_id: eventMemberId, role_key });
      }
    }
    return entradas;
  }
}
