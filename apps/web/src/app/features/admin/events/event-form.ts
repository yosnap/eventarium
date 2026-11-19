import { NgTemplateOutlet } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { DatetimePicker } from '../../../shared/ui/datetime-picker';
import { Dialog } from '../../../shared/ui/dialog';
import { ErrorSummary, ResumenDeError } from '../../../shared/ui/error-summary';
import { Input } from '../../../shared/ui/input';
import { AddressMap } from '../../../shared/ui/address-map';
import { PageHeader } from '../../../shared/ui/page-header';
import { Select, type SelectOption } from '../../../shared/ui/select';
import { RichTextEditor } from '../../../shared/ui/rich-text-editor';
import { TagsInput } from '../../../shared/ui/tags-input';
import { EventScope } from '../../../layouts/admin/event-scope';
import { isoAValorLocal } from './datetime-local';
import { slugify } from '../../../core/texto/slug';
import { EventReminderSettings } from './event-reminder-settings';
import { EventDetails } from './event-details';
import {
  LONGITUD_MAX_ETIQUETA,
  LONGITUD_MIN_ETIQUETA,
  MAX_ETIQUETAS,
  analizarEtiquetas,
} from '../../../core/eventos/etiquetas';
import { PestanasDeIdioma } from '../../../shared/ui/pestanas-de-idioma';
import { NOMBRE_DEL_IDIOMA } from '../../../core/i18n/idioma';
import { ThemingService } from '../../../core/theming/theming.service';

type LocationMode = 'in_person' | 'online' | 'hybrid';
type RegistrationMode = 'free' | 'approval' | 'paid';

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
/** `EventCreate.slug` (`apps/api/app/modules/events/schemas.py`). */
const LONGITUD_MAXIMA_SLUG = 160;
/** `EventCreate.description`, mismo tope que la API. */
const LONGITUD_MAXIMA_DESCRIPCION = 20000;

/** «Solo con enlace» (`hidden`): se abre con la URL pero no sale en listados ni buscadores. */
type Visibilidad = 'public' | 'hidden' | 'private';

interface EventoBase {
  readonly id: string;
  readonly slug: string;
  readonly title: string;
  readonly summary: string | null;
  readonly description: string | null;
  readonly registration_mode: RegistrationMode;
  readonly visibility: Visibilidad;
  readonly capacity: number | null;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly location_mode: LocationMode;
  readonly city: string | null;
  readonly location_address: string | null;
  readonly latitude: number | null;
  readonly longitude: number | null;
  readonly timezone: string;
  readonly payment_checkout_window_minutes: number;
  readonly reminder_enabled: boolean;
  readonly reminder_hours_before: number;
  readonly category: CategoriaDelCatalogo | null;
  readonly tags: readonly string[];
  readonly source_locale?: string;
}

interface CategoriaDelCatalogo {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly is_active: boolean;
}

type CampoBase =
  'slug' | 'title' | 'startsAt' | 'endsAt' | 'paymentWindow' | 'capacity' | 'description';

// Rango de `events.payment_checkout_window_minutes` (fase 6 del PRD, fase 2
// de trabajo): espejo del `CHECK` de base de datos y del schema del
// backend, entregados ambos en la fase 1 — aquí no se duplica la regla, solo
// se refleja en el cliente.
const VENTANA_DE_PAGO_MIN = 30;
const VENTANA_DE_PAGO_MAX = 1439;
const VENTANA_DE_PAGO_POR_DEFECTO = 30;

// Mismo valor por defecto que `EventCreate.timezone` en el backend
// (`apps/api/app/modules/events/schemas.py`): un evento nuevo abre ya con
// zona horaria, sin que quien lo crea tenga que pensar en ello.
const ZONA_HORARIA_POR_DEFECTO = 'Europe/Madrid';

/** Lista de IANA cuando `Intl.supportedValuesOf` no está disponible (Safari
 * &lt;17): unas pocas zonas de referencia en vez de vaciar el selector. */
const ZONAS_HORARIAS_DE_RESERVA: readonly string[] = [
  'Europe/Madrid',
  'Europe/London',
  'Europe/Paris',
  'America/New_York',
  'America/Mexico_City',
  'America/Bogota',
  'America/Buenos_Aires',
  'UTC',
];

function zonasHorariasDisponibles(): readonly string[] {
  try {
    return Intl.supportedValuesOf('timeZone');
  } catch {
    return ZONAS_HORARIAS_DE_RESERVA;
  }
}

/**
 * Alta y edición de los datos base de un evento (título, slug, fechas, modalidad,
 * ventana de pago). Portada, estado y las secciones del evento viven en
 * `EventDetails`, que este componente delega en cuanto hay un `eventId`.
 */
