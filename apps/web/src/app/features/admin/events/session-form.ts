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
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Input } from '../../../shared/ui/input';
import { Select, type SelectOption } from '../../../shared/ui/select';
import { capitalizarClaveDeTraduccion } from '../../../shared/text/capitalizar-clave-de-traduccion';
import { isoAValorLocal } from './datetime-local';

export type SessionType = 'talk' | 'break' | 'service' | 'other';
type VideoPlatform = '' | 'youtube' | 'vimeo' | 'twitch' | 'other';

export interface EventSession {
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
  readonly venue_id: string | null;
  readonly updated_at: string;
}

interface EventVenueOption {
  readonly id: string;
  readonly name: string;
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
 * Formulario de alta y edición de una sesión de la agenda.
 *
 * Tiene todo su estado propio (los ocho campos, la sesión en edición y las
 * sedes del evento), por eso vive aparte del listado y le devuelve el
 * resultado por `guardada` para que el listado recargue.
 */
@Component({
  selector: 'app-session-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Input, Select],
  template: `
    <ng-container *transloco="let t">
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
        <app-input fieldId="sesion-sala" [label]="t('admin.events.agenda.sala')" [(value)]="sala" />

        @if (sedes().length > 0) {
          <app-select
            fieldId="sesion-sede"
            [label]="t('admin.events.agenda.sede')"
            [options]="opcionesDeSede()"
            [(value)]="venueId"
          />
        }

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
            <app-button variant="secundario" type="button" (pulsado)="cancelar()">
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
    </ng-container>
  `,
  styles: `
    .formulario {
      display: grid;
      gap: var(--space-md);
      margin-top: var(--space-lg);
      padding-top: var(--space-lg);
      border-top: 1px solid var(--border);
    }
    h3 {
      margin: 0;
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
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      color: var(--fg);
      font: inherit;
    }
    .ayuda {
      margin: 0;
      color: var(--muted);
      font-size: 0.8125rem;
    }
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class SessionForm implements OnInit {
  readonly eventId = input.required<string>();
  /** La sesión a editar, o `null` para el alta. */
  readonly sesion = input<EventSession | null>(null);

  readonly guardada = output<void>();
  readonly cancelada = output<void>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly tiposDisponibles = SESSION_TYPES;
  protected readonly guardando = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly sedes = signal<EventVenueOption[]>([]);

  private readonly valoresIniciales = vacio();
  protected readonly tipo = signal(this.valoresIniciales.session_type);
  protected readonly titulo = signal(this.valoresIniciales.title);
  protected readonly inicio = signal(this.valoresIniciales.starts_at);
  protected readonly fin = signal(this.valoresIniciales.ends_at);
  protected readonly sala = signal(this.valoresIniciales.room);
  protected readonly videoPlatform = signal(this.valoresIniciales.video_platform);
  protected readonly videoUrl = signal(this.valoresIniciales.video_url);
  protected readonly materiales = signal(this.valoresIniciales.materiales);
  protected readonly venueId = signal('');

  protected readonly opcionesDeSede = computed<SelectOption[]>(() => [
    { value: '', label: this.transloco.translate('admin.events.agenda.sinSedeEspecifica') },
    ...this.sedes().map((sede) => ({ value: sede.id, label: sede.name })),
  ]);

  constructor() {
    // Las sedes se piden en `ngOnInit`, no en el constructor: los `input.required`
    // (en particular `eventId`) todavía no están enlazados al construir el
    // componente, así que una petición aquí saldría con la URL a medio formar.
  }

  ngOnInit(): void {
    void this.cargarSedes();
  }

  /** La sesión en edición, si la hay: quien consume lee esto, no el input crudo. */
  protected readonly editandoId = computed(() => this.sesion()?.id ?? null);

  /** Rellena el formulario con la sesión recibida; el padre lo llama al editar. */
  cargarSesion(sesion: EventSession | null): void {
    this.formError.set(null);
    if (!sesion) {
      this.limpiar();
      return;
    }
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
    this.venueId.set(sesion.venue_id ?? '');
  }

  protected cancelar(): void {
    this.limpiar();
    this.cancelada.emit();
  }

  protected capitaliza(valor: string): string {
    return capitalizarClaveDeTraduccion(valor);
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
      venue_id: this.venueId() || null,
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
      this.limpiar();
      this.guardada.emit();
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

  private limpiar(): void {
    const vacios = vacio();
    this.tipo.set(vacios.session_type);
    this.titulo.set(vacios.title);
    this.inicio.set(vacios.starts_at);
    this.fin.set(vacios.ends_at);
    this.sala.set(vacios.room);
    this.videoPlatform.set(vacios.video_platform);
    this.videoUrl.set(vacios.video_url);
    this.materiales.set(vacios.materiales);
    this.venueId.set('');
    this.formError.set(null);
  }

  private materialesComoLista(): { url: string }[] {
    return this.materiales()
      .split('\n')
      .map((linea) => linea.trim())
      .filter((linea) => linea.length > 0)
      .map((url) => ({ url }));
  }

  private async cargarSedes(): Promise<void> {
    try {
      const sedes = await firstValueFrom(
        this.http.get<EventVenueOption[]>(this.api.url(`/events/${this.eventId()}/venues`)),
      );
      this.sedes.set([...sedes]);
    } catch {
      // Sin sedes cargadas, el selector de sede simplemente no aparece: el resto
      // del editor de agenda sigue funcionando igual.
    }
  }
}
