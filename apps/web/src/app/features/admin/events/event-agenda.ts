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
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { displayName } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { isoAValorLocal } from './datetime-local';

type SessionType = 'talk' | 'break' | 'service' | 'other';
type VideoPlatform = '' | 'youtube' | 'vimeo' | 'twitch' | 'other';

interface EventSession {
  readonly id: string;
  readonly session_type: SessionType;
  readonly title: string;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly room: string | null;
  readonly video_platform: string | null;
  readonly video_url: string | null;
  readonly materials: readonly { url?: string }[];
  readonly sort_order: number;
  readonly updated_at: string;
}

interface Persona {
  readonly first_name: string | null;
  readonly last_name: string | null;
  readonly email: string;
}

interface RosterMember extends Persona {
  readonly id: string;
  readonly organization_member_id: string;
  readonly role_key: string;
}

interface OrganizationMemberOption extends Persona {
  readonly id: string;
  readonly role_key: string;
}

interface SessionParticipant extends Persona {
  readonly id: string;
  readonly event_member_id: string;
  readonly role_key: string;
}

interface Page<T> {
  readonly items: readonly T[];
}

interface DiaDeAgenda {
  readonly fecha: string;
  readonly sesiones: readonly EventSession[];
}

const SESSION_TYPES: readonly SessionType[] = ['talk', 'break', 'service', 'other'];

function vacio(): {
  session_type: SessionType;
  title: string;
  starts_at: string;
  ends_at: string;
  room: string;
  video_platform: VideoPlatform;
  video_url: string;
  materiales: string;
} {
  return {
    session_type: 'talk',
    title: '',
    starts_at: '',
    ends_at: '',
    room: '',
    video_platform: '',
    video_url: '',
    materiales: '',
  };
}

/**
 * Editor de la agenda de un evento: alta, edición y eliminación de sesiones,
 * agrupadas por día a partir de `starts_at` (nunca un campo `day` aparte, para
 * que no se pueda desincronizar del horario real).
 */
