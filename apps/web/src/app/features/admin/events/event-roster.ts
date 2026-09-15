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
import { Input } from '../../../shared/ui/input';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface InvitationCreateResponse {
  readonly status: 'added' | 'invited';
}

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

/** Un rol concreto de una persona, tal y como lo agrupa `GET
 * /organizations/me/members` desde la fase 4 del plan de invitaciones. */
interface GroupedMemberRole {
  readonly id: string;
  readonly role_key: string;
}

interface GroupedMember extends Persona {
  readonly roles: readonly GroupedMemberRole[];
}

interface Page<T> {
  readonly items: readonly T[];
  readonly total: number;
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
  imports: [TranslocoDirective, Alert, Button, Card, Input],
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

        <p class="separador">{{ t('admin.events.roster.oInvitar') }}</p>

        @if (mensajeInvitar(); as texto) {
          <app-alert tone="exito">{{ texto }}</app-alert>
        }
        <form (submit)="invitarPonente($event)" novalidate class="invitar-ponente">
          <app-input
            fieldId="roster-invitar-email"
            [label]="t('admin.events.roster.invitarEmail')"
            type="email"
            autocomplete="email"
            [required]="true"
            [error]="errorInviteEmail()"
            [(value)]="inviteEmail"
          />
          <app-button type="submit" [loading]="invitando()">
            {{
              invitando() ? t('admin.events.roster.invitando') : t('admin.events.roster.invitar')
            }}
          </app-button>
        </form>
        <p class="ayuda-invitar">{{ t('admin.events.roster.invitarAyuda') }}</p>
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
      /* La pintura del control la da la regla compartida de styles.css. */
      flex: 1;
      min-width: 12rem;
    }
    .separador {
      margin: var(--space-md) 0 0;
      color: var(--muted);
      font-size: var(--fs-label);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .invitar-ponente {
      display: flex;
      align-items: flex-end;
      gap: var(--space-sm);
      flex-wrap: wrap;
    }
    .ayuda-invitar {
      margin: 0;
      color: var(--muted);
      font-size: 0.875rem;
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

  protected readonly inviteEmail = signal('');
  protected readonly errorInviteEmail = signal<string | null>(null);
  protected readonly invitando = signal(false);
  protected readonly mensajeInvitar = signal<string | null>(null);

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

  protected async invitarPonente(evento: Event): Promise<void> {
    evento.preventDefault();
    this.mensajeInvitar.set(null);

    const email = this.inviteEmail().trim();
    this.errorInviteEmail.set(
      !email
        ? this.transloco.translate('admin.events.roster.invitarEmailRequerido')
        : !EMAIL_RE.test(email)
          ? this.transloco.translate('admin.events.roster.invitarEmailInvalido')
          : null,
    );
    if (this.errorInviteEmail()) {
      return;
    }

    this.invitando.set(true);
    try {
      const respuesta = await firstValueFrom(
        this.http.post<InvitationCreateResponse>(
          this.api.url(`/events/${this.eventId()}/invitations`),
          { email },
        ),
      );
      this.inviteEmail.set('');
      this.mensajeInvitar.set(
        this.transloco.translate(
          respuesta.status === 'added'
            ? 'admin.events.roster.invitarAnadidoDirectamente'
            : 'admin.events.roster.invitarEnviada',
        ),
      );
      if (respuesta.status === 'added') {
        await this.cargarRoster();
      }
    } catch (error) {
      this.errorInviteEmail.set(this.mensajeDeError(error));
    } finally {
      this.invitando.set(false);
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
      // El selector necesita a toda la organización, así que se paginan las
      // peticiones hasta agotar (el backend limita cada página a 100).
      const personas: GroupedMember[] = [];
      let offset = 0;
      for (;;) {
        const pagina = await firstValueFrom(
          this.http.get<Page<GroupedMember>>(this.api.url('/organizations/me/members'), {
            params: { limit: 100, offset },
          }),
        );
        personas.push(...pagina.items);
        offset += pagina.items.length;
        if (personas.length >= pagina.total || pagina.items.length === 0) {
          break;
        }
      }
      // Cada persona trae **todos** sus roles en un solo elemento — se
      // despliega de vuelta a una opción por (persona, rol), que es lo que
      // necesita este selector: añadir a alguien al roster es añadir una
      // membresía concreta, no a la persona en abstracto.
      const opciones: OrganizationMemberOption[] = [];
      for (const persona of personas) {
        for (const rol of persona.roles) {
          opciones.push({
            id: rol.id,
            role_key: rol.role_key,
            first_name: persona.first_name,
            last_name: persona.last_name,
            email: persona.email,
          });
        }
      }
      this.organizationMembers.set(opciones);
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