@Component({
  selector: 'app-event-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    NgTemplateOutlet,
    TranslocoDirective,
    RouterLink,
    Alert,
    Button,
    Card,
    DatetimePicker,
    Dialog,
    ErrorSummary,
    Input,
    AddressMap,
    EventDetails,
    EventReminderSettings,
    PageHeader,
    PestanasDeIdioma,
    Select,
    RichTextEditor,
    TagsInput,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.events.formulario.rotulo')">
        {{
          esEdicion()
            ? t('admin.events.formulario.tituloEditar')
            : t('admin.events.formulario.tituloCrear')
        }}
      </app-page-header>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <ng-template #formulario>
          <app-pestanas-de-idioma tipo="event" [entityId]="eventId()">
            <form (submit)="guardar($event)" novalidate>
              <app-error-summary
                [errores]="resumenDeErrores()"
                [titulo]="t('comun.corrigeErrores')"
              />

              <app-card>
                <div class="rejilla">
                  <app-input
                    class="campo-ancho"
                    fieldId="evento-titulo"
                    [label]="t('admin.events.formulario.titulo')"
                    [required]="true"
                    [error]="errores().title"
                    [value]="title()"
                    (valueChange)="alCambiarTitulo($event)"
                    (blurred)="validar('title')"
                  />
                  <app-input
                    class="campo-ancho"
                    fieldId="evento-slug"
                    [label]="t('admin.events.formulario.slug')"
                    [required]="true"
                    [hint]="t('admin.events.formulario.slugAyuda')"
                    [error]="errores().slug"
                    [value]="slug()"
                    (valueChange)="alCambiarSlug($event)"
                    (blurred)="validar('slug')"
                  />

                  <app-datetime-picker
                    fieldId="evento-inicio"
                    [label]="t('admin.events.formulario.inicio')"
                    [required]="true"
                    [error]="errores().startsAt"
                    [(value)]="startsAt"
                    [(horaPendiente)]="horaInicioPendiente"
                    (blurred)="validar('startsAt')"
                  />
                  <app-datetime-picker
                    fieldId="evento-fin"
                    [label]="t('admin.events.formulario.fin')"
                    [required]="true"
                    [error]="errores().endsAt"
                    [(value)]="endsAt"
                    [(horaPendiente)]="horaFinPendiente"
                    (blurred)="validar('endsAt')"
                  />
                  <app-input
                    fieldId="evento-ciudad"
                    [label]="t('admin.events.formulario.ciudad')"
                    [(value)]="city"
                  />

                  <!-- Categoría y etiquetas en su propia fila de dos columnas: en la
                     rejilla general la categoría caía junto a fechas y ciudad y
                     descuadraba esa fila. -->
                  @if (opcionesDeIdioma().length > 2) {
                    <app-select
                      class="campo-ancho"
                      fieldId="evento-idioma"
                      [label]="t('admin.events.formulario.idioma')"
                      [hint]="t('admin.events.formulario.idiomaAyuda')"
                      [options]="opcionesDeIdioma()"
                      [(value)]="idiomaOrigen"
                    />
                  }
                  <div class="campo-ancho fila-clasificacion">
                    <app-select
                      fieldId="evento-categoria"
                      [label]="t('admin.events.formulario.categoria')"
                      [options]="opcionesDeCategoria()"
                      [(value)]="categoria"
                    />
                    <app-tags-input
                      fieldId="evento-etiquetas"
                      [label]="t('admin.events.formulario.etiquetas')"
                      [hint]="t('admin.events.formulario.etiquetasAyuda')"
                      [placeholder]="t('admin.events.formulario.etiquetasPlaceholder')"
                      [textoQuitar]="t('admin.events.formulario.quitarEtiqueta')"
                      [maximo]="maximoEtiquetas"
                      [normalizar]="normalizarEtiqueta"
                      [validar]="validarEtiqueta"
                      [sugerencias]="sugerenciasDeEtiquetas()"
                      [(value)]="etiquetas"
                      (buscar)="buscarEtiquetas($event)"
                    />
                  </div>
                  <app-input
                    class="campo-ancho"
                    fieldId="evento-resumen"
                    [label]="t('admin.events.formulario.resumen')"
                    [hint]="t('admin.events.formulario.resumenAyuda')"
                    [(value)]="summary"
                  />
                  <app-rich-text-editor
                    class="campo-ancho"
                    fieldId="evento-descripcion"
                    [label]="t('admin.events.formulario.descripcion')"
                    [longitudMaxima]="longitudMaximaDescripcion"
                    [error]="errores().description"
                    [(value)]="description"
                  />

                  <app-select
                    fieldId="evento-modalidad"
                    [label]="t('admin.events.formulario.modalidad')"
                    [options]="opcionesDeModalidad()"
                    [value]="locationMode()"
                    (valueChange)="locationMode.set($any($event))"
                  />
                  <app-select
                    fieldId="evento-zona-horaria"
                    [label]="t('admin.events.formulario.zonaHoraria')"
                    [options]="opcionesDeZonaHoraria()"
                    [buscable]="true"
                    [(value)]="timezone"
                  />

                  <app-select
                    fieldId="evento-modo-inscripcion"
                    [label]="t('admin.events.formulario.modoInscripcion')"
                    [options]="opcionesDeModoDeInscripcion()"
                    [hint]="t('admin.events.formulario.modoAyuda.' + registrationMode())"
                    [value]="registrationMode()"
                    (valueChange)="alCambiarModo($any($event))"
                  />
                  <app-select
                    fieldId="evento-visibilidad"
                    [label]="t('admin.events.formulario.visibilidad')"
                    [options]="opcionesDeVisibilidad()"
                    [hint]="t('admin.events.formulario.visibilidadAyuda.' + visibility())"
                    [value]="visibility()"
                    (valueChange)="visibility.set($any($event))"
                  />
                  <div class="campo-numero">
                    <label for="evento-aforo">{{ t('admin.events.formulario.aforo') }}</label>
                    <input
                      id="evento-aforo"
                      type="number"
                      inputmode="numeric"
                      min="1"
                      [value]="capacity() ?? ''"
                      [attr.aria-invalid]="errores().capacity ? 'true' : null"
                      [attr.aria-describedby]="
                        errores().capacity ? 'evento-aforo-error' : 'evento-aforo-ayuda'
                      "
                      (input)="alCambiarAforo($event)"
                      (blur)="validar('capacity')"
                    />
                    @if (errores().capacity; as mensaje) {
                      <p id="evento-aforo-error" class="error-campo">{{ mensaje }}</p>
                    } @else {
                      <p id="evento-aforo-ayuda" class="ayuda-campo">
                        {{ t('admin.events.formulario.aforoAyuda') }}
                      </p>
                    }
                  </div>

                  <app-event-reminder-settings
                    class="campo-ancho"
                    [dePago]="registrationMode() === 'paid'"
                    [(activado)]="reminderEnabled"
                    [(horas)]="reminderHours"
                    [(horasElegidas)]="reminderHoursElegidas"
                  />

                  @if (locationMode() !== 'online') {
                    <app-address-map
                      class="campo-ancho"
                      fieldId="evento-direccion"
                      [label]="t('admin.events.formulario.direccion')"
                      [(value)]="locationAddress"
                      [initialLatitude]="latitud()"
                      [initialLongitude]="longitud()"
                    />
                  }

                  <div class="campo-numero">
                    <label for="evento-ventana-pago">{{
                      t('admin.events.formulario.ventanaDePago')
                    }}</label>
                    <input
                      id="evento-ventana-pago"
                      type="number"
                      inputmode="numeric"
                      [min]="ventanaDePagoMin"
                      [max]="ventanaDePagoMax"
                      [value]="paymentWindow()"
                      [attr.aria-invalid]="errores().paymentWindow ? 'true' : null"
                      [attr.aria-describedby]="
                        errores().paymentWindow
                          ? 'evento-ventana-pago-error'
                          : 'evento-ventana-pago-ayuda'
                      "
                      (input)="alCambiarVentanaDePago($event)"
                      (blur)="validar('paymentWindow')"
                    />
                    @if (errores().paymentWindow; as mensaje) {
                      <p id="evento-ventana-pago-error" class="error-campo">{{ mensaje }}</p>
                    } @else {
                      <p id="evento-ventana-pago-ayuda" class="ayuda-campo">
                        {{ t('admin.events.formulario.ventanaDePagoAyuda') }}
                      </p>
                    }
                  </div>
                </div>
              </app-card>

              @if (exito()) {
                <app-alert tone="exito">{{ t('admin.events.formulario.exito') }}</app-alert>
              }
              @if (error(); as mensaje) {
                <app-alert tone="error">{{ mensaje }}</app-alert>
              }

              <div class="acciones-finales">
                <a routerLink="/dashboard/events">
                  <app-button variant="secundario" type="button">{{
                    t('admin.roles.cancelar')
                  }}</app-button>
                </a>
                <app-button type="submit" [loading]="guardando()">
                  {{
                    guardando()
                      ? t('admin.events.formulario.guardando')
                      : t('admin.events.formulario.guardar')
                  }}
                </app-button>
              </div>
            </form>
          </app-pestanas-de-idioma>
        </ng-template>

        <!-- Al editar, la ficha coloca el formulario junto a portada y estado. -->
        @if (eventId(); as id) {
          <app-event-details [eventId]="id">
            <ng-container [ngTemplateOutlet]="formulario" />
          </app-event-details>
        } @else {
          <div class="solo-formulario">
            <ng-container [ngTemplateOutlet]="formulario" />
          </div>
        }

        <app-dialog #dialogoMoverSesiones (cerrado)="pendienteDeMover.set(null)">
          <p>{{ avisoDeSesiones() }}</p>
          <p>{{ t('admin.events.formulario.moverSesionesPregunta') }}</p>
          <app-button
            pie
            variant="secundario"
            type="button"
            [disabled]="guardando()"
            (pulsado)="dialogoMoverSesiones.cerrar()"
          >
            {{ t('comun.cancelar') }}
          </app-button>
          <app-button pie type="button" [loading]="guardando()" (pulsado)="moverSesiones()">
            {{ t('admin.events.formulario.moverSesiones') }}
          </app-button>
        </app-dialog>
      }
    </ng-container>
  `,
  styles: `
    /* \`ng-container\` no genera elemento: cabecera, formulario y
     * \`app-event-details\` son hijos directos de este host. Y un componente
     * sin \`display\` propio es \`inline\` por defecto, donde un margen
     * vertical no hace nada — hay que forzar \`display: block\` en cada hijo
     * antes de que \`margin-top\` pueda separarlos. */
    :host {
      display: block;
    }
    /* :not(form): el propio <form> ya declara su display (grid, más abajo)
       — sin esta exclusión, esta regla lo pisaba a display:block por mayor
       especificidad ([_nghost] > [_ngcontent] gana a form[_ngcontent]), y su
       "gap" dejaba de tener ningún efecto real (hallazgo del usuario:
       tarjeta y botones finales quedaban pegados, sin separación). */
    :host > *:not(form) {
      display: block;
    }
    :host > * + * {
      margin-top: var(--space-lg);
    }
    form {
      display: grid;
      gap: var(--space-lg);
    }
    /* Sin errores el resumen no pinta nada, pero como hijo de la rejilla
     * seguía sumando un hueco y bajaba el formulario respecto a la columna
     * lateral de la ficha. */
    app-error-summary:empty {
      display: none;
    }
    /* Al crear no hay columna lateral. 64rem: tres columnas de campo con aire
     * (inicio, fin y ciudad caben en una fila sin pisarse) sin que el título
     * ni la dirección se estiren hasta líneas interminables. Al editar, el
     * ancho lo marca la rejilla de \`app-event-details\`. */
    .solo-formulario {
      max-width: 64rem;
    }
    /* Campos cortos (fechas, zona horaria, modalidad, ciudad, ventana de
     * pago) en columnas cuando hay sitio; título, slug y dirección
     * ocupan la rejilla entera con \`.campo-ancho\`, en vez de la única
     * columna a todo el ancho que tenía el formulario antes. */
    .fila-clasificacion {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--space-lg) var(--space-md);
      align-items: start;
    }
    @media (max-width: 40rem) {
      .fila-clasificacion {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    .rejilla {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(18rem, 100%), 1fr));
      gap: var(--space-lg) var(--space-md);
      align-items: start;
    }
    /* Los pickers traen dos controles (fecha + caja de hora) que no pueden
     * encoger bajo su contenido: sin esto, la columna de grid los dejaba
     * desbordar y pisaban al campo vecino (Ciudad). */
    .rejilla > app-datetime-picker,
    .rejilla > app-input {
      min-width: 0;
    }
    .campo-ancho {
      grid-column: 1 / -1;
    }
    .campo-numero {
      display: grid;
      gap: var(--space-sm);
    }
    .campo-numero input {
      width: 100%;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      color: var(--fg);
      font: inherit;
      /* 46px (2.875rem), la altura de .sel__btn: aforo y ventana de pago
       * quedan alineados con los desplegables de su misma fila. */
      min-height: 2.875rem;
    }
    .campo-numero input {
      max-width: 12rem;
    }
    .error-campo {
      margin: 0;
      color: var(--danger);
      font-size: 0.875rem;
    }
    .ayuda-campo {
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
export class EventForm {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly theming = inject(ThemingService);
  private readonly route = inject(ActivatedRoute);
  private readonly eventScope = inject(EventScope);

  protected readonly eventId = signal<string | null>(null);
  protected readonly esEdicion = computed(() => this.eventId() !== null);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly exito = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly slug = signal('');
  /** El slug sigue al título mientras nadie lo toca. Al editar un evento
   * existente arranca a `true`: cambiarlo solo rompería su URL pública. */
  private readonly slugManual = signal(false);
  protected readonly title = signal('');
  protected readonly summary = signal('');
  protected readonly description = signal('');
  protected readonly longitudMaximaDescripcion = LONGITUD_MAXIMA_DESCRIPCION;
  protected readonly registrationMode = signal<RegistrationMode>('free');
  protected readonly visibility = signal<Visibilidad>('public');
  protected readonly reminderEnabled = signal(true);
  /** `null` en un evento nuevo sin elegir: la API decide (24 h, o 48 h si es de pago). */
  protected readonly reminderHours = signal<number | null>(null);
  protected readonly reminderHoursElegidas = signal(false);
  /** `null` = sin límite de aforo; `NaN` = lo escrito no es un número. */
  protected readonly capacity = signal<number | null>(null);
  protected readonly startsAt = signal('');
  protected readonly endsAt = signal('');
  /** Día elegido sin hora todavía en cada selector: el error pide la hora, no
   * la fecha. */
  protected readonly horaInicioPendiente = signal(false);
  protected readonly horaFinPendiente = signal(false);
  protected readonly locationMode = signal<LocationMode>('in_person');
  protected readonly city = signal('');
  protected readonly locationAddress = signal('');
  protected readonly latitud = signal<number | null>(null);
  protected readonly longitud = signal<number | null>(null);
  protected readonly timezone = signal(ZONA_HORARIA_POR_DEFECTO);
  protected readonly paymentWindow = signal(VENTANA_DE_PAGO_POR_DEFECTO);
  protected readonly ventanaDePagoMin = VENTANA_DE_PAGO_MIN;
  protected readonly ventanaDePagoMax = VENTANA_DE_PAGO_MAX;

  /** Id de la categoría elegida, o cadena vacía = sin categoría. */
  protected readonly categoria = signal('');
  protected readonly categoriasActivas = signal<readonly CategoriaDelCatalogo[]>([]);
  /** La categoría que el evento ya tiene, aunque se haya desactivado: se sigue
   * mostrando para no borrarla al guardar otros cambios. */
  private readonly categoriaActual = signal<CategoriaDelCatalogo | null>(null);
  protected readonly etiquetas = signal<string[]>([]);
  /** Idioma en que se escribe el evento; vacío en un alta: el de la organización. */
  protected readonly idiomaOrigen = signal('');
  protected readonly opcionesDeIdioma = computed(() => [
    {
      value: '',
      label: this.transloco.translate('admin.events.formulario.idiomaDeLaOrganizacion'),
    },
    ...this.theming.idiomasActivos().map((idioma) => ({
      value: idioma,
      label: NOMBRE_DEL_IDIOMA[idioma],
    })),
  ]);
  protected readonly sugerenciasDeEtiquetas = signal<readonly string[]>([]);
  private ultimaBusquedaDeEtiquetas = '';
  protected readonly maximoEtiquetas = MAX_ETIQUETAS;
  protected readonly normalizarEtiqueta = (texto: string): string =>
    texto.trim().toLowerCase().replace(/\s+/g, ' ');
  /** Mismas reglas que `analizarEtiquetas` (y que la API), aplicadas a la
   * etiqueta que se intenta añadir junto a las que ya hay. */
  protected readonly validarEtiqueta = (
    etiqueta: string,
    actuales: readonly string[],
  ): string | null => {
    const { error } = analizarEtiquetas([...actuales, etiqueta].join(','));
    if (!error) return null;
    switch (error.tipo) {
      case 'longitud':
        return this.transloco.translate('admin.events.formulario.etiquetaLongitud', {
          etiqueta: error.etiqueta,
          min: LONGITUD_MIN_ETIQUETA,
          max: LONGITUD_MAX_ETIQUETA,
        });
      case 'caracteres':
        return this.transloco.translate('admin.events.formulario.etiquetaCaracteres', {
          etiqueta: error.etiqueta,
        });
      case 'demasiadas':
        return this.transloco.translate('admin.events.formulario.etiquetasDemasiadas', {
          max: MAX_ETIQUETAS,
        });
    }
  };

  protected readonly opcionesDeCategoria = computed<SelectOption[]>(() => {
    const opciones: SelectOption[] = [
      { value: '', label: this.transloco.translate('admin.events.formulario.sinCategoria') },
      ...this.categoriasActivas().map((c) => ({ value: c.id, label: c.name })),
    ];
    const actual = this.categoriaActual();
    if (actual && !opciones.some((o) => o.value === actual.id)) {
      opciones.push({
        value: actual.id,
        label: this.transloco.translate('admin.events.formulario.categoriaDesactivada', {
          nombre: actual.name,
        }),
      });
    }
    return opciones;
  });

  protected readonly opcionesDeModalidad = computed<SelectOption[]>(() => [
    { value: 'in_person', label: this.transloco.translate('admin.events.formulario.presencial') },
    { value: 'online', label: this.transloco.translate('admin.events.formulario.online') },
    { value: 'hybrid', label: this.transloco.translate('admin.events.formulario.hibrido') },
  ]);

  protected readonly opcionesDeModoDeInscripcion = computed<SelectOption[]>(() => [
    { value: 'free', label: this.transloco.translate('admin.events.formulario.modoLibre') },
    {
      value: 'approval',
      label: this.transloco.translate('admin.events.formulario.modoAprobacion'),
    },
    { value: 'paid', label: this.transloco.translate('admin.events.formulario.modoPago') },
  ]);

  protected readonly opcionesDeVisibilidad = computed<SelectOption[]>(() =>
    (['public', 'hidden', 'private'] as const).map((valor) => ({
      value: valor,
      label: this.transloco.translate(`admin.events.formulario.visibilidadOpcion.${valor}`),
    })),
  );

  protected readonly opcionesDeZonaHoraria = computed<SelectOption[]>(() =>
    zonasHorariasDisponibles().map((zona) => ({ value: zona, label: zona })),
  );

  protected readonly errores = signal<Record<CampoBase, string | null>>({
    slug: null,
    title: null,
    startsAt: null,
    endsAt: null,
    paymentWindow: null,
    capacity: null,
    description: null,
  });

  protected readonly resumenDeErrores = computed<ResumenDeError[]>(() => {
    const actuales = this.errores();
    const resumen: ResumenDeError[] = [];
    if (actuales.title) resumen.push({ campoId: 'evento-titulo', mensaje: actuales.title });
    if (actuales.slug) resumen.push({ campoId: 'evento-slug', mensaje: actuales.slug });
    if (actuales.startsAt) resumen.push({ campoId: 'evento-inicio', mensaje: actuales.startsAt });
    if (actuales.endsAt) resumen.push({ campoId: 'evento-fin', mensaje: actuales.endsAt });
    if (actuales.paymentWindow) {
      resumen.push({ campoId: 'evento-ventana-pago', mensaje: actuales.paymentWindow });
    }
    if (actuales.capacity) resumen.push({ campoId: 'evento-aforo', mensaje: actuales.capacity });
    if (actuales.description) {
      resumen.push({ campoId: 'evento-descripcion', mensaje: actuales.description });
    }
    return resumen;
  });

  constructor() {
    void this.cargarCategorias();
    const id = this.route.snapshot.paramMap.get('eventId');
    if (id && id !== 'nuevo') {
      this.eventId.set(id);
      void this.cargar(id);
    } else {
      this.cargando.set(false);
    }
  }

  private async cargarCategorias(): Promise<void> {
    try {
      this.categoriasActivas.set(
        await firstValueFrom(
          this.http.get<CategoriaDelCatalogo[]>(this.api.url('/event-categories')),
        ),
      );
    } catch {
      // Sin catálogo el formulario sigue funcionando: solo no ofrece categorías.
    }
  }

  private async cargar(id: string): Promise<void> {
    this.cargando.set(true);
    try {
      const evento = await firstValueFrom(this.http.get<EventoBase>(this.api.url(`/events/${id}`)));
      this.slug.set(evento.slug);
      this.slugManual.set(true);
      this.title.set(evento.title);
      this.summary.set(evento.summary ?? '');
      this.description.set(evento.description ?? '');
      this.registrationMode.set(evento.registration_mode);
      this.visibility.set(evento.visibility ?? 'public');
      this.capacity.set(evento.capacity);
      this.startsAt.set(isoAValorLocal(evento.starts_at));
      this.endsAt.set(isoAValorLocal(evento.ends_at));
      this.locationMode.set(evento.location_mode);
      this.city.set(evento.city ?? '');
      this.locationAddress.set(evento.location_address ?? '');
      this.latitud.set(evento.latitude);
      this.longitud.set(evento.longitude);
      this.timezone.set(evento.timezone);
      this.paymentWindow.set(evento.payment_checkout_window_minutes);
      this.reminderEnabled.set(evento.reminder_enabled);
      this.reminderHours.set(evento.reminder_hours_before);
      this.categoria.set(evento.category?.id ?? '');
      this.categoriaActual.set(evento.category);
      this.etiquetas.set([...evento.tags]);
      this.idiomaOrigen.set(evento.source_locale ?? '');
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  /** Sugerencias de etiquetas ya usadas en la organización; si falla, el campo
   * sigue funcionando sin ellas. */
  protected async buscarEtiquetas(texto: string): Promise<void> {
    // Una respuesta lenta de «da» no debe pisar la de «dat», que llegó antes.
    this.ultimaBusquedaDeEtiquetas = texto;
    let sugerencias: readonly string[] = [];
    try {
      sugerencias = await firstValueFrom(
        this.http.get<string[]>(this.api.url('/events/tags'), { params: { q: texto } }),
      );
    } catch {
      // Sin sugerencias el campo sigue funcionando.
    }
    if (texto === this.ultimaBusquedaDeEtiquetas) {
      this.sugerenciasDeEtiquetas.set(sugerencias);
    }
  }

  protected alCambiarTitulo(valor: string): void {
    this.title.set(valor);
    if (!this.slugManual()) {
      this.slug.set(slugify(valor, LONGITUD_MAXIMA_SLUG));
    }
  }

  protected alCambiarSlug(valor: string): void {
    this.slug.set(valor);
    // Al crear, vaciarlo devuelve el control al título; en un evento existente
    // nunca, porque cambiaría su URL pública.
    this.slugManual.set(valor.trim() !== '' || this.esEdicion());
  }

  /** Al pasar a pago, el recordatorio por defecto (24 h) llegaría con el plazo de
   * reembolso ya cerrado: sube a 48 h si nadie ha elegido otras horas, como la API. */
  protected alCambiarModo(modo: RegistrationMode): void {
    this.registrationMode.set(modo);
    if (modo === 'paid' && this.reminderHours() === 24 && !this.reminderHoursElegidas()) {
      this.reminderHours.set(48);
    }
  }

  protected alCambiarAforo(evento: Event): void {
    const campo = evento.target as HTMLInputElement;
    // Con `type="number"` un texto no numérico llega como `''`: sin mirar
    // `badInput` se guardaría como «sin límite» y la API ofrecería plaza a
    // toda la lista de espera.
    if (campo.validity.badInput) {
      this.capacity.set(Number.NaN);
      return;
    }
    this.capacity.set(campo.value === '' ? null : Number(campo.value));
  }

  protected alCambiarVentanaDePago(evento: Event): void {
    const bruto = (evento.target as HTMLInputElement).value;
    this.paymentWindow.set(bruto === '' ? Number.NaN : Number(bruto));
  }

  private errorDe(campo: CampoBase): string | null {
    switch (campo) {
      case 'title':
        return this.title().trim()
          ? null
          : this.transloco.translate('admin.events.formulario.tituloRequerido');
      case 'slug': {
        const valor = this.slug().trim();
        if (!valor) return this.transloco.translate('admin.events.formulario.slugRequerido');
        return SLUG_RE.test(valor)
          ? null
          : this.transloco.translate('admin.events.formulario.slugInvalido');
      }
      case 'startsAt':
        if (this.horaInicioPendiente()) {
          return this.transloco.translate('admin.events.formulario.horaInicioRequerida');
        }
        return this.startsAt()
          ? null
          : this.transloco.translate('admin.events.formulario.inicioRequerido');
      case 'endsAt':
        if (this.horaFinPendiente()) {
          return this.transloco.translate('admin.events.formulario.horaFinRequerida');
        }
        if (!this.endsAt()) {
          return this.transloco.translate('admin.events.formulario.finRequerido');
        }
        return new Date(this.endsAt()) > new Date(this.startsAt())
          ? null
          : this.transloco.translate('admin.events.formulario.finAnteriorAlInicio');
      case 'paymentWindow': {
        const valor = this.paymentWindow();
        if (Number.isNaN(valor)) {
          return this.transloco.translate('admin.events.formulario.ventanaDePagoRequerida');
        }
        return valor >= VENTANA_DE_PAGO_MIN && valor <= VENTANA_DE_PAGO_MAX
          ? null
          : this.transloco.translate('admin.events.formulario.ventanaDePagoFueraDeRango');
      }
      case 'description':
        return this.description().length > LONGITUD_MAXIMA_DESCRIPCION
          ? this.transloco.translate('admin.events.formulario.descripcionLarga', {
              max: LONGITUD_MAXIMA_DESCRIPCION,
            })
          : null;
      case 'capacity': {
        const valor = this.capacity();
        return valor === null || (Number.isInteger(valor) && valor >= 1)
          ? null
          : this.transloco.translate('admin.events.formulario.aforoInvalido');
      }
    }
  }

  protected validar(campo: CampoBase): void {
    this.errores.update((actuales) => ({ ...actuales, [campo]: this.errorDe(campo) }));
  }

  private validarTodo(): boolean {
    const actuales: Record<CampoBase, string | null> = {
      slug: this.errorDe('slug'),
      title: this.errorDe('title'),
      startsAt: this.errorDe('startsAt'),
      endsAt: this.errorDe('endsAt'),
      paymentWindow: this.errorDe('paymentWindow'),
      capacity: this.errorDe('capacity'),
      description: this.errorDe('description'),
    };
    this.errores.set(actuales);
    return Object.values(actuales).every((mensaje) => !mensaje);
  }

  private readonly dialogoMoverSesiones = viewChild.required<Dialog>('dialogoMoverSesiones');
  /** Lo que se intentó guardar cuando la API avisó de sesiones que quedarían
   * fuera de las fechas nuevas: se reenvía tal cual, moviéndolas, si se acepta. */
  protected readonly pendienteDeMover = signal<Record<string, unknown> | null>(null);
  protected readonly avisoDeSesiones = signal('');

  protected async moverSesiones(): Promise<void> {
    const payload = this.pendienteDeMover();
    if (!payload) return;
    await this.enviar({ ...payload, mover_sesiones: true });
    this.dialogoMoverSesiones().cerrar();
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    this.exito.set(false);
    if (!this.validarTodo()) {
      return;
    }

    const payload = {
      slug: this.slug().trim(),
      title: this.title().trim(),
      // Siempre explícitos, como la categoría: `null` vacía el resumen, la
      // descripción o el aforo. La API solo valida modo y aforo si cambian.
      summary: this.summary().trim() || null,
      description: this.description().trim() || null,
      registration_mode: this.registrationMode(),
      visibility: this.visibility(),
      capacity: this.capacity(),
      starts_at: new Date(this.startsAt()).toISOString(),
      ends_at: new Date(this.endsAt()).toISOString(),
      location_mode: this.locationMode(),
      city: this.city().trim() || null,
      location_address:
        this.locationMode() !== 'online' ? this.locationAddress().trim() || null : null,
      timezone: this.timezone(),
      payment_checkout_window_minutes: this.paymentWindow(),
      reminder_enabled: this.reminderEnabled(),
      // Sin elegir en un evento nuevo no se envía: la API pone su valor por defecto.
      ...(this.reminderHours() === null ? {} : { reminder_hours_before: this.reminderHours() }),
      // Siempre explícitos: `null` quita la categoría, `[]` las etiquetas.
      category_id: this.categoria() || null,
      tags: [...this.etiquetas()],
      ...(this.idiomaOrigen() ? { source_locale: this.idiomaOrigen() } : {}),
    };
    await this.enviar(payload);
  }

  private async enviar(payload: Record<string, unknown>): Promise<void> {
    this.error.set(null);
    this.guardando.set(true);
    try {
      const id = this.eventId();
      const guardado = id
        ? await firstValueFrom(this.http.patch<EventoBase>(this.api.url(`/events/${id}`), payload))
        : await firstValueFrom(this.http.post<EventoBase>(this.api.url('/events'), payload));
      this.eventId.set(guardado.id);
      // Las pestañas de pago dependen del modo: refrescar el ámbito del evento
      // para que aparezcan o desaparezcan sin recargar la página.
      this.eventScope.actualizar(guardado.id, guardado);
      this.exito.set(true);
    } catch (error) {
      // Fechas nuevas que dejan sesiones fuera: se pregunta antes que fallar.
      // Si ya se pidió moverlas y aun así no caben, es un error normal.
      if (
        error instanceof ApiError &&
        error.problem?.['code'] === 'sesiones_fuera_de_rango' &&
        error.problem?.['movidas'] === false
      ) {
        this.avisoDeSesiones.set(error.message);
        this.pendienteDeMover.set(payload);
        this.dialogoMoverSesiones().abrir();
        return;
      }
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
      // Slug ocupado: la API propone uno libre; se deja puesto para guardar a la
      // primera, con el mensaje explicando por qué ha cambiado.
      const sugerido = error instanceof ApiError ? error.problem?.['suggested_slug'] : null;
      if (typeof sugerido === 'string') {
        this.slug.set(sugerido);
        this.slugManual.set(true);
      }
    } finally {
      this.guardando.set(false);
    }
  }
}