@Component({
  selector: 'app-event-agenda',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, DatePipe, Alert, Button, Card, Input],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.roster.titulo')">
        @if (rosterError(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (roster().length === 0) {
          <p>{{ t('admin.events.roster.sinPersonas') }}</p>
        } @else {
          <ul class="roster">
            @for (persona of roster(); track persona.id) {
              <li>
                <span
                  >{{ nombreDe(persona) }} · <code>{{ persona.role_key }}</code></span
                >
                <app-button variant="peligro" type="button" (pulsado)="quitarDelRoster(persona.id)">
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
            [loading]="anadiendoAlRoster()"
            (pulsado)="anadirAlRoster()"
          >
            {{ t('admin.events.roster.anadir') }}
          </app-button>
        </div>
      </app-card>

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
                    <div class="participantes-editor">
                      @if (roster().length === 0) {
                        <p>{{ t('admin.events.agenda.participantes.sinRoster') }}</p>
                      } @else {
                        @for (persona of roster(); track persona.id) {
                          <app-input
                            [fieldId]="'participante-' + sesion.id + '-' + persona.id"
                            [label]="nombreDe(persona)"
                            [hint]="t('admin.events.agenda.participantes.rolesAyuda')"
                            [value]="rolesDePersona()[persona.id] ?? ''"
                            (valueChange)="fijarRolesDePersona(persona.id, $event)"
                          />
                        }
                      }
                      @if (participantesError(); as mensaje) {
                        <app-alert tone="error">{{ mensaje }}</app-alert>
                      }
                      <app-button
                        type="button"
                        [loading]="guardandoParticipantes()"
                        (pulsado)="guardarParticipantes(sesion)"
                      >
                        {{ t('admin.events.agenda.participantes.guardar') }}
                      </app-button>
                    </div>
                  }
                </li>
              }
            </ul>
          }
        }

        <form (submit)="guardar($event)" novalidate class="formulario">
          <h3>
            {{
              editandoId()
                ? t('admin.events.agenda.editarSesion')
                : t('admin.events.agenda.anadirSesion')
            }}
          </h3>

          <div class="campo-select">
            <label for="sesion-tipo">{{ t('admin.events.agenda.tipo') }}</label>
            <select id="sesion-tipo" [value]="tipo()" (change)="alCambiarTipo($event)">
              @for (opcion of tiposDisponibles; track opcion) {
                <option [value]="opcion">
                  {{ t('admin.events.agenda.tipo' + capitaliza(opcion)) }}
                </option>
              }
            </select>
          </div>

          <app-input
            fieldId="sesion-titulo"
            [label]="t('admin.events.agenda.tituloSesion')"
            [required]="true"
            [(value)]="titulo"
          />
          <app-input
            fieldId="sesion-inicio"
            type="datetime-local"
            [label]="t('admin.events.agenda.inicio')"
            [required]="true"
            [(value)]="inicio"
          />
          <app-input
            fieldId="sesion-fin"
            type="datetime-local"
            [label]="t('admin.events.agenda.fin')"
            [required]="true"
            [(value)]="fin"
          />
          <app-input
            fieldId="sesion-sala"
            [label]="t('admin.events.agenda.sala')"
            [(value)]="sala"
          />

          <div class="campo-select">
            <label for="sesion-video">{{ t('admin.events.agenda.plataformaVideo') }}</label>
            <select
              id="sesion-video"
              [value]="videoPlatform()"
              (change)="alCambiarVideoPlatform($event)"
            >
              <option value="">{{ t('admin.events.agenda.sinVideo') }}</option>
              <option value="youtube">YouTube</option>
              <option value="vimeo">Vimeo</option>
              <option value="twitch">Twitch</option>
              <option value="other">{{ t('admin.events.agenda.otraPlataforma') }}</option>
            </select>
          </div>
          @if (videoPlatform()) {
            <app-input
              fieldId="sesion-video-url"
              type="url"
              [label]="t('admin.events.agenda.enlaceVideo')"
              [(value)]="videoUrl"
            />
          }

          <div class="campo-materiales">
            <label for="sesion-materiales">{{ t('admin.events.agenda.materiales') }}</label>
            <textarea
              id="sesion-materiales"
              rows="3"
              [value]="materiales()"
              (input)="materiales.set(alTextarea($event))"
            ></textarea>
            <p class="ayuda">{{ t('admin.events.agenda.materialesAyuda') }}</p>
          </div>

          @if (formError(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <div class="acciones-finales">
            @if (editandoId()) {
              <app-button variant="secundario" type="button" (pulsado)="cancelarEdicion()">
                {{ t('admin.roles.cancelar') }}
              </app-button>
            }
            <app-button type="submit" [loading]="guardando()">
              {{
                editandoId()
                  ? t('admin.events.agenda.guardarCambios')
                  : t('admin.events.agenda.anadirSesion')
              }}
            </app-button>
          </div>
        </form>
      </app-card>
    </ng-container>
  `,
  styles: `
    h3 {
      margin: var(--space-md) 0 var(--space-xs);
    }
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
      border-bottom: 1px solid var(--color-border);
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
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    .participantes-editor {
      display: grid;
      gap: var(--space-sm);
      margin-top: var(--space-sm);
      padding: var(--space-sm) var(--space-md);
      background-color: var(--color-surface-muted, rgba(0, 0, 0, 0.03));
      border-radius: var(--radius-md);
    }
    .sesiones {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-sm);
    }
    .sesiones li {
      border-bottom: 1px solid var(--color-border);
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
      color: var(--color-text-muted, #6b7280);
      font-size: 0.875rem;
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      margin-top: var(--space-lg);
      padding-top: var(--space-lg);
      border-top: 1px solid var(--color-border);
    }
    .campo-select,
    .campo-materiales {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select,
    textarea {
      width: 100%;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
    }
    .ayuda {
      margin: 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.8125rem;
    }
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class EventAgenda implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly tiposDisponibles = SESSION_TYPES;

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly sesiones = signal<EventSession[]>([]);
  protected readonly editandoId = signal<string | null>(null);
  protected readonly nombreDe = displayName;

  protected readonly roster = signal<RosterMember[]>([]);
  protected readonly rosterError = signal<string | null>(null);
  protected readonly organizationMembers = signal<OrganizationMemberOption[]>([]);
  protected readonly miembroAAnadir = signal('');
  protected readonly anadiendoAlRoster = signal(false);
  protected readonly miembrosDisponibles = computed(() => {
    const yaEnRoster = new Set(this.roster().map((m) => m.organization_member_id));
    return this.organizationMembers().filter((m) => !yaEnRoster.has(m.id));
  });

  protected readonly editandoParticipantesId = signal<string | null>(null);
  protected readonly rolesDePersona = signal<Record<string, string>>({});
  protected readonly guardandoParticipantes = signal(false);
  protected readonly participantesError = signal<string | null>(null);

  private readonly valoresIniciales = vacio();
  protected readonly tipo = signal(this.valoresIniciales.session_type);
  protected readonly titulo = signal(this.valoresIniciales.title);
  protected readonly inicio = signal(this.valoresIniciales.starts_at);
  protected readonly fin = signal(this.valoresIniciales.ends_at);
  protected readonly sala = signal(this.valoresIniciales.room);
  protected readonly videoPlatform = signal(this.valoresIniciales.video_platform);
  protected readonly videoUrl = signal(this.valoresIniciales.video_url);
  protected readonly materiales = signal(this.valoresIniciales.materiales);

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
    void this.cargarRoster();
    void this.cargarMiembrosDeLaOrganizacion();
  }

  private async cargarRoster(): Promise<void> {
    try {
      const roster = await firstValueFrom(
        this.http.get<RosterMember[]>(this.api.url(`/events/${this.eventId()}/members`)),
      );
      this.roster.set([...roster]);
    } catch (error) {
      this.rosterError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.roster.error'),
      );
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
      this.rosterError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.roster.error'),
      );
    }
  }

  protected alCambiarMiembroAAnadir(evento: Event): void {
    this.miembroAAnadir.set((evento.target as HTMLSelectElement).value);
  }

  protected async anadirAlRoster(): Promise<void> {
    const organizationMemberId = this.miembroAAnadir();
    if (!organizationMemberId) {
      return;
    }
    this.rosterError.set(null);
    this.anadiendoAlRoster.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/events/${this.eventId()}/members`), {
          organization_member_id: organizationMemberId,
        }),
      );
      this.miembroAAnadir.set('');
      await this.cargarRoster();
    } catch (error) {
      this.rosterError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.roster.error'),
      );
    } finally {
      this.anadiendoAlRoster.set(false);
    }
  }

  protected async quitarDelRoster(eventMemberId: string): Promise<void> {
    this.rosterError.set(null);
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/members/${eventMemberId}`)),
      );
      await this.cargarRoster();
    } catch (error) {
      this.rosterError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.roster.error'),
      );
    }
  }

  protected async alternarParticipantes(sesion: EventSession): Promise<void> {
    if (this.editandoParticipantesId() === sesion.id) {
      this.editandoParticipantesId.set(null);
      return;
    }
    this.participantesError.set(null);
    this.editandoParticipantesId.set(sesion.id);
    try {
      const participantes = await firstValueFrom(
        this.http.get<SessionParticipant[]>(
          this.api.url(`/events/${this.eventId()}/sessions/${sesion.id}/participants`),
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
      this.participantesError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.agenda.participantes.error'),
      );
    }
  }

  protected fijarRolesDePersona(eventMemberId: string, valor: string): void {
    this.rolesDePersona.set({ ...this.rolesDePersona(), [eventMemberId]: valor });
  }

  private participantesComoLista(): { event_member_id: string; role_key: string }[] {
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

  protected async guardarParticipantes(sesion: EventSession): Promise<void> {
    this.participantesError.set(null);
    this.guardandoParticipantes.set(true);
    try {
      await firstValueFrom(
        this.http.put(
          this.api.url(`/events/${this.eventId()}/sessions/${sesion.id}/participants`),
          {
            expected_updated_at: sesion.updated_at,
            participants: this.participantesComoLista(),
          },
        ),
      );
      this.editandoParticipantesId.set(null);
      await this.cargar();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // La agenda cambió desde que se abrió el editor: se recarga en vez de
        // reintentar a ciegas, para no pisar el trabajo de otra persona.
        await this.cargar();
      }
      this.participantesError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.agenda.participantes.error'),
      );
    } finally {
      this.guardandoParticipantes.set(false);
    }
  }

  protected capitaliza(valor: string): string {
    return valor.charAt(0).toUpperCase() + valor.slice(1);
  }

  protected alCambiarTipo(evento: Event): void {
    this.tipo.set((evento.target as HTMLSelectElement).value as SessionType);
  }

  protected alCambiarVideoPlatform(evento: Event): void {
    this.videoPlatform.set((evento.target as HTMLSelectElement).value as VideoPlatform);
  }

  protected alTextarea(evento: Event): string {
    return (evento.target as HTMLTextAreaElement).value;
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const sesiones = await firstValueFrom(
        this.http.get<EventSession[]>(this.api.url(`/events/${this.eventId()}/sessions`)),
      );
      this.sesiones.set([...sesiones]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.agenda.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected editar(sesion: EventSession): void {
    this.editandoId.set(sesion.id);
    this.tipo.set(sesion.session_type);
    this.titulo.set(sesion.title);
    this.inicio.set(isoAValorLocal(sesion.starts_at));
    this.fin.set(isoAValorLocal(sesion.ends_at));
    this.sala.set(sesion.room ?? '');
    this.videoPlatform.set((sesion.video_platform ?? '') as VideoPlatform);
    this.videoUrl.set(sesion.video_url ?? '');
    this.materiales.set(
      sesion.materials
        .map((m) => m.url)
        .filter((url): url is string => !!url)
        .join('\n'),
    );
    this.formError.set(null);
  }

  protected cancelarEdicion(): void {
    this.editandoId.set(null);
    const vacios = vacio();
    this.tipo.set(vacios.session_type);
    this.titulo.set(vacios.title);
    this.inicio.set(vacios.starts_at);
    this.fin.set(vacios.ends_at);
    this.sala.set(vacios.room);
    this.videoPlatform.set(vacios.video_platform);
    this.videoUrl.set(vacios.video_url);
    this.materiales.set(vacios.materiales);
    this.formError.set(null);
  }

  private materialesComoLista(): { url: string }[] {
    return this.materiales()
      .split('\n')
      .map((linea) => linea.trim())
      .filter((linea) => linea.length > 0)
      .map((url) => ({ url }));
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.formError.set(null);

    if (!this.titulo().trim() || !this.inicio() || !this.fin()) {
      this.formError.set(this.transloco.translate('admin.events.agenda.camposRequeridos'));
      return;
    }

    const payload = {
      session_type: this.tipo(),
      title: this.titulo().trim(),
      starts_at: new Date(this.inicio()).toISOString(),
      ends_at: new Date(this.fin()).toISOString(),
      room: this.sala().trim() || null,
      video_platform: this.videoPlatform() || null,
      video_url: this.videoPlatform() ? this.videoUrl().trim() || null : null,
      materials: this.materialesComoLista(),
    };

    this.guardando.set(true);
    try {
      const idEnEdicion = this.editandoId();
      if (idEnEdicion) {
        await firstValueFrom(
          this.http.patch(
            this.api.url(`/events/${this.eventId()}/sessions/${idEnEdicion}`),
            payload,
          ),
        );
      } else {
        await firstValueFrom(
          this.http.post(this.api.url(`/events/${this.eventId()}/sessions`), payload),
        );
      }
      this.cancelarEdicion();
      await this.cargar();
    } catch (error) {
      this.formError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.agenda.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  protected async borrar(sessionId: string): Promise<void> {
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/sessions/${sessionId}`)),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.agenda.error'),
      );
    }
  }
}
