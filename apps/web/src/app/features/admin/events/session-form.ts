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
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { DatetimePicker } from '../../../shared/ui/datetime-picker';
import { Input } from '../../../shared/ui/input';
import { Select, type SelectOption } from '../../../shared/ui/select';
import { isoAValorLocal } from './datetime-local';
import { PestanasDeIdioma } from '../../../shared/ui/pestanas-de-idioma';

type VideoPlatform = '' | 'youtube' | 'vimeo' | 'twitch' | 'other';

/** El tipo de una sesión tal y como lo pinta la agenda (`SessionTypeRef`). */
export interface TipoDeSesionRef {
  readonly id: string;
  readonly name: string;
  readonly color: string;
  readonly is_break: boolean;
}

export interface EventSession {
  readonly id: string;
  /** Texto heredado (clave base); el tipo de verdad es `type`. */
  readonly session_type: string;
  readonly type?: TipoDeSesionRef;
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

/** Un tipo del catálogo de la organización, con lo que pide el formulario. */
interface TipoDelCatalogo extends TipoDeSesionRef {
  readonly description: string | null;
  readonly is_active: boolean;
}

function vacio(): {
  session_type: string;
  title: string;
  starts_at: string;
  ends_at: string;
  room: string;
  video_platform: VideoPlatform;
  video_url: string;
  materiales: string;
} {
  return {
    session_type: '',
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
  imports: [
    PestanasDeIdioma,
    TranslocoDirective,
    RouterLink,
    Alert,
    Button,
    DatetimePicker,
    Input,
    Select,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-pestanas-de-idioma tipo="session" [entityId]="editandoId()">
        <form (submit)="guardar($event)" novalidate class="formulario">
          <h3>
            {{
              editandoId()
                ? t('admin.events.agenda.editarSesion')
                : t('admin.events.agenda.anadirSesion')
            }}
          </h3>

          <app-select
            fieldId="sesion-tipo"
            [label]="t('admin.events.agenda.tipo')"
            [options]="opcionesDeTipo()"
            [hint]="ayudaDeTipo()"
            [(value)]="tipo"
          />
          <!-- Otra pestaña: navegar aquí perdería lo escrito en el formulario. -->
          <a
            class="gestionar-tipos"
            routerLink="/dashboard/session-types"
            target="_blank"
            [attr.aria-label]="t('admin.events.agenda.gestionarTiposAria')"
          >
            <span aria-hidden="true">＋</span> {{ t('admin.events.agenda.gestionarTipos') }}
          </a>

          <app-input
            fieldId="sesion-titulo"
            [label]="t('admin.events.agenda.tituloSesion')"
            [required]="true"
            [(value)]="titulo"
          />
          <app-datetime-picker
            fieldId="sesion-inicio"
            [label]="t('admin.events.agenda.inicio')"
            [required]="true"
            [min]="limitesActivos().min"
            [max]="limitesActivos().max"
            [(value)]="inicio"
          />
          <app-datetime-picker
            fieldId="sesion-fin"
            [label]="t('admin.events.agenda.fin')"
            [required]="true"
            [min]="limitesActivos().min"
            [max]="limitesActivos().max"
            [error]="errorDeFin()"
            [(value)]="fin"
          />
          <app-input
            fieldId="sesion-sala"
            [label]="t('admin.events.agenda.sala')"
            [(value)]="sala"
          />

          @if (sedes().length > 0) {
            <app-select
              fieldId="sesion-sede"
              [label]="t('admin.events.agenda.sede')"
              [options]="opcionesDeSede()"
              [(value)]="venueId"
            />
          }

          <app-select
            fieldId="sesion-video"
            [label]="t('admin.events.agenda.plataformaVideo')"
            [options]="opcionesDeVideoPlatform()"
            [(value)]="videoPlatform"
          />
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
      </app-pestanas-de-idioma>
    </ng-container>
  `,
  styles: `
    /* Ámbar suave, como un aviso y no un error: se ve que se puede pulsar. */
    .gestionar-tipos {
      justify-self: start;
      margin-top: calc(-1 * var(--space-sm));
      color: var(--tipo-ambar);
      font-size: var(--fs-sm);
      text-decoration: underline;
      text-decoration-style: dotted;
      text-underline-offset: 3px;
    }
    .gestionar-tipos:hover {
      text-decoration-style: solid;
    }
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
    .campo-materiales {
      display: grid;
      gap: var(--space-sm);
    }
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

  /** El catálogo de la organización (también los desactivados: la sesión en
   * edición puede tener uno, y debe seguir pudiéndose guardar con él). */
  protected readonly catalogo = signal<readonly TipoDelCatalogo[]>([]);
  protected readonly guardando = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly sedes = signal<EventVenueOption[]>([]);
  /** Rango del evento en hora local (la misma que usan los campos y la que se
   * convierte a UTC al guardar): la sesión tiene que caer dentro. Vacío hasta
   * cargar el evento, y entonces sin límite: el backend lo vuelve a exigir. */
  protected readonly limites = signal<{ min: string; max: string }>({ min: '', max: '' });

  private readonly valoresIniciales = vacio();
  // Tipado como `string`, no `SessionType`/`VideoPlatform`: `app-select` exige
  // un `WritableSignal<string>` para el `[(value)]` bidireccional. El tipo
  // estrecho solo importa al construir el payload, donde se afirma de nuevo.
  protected readonly tipo = signal<string>(this.valoresIniciales.session_type);
  protected readonly titulo = signal(this.valoresIniciales.title);
  protected readonly inicio = signal(this.valoresIniciales.starts_at);
  protected readonly fin = signal(this.valoresIniciales.ends_at);
  protected readonly sala = signal(this.valoresIniciales.room);
  protected readonly videoPlatform = signal<string>(this.valoresIniciales.video_platform);
  protected readonly videoUrl = signal(this.valoresIniciales.video_url);
  protected readonly materiales = signal(this.valoresIniciales.materiales);
  protected readonly venueId = signal('');

  protected readonly opcionesDeSede = computed<SelectOption[]>(() => [
    { value: '', label: this.transloco.translate('admin.events.agenda.sinSedeEspecifica') },
    ...this.sedes().map((sede) => ({ value: sede.id, label: sede.name })),
  ]);

  /** Los activos, más el que ya tiene la sesión aunque esté desactivado. */
  protected readonly opcionesDeTipo = computed<SelectOption[]>(() =>
    this.catalogo()
      .filter((tipo) => tipo.is_active || tipo.id === this.tipo())
      .map((tipo) => ({ value: tipo.id, label: tipo.name })),
  );

  protected readonly ayudaDeTipo = computed(
    () => this.catalogo().find((tipo) => tipo.id === this.tipo())?.description ?? null,
  );

  protected readonly opcionesDeVideoPlatform = computed<SelectOption[]>(() => [
    { value: '', label: this.transloco.translate('admin.events.agenda.sinVideo') },
    { value: 'youtube', label: 'YouTube' },
    { value: 'vimeo', label: 'Vimeo' },
    { value: 'twitch', label: 'Twitch' },
    { value: 'other', label: this.transloco.translate('admin.events.agenda.otraPlataforma') },
  ]);

  constructor() {
    // Las sedes se piden en `ngOnInit`, no en el constructor: los `input.required`
    // (en particular `eventId`) todavía no están enlazados al construir el
    // componente, así que una petición aquí saldría con la URL a medio formar.
  }

  ngOnInit(): void {
    void this.cargarSedes();
    void this.cargarLimites();
    void this.cargarTipos();
    // Montado ya con una sesión (la edición en línea de la agenda): se rellena
    // al nacer, sin esperar a que el padre llame a `cargarSesion`.
    const sesion = this.sesion();
    if (sesion) {
      this.cargarSesion(sesion);
    }
  }

  /** El fin, en el momento: antes que el inicio no tiene sentido guardarlo. */
  protected readonly errorDeFin = computed(() =>
    this.inicio() && this.fin() && this.fin() <= this.inicio()
      ? this.transloco.translate('admin.events.agenda.finAntesDeInicio')
      : null,
  );

  /** Fechas con las que se abrió la sesión en edición (`null` en el alta). */
  private readonly fechasCargadas = signal<{ inicio: string; fin: string } | null>(null);

  /** Una sesión que ya estaba fuera del evento (anterior a esta regla) se puede
   * seguir editando mientras no se toquen sus fechas, como en el backend: hasta
   * entonces no se le aplican los límites. */
  protected readonly limitesActivos = computed(() => {
    const cargadas = this.fechasCargadas();
    const sinCambios =
      cargadas !== null && cargadas.inicio === this.inicio() && cargadas.fin === this.fin();
    return sinCambios ? { min: '', max: '' } : this.limites();
  });

  private fueraDelEvento(valor: string): boolean {
    const { min, max } = this.limitesActivos();
    return (min !== '' && valor < min) || (max !== '' && valor > max);
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
    this.tipo.set(sesion.type?.id ?? '');
    this.titulo.set(sesion.title);
    this.inicio.set(isoAValorLocal(sesion.starts_at));
    this.fin.set(isoAValorLocal(sesion.ends_at));
    this.fechasCargadas.set({ inicio: this.inicio(), fin: this.fin() });
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
    if (this.errorDeFin()) {
      this.formError.set(this.errorDeFin());
      return;
    }
    if (this.fueraDelEvento(this.inicio()) || this.fueraDelEvento(this.fin())) {
      this.formError.set(this.transloco.translate('admin.events.agenda.fueraDelEvento'));
      return;
    }

    const payload = {
      // Sin tipo elegido, la API pone el primero activo que no es pausa.
      session_type_id: this.tipo() || null,
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
    this.tipo.set(this.tipoPorDefecto());
    this.titulo.set(vacios.title);
    this.inicio.set(vacios.starts_at);
    this.fin.set(vacios.ends_at);
    this.sala.set(vacios.room);
    this.videoPlatform.set(vacios.video_platform);
    this.videoUrl.set(vacios.video_url);
    this.materiales.set(vacios.materiales);
    this.venueId.set('');
    this.fechasCargadas.set(null);
    this.formError.set(null);
  }

  private materialesComoLista(): { url: string }[] {
    return this.materiales()
      .split('\n')
      .map((linea) => linea.trim())
      .filter((linea) => linea.length > 0)
      .map((url) => ({ url }));
  }

  private tipoPorDefecto(): string {
    const tipos = this.catalogo();
    return (
      (
        tipos.find((tipo) => tipo.is_active && !tipo.is_break) ??
        tipos.find((tipo) => tipo.is_active)
      )?.id ?? ''
    );
  }

  private async cargarTipos(): Promise<void> {
    try {
      const tipos = await firstValueFrom(
        this.http.get<TipoDelCatalogo[]>(this.api.url('/organizations/me/session-types')),
      );
      this.catalogo.set(tipos);
      // Alta sin tipo elegido: el primero activo que no es una pausa, como la API.
      if (!this.tipo()) {
        this.tipo.set(this.tipoPorDefecto());
      }
    } catch {
      // Sin catálogo el desplegable queda vacío y la API elige el tipo por defecto.
    }
  }

  private async cargarLimites(): Promise<void> {
    try {
      const evento = await firstValueFrom(
        this.http.get<{ starts_at: string; ends_at: string }>(
          this.api.url(`/events/${this.eventId()}`),
        ),
      );
      this.limites.set({
        min: isoAValorLocal(evento.starts_at, { redondearArriba: true }),
        max: isoAValorLocal(evento.ends_at),
      });
    } catch {
      // Sin el evento no hay límites en el formulario; el backend sigue
      // rechazando una sesión fuera de sus fechas.
    }
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
