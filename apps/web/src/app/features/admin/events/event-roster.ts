import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
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
import { Card } from '../../../shared/ui/card';

interface Persona {
  readonly first_name: string | null;
  readonly last_name: string | null;
  readonly email: string;
}

export interface RosterMember extends Persona {
  readonly id: string;
  readonly organization_member_id: string;
  readonly role_key: string;
}

interface OrganizationMemberOption extends Persona {
  readonly id: string;
  readonly role_key: string;
}

interface Page<T> {
  readonly items: readonly T[];
}

/**
 * Roster de personas del evento (ponentes, moderadores y demás miembros):
 * alta desde los miembros de la organización, baja y listado.
 *
 * Vive aparte del editor de agenda porque no comparte estado con él: la
 * agenda solo necesita el roster para el editor de participantes de cada
 * sesión, así que lo emite por `cambio` en vez de obligar a su padre a
 * duplicar la carga y las cuatro operaciones de escritura.
 */
@Component({
  selector: 'app-event-roster',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.roster.titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (roster().length === 0) {
          <p>{{ t('admin.events.roster.sinPersonas') }}</p>
        } @else {
          <ul class="roster">
            @for (persona of roster(); track persona.id) {
              <li>
                <span
                  >{{ nombreDe(persona) }} · <code>{{ persona.role_key }}</code></span
                >
                <app-button variant="peligro" type="button" (pulsado)="quitar(persona.id)">
                  {{ t('admin.events.roster.quitar') }}
                </app-button>
              </li>
            }
          </ul>
        }
        <div class="anadir-roster">
          <label for="roster-anadir" class="sr-only">
            {{ t('admin.events.roster.elegirPersona') }}
          </label>
          <select
            id="roster-anadir"
            [value]="miembroAAnadir()"
            (change)="alCambiarMiembroAAnadir($event)"
          >
            <option value="">{{ t('admin.events.roster.elegirPersona') }}</option>
            @for (miembro of miembrosDisponibles(); track miembro.id) {
              <option [value]="miembro.id">{{ nombreDe(miembro) }} ({{ miembro.role_key }})</option>
            }
          </select>
          <app-button
            type="button"
            [disabled]="!miembroAAnadir()"
            [loading]="anadiendo()"
            (pulsado)="anadir()"
          >
            {{ t('admin.events.roster.anadir') }}
          </app-button>
        </div>
      </app-card>
    </ng-container>
  `,
  styles: `
    .roster {
      list-style: none;
      margin: 0 0 var(--space-md);
      padding: 0;
      display: grid;
      gap: var(--space-sm);
    }
    .roster li {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: var(--space-md);
      border-bottom: 1px solid var(--border);
      padding-bottom: var(--space-sm);
    }
    .anadir-roster {
      display: flex;
      gap: var(--space-sm);
      align-items: center;
      flex-wrap: wrap;
    }
    .anadir-roster select {
      flex: 1;
      min-width: 12rem;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      color: var(--fg);
      font: inherit;
    }
  `,
})
export class EventRoster implements OnInit {
  readonly eventId = input.required<string>();

  /** El roster vigente, para quien necesite sus personas (el editor de participantes). */
  readonly cambio = output<readonly RosterMember[]>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly roster = signal<RosterMember[]>([]);
  protected readonly organizationMembers = signal<OrganizationMemberOption[]>([]);
  protected readonly miembroAAnadir = signal('');
  protected readonly anadiendo = signal(false);
  protected readonly nombreDe = displayName;

  protected readonly miembrosDisponibles = computed(() => {
    const yaEnRoster = new Set(this.roster().map((m) => m.organization_member_id));
    return this.organizationMembers().filter((m) => !yaEnRoster.has(m.id));
  });

  ngOnInit(): void {
    void this.cargarRoster();
    void this.cargarMiembrosDeLaOrganizacion();
  }

  protected alCambiarMiembroAAnadir(evento: Event): void {
    this.miembroAAnadir.set((evento.target as HTMLSelectElement).value);
  }

  protected async anadir(): Promise<void> {
    const organizationMemberId = this.miembroAAnadir();
    if (!organizationMemberId) {
      return;
    }
    this.error.set(null);
    this.anadiendo.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/events/${this.eventId()}/members`), {
          organization_member_id: organizationMemberId,
        }),
      );
      this.miembroAAnadir.set('');
      await this.cargarRoster();
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.anadiendo.set(false);
    }
  }

  protected async quitar(eventMemberId: string): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/members/${eventMemberId}`)),
      );
      await this.cargarRoster();
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    }
  }

  private async cargarRoster(): Promise<void> {
    try {
      const roster = await firstValueFrom(
        this.http.get<RosterMember[]>(this.api.url(`/events/${this.eventId()}/members`)),
      );
      this.roster.set([...roster]);
      this.cambio.emit(this.roster());
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.cargando.set(false);
    }
  }

  private async cargarMiembrosDeLaOrganizacion(): Promise<void> {
    try {
      const pagina = await firstValueFrom(
        this.http.get<Page<OrganizationMemberOption>>(this.api.url('/organizations/me/members'), {
          params: { limit: 200, offset: 0 },
        }),
      );
      this.organizationMembers.set([...pagina.items]);
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    }
  }

  private mensajeDeError(error: unknown): string {
    return error instanceof ApiError
      ? error.message
      : this.transloco.translate('admin.events.roster.error');
  }
}
