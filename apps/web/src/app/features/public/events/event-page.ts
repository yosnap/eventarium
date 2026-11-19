import { DOCUMENT, DatePipe, ViewportScroller } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  computed,
  effect,
  inject,
  input,
  makeStateKey,
  signal,
  LOCALE_ID,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { temaDeEvento } from '../../../core/theming/tema-de-evento';
import { ApiError } from '../../../core/api/error.interceptor';
import { seoDePagina } from '../../../core/seo/meta.service';
import { apiEvento, rutaEvento, urlEvento } from '../../../core/routing/rutas-publicas';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { formatearPrecio } from '../../../shared/text/formatear-precio';
import { Alert } from '../../../shared/ui/alert';
import { Breadcrumb, type BreadcrumbItem } from '../../../shared/ui/breadcrumb';
import { Chip, type ChipTone } from '../../../shared/ui/chip';
import { migasDeEvento } from '../../../shared/ui/migas-de-evento';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { ShareLinks } from '../../../shared/ui/share-links';
import { VenueMap } from '../../../shared/ui/venue-map';
import { MarkdownSeguro } from '../../../shared/legal/markdown-seguro';
import type {
  LocationMode,
  PublicEventDetail,
  PublicParticipant,
  RegistrationMode,
} from './event-page.types';
import { type DiaDeAgenda, EventAgendaSection } from './sections/event-agenda-section';
import { type Speaker, EventSpeakersSection } from './sections/event-speakers-section';
import { DirectionsLink } from '../../../shared/ui/directions-link';
import { EventNearbySection } from './sections/event-nearby-section';
import { AvisoVentaEntradas, avisoDeVenta } from './aviso-venta-entradas';
import { EnlacePipe } from '../../../core/i18n/enlace.pipe';
import { IdiomaService } from '../../../core/i18n/idioma.service';
import { idiomasDeLaRespuesta } from '../../../core/seo/indexacion-por-idioma';
import { AvisoContenidoOriginal } from '../../../shared/ui/aviso-contenido-original';
import { traduccionEnVivo } from '../../../core/traducciones/traduccion-en-vivo';
import { EnTraduccion } from '../../../shared/ui/esqueleto';

/** `starts_at` (UTC) al día calendario en la zona del evento, sin arrastrar la
 * zona horaria del entorno de ejecución (navegador o SSR) al agrupar por fecha:
 * usar `getTimezoneOffset()` movía sesiones cercanas a medianoche a días
 * distintos según dónde se ejecutara. `en-CA` da directamente `AAAA-MM-DD`. */
function fechaEnZona(iso: string, zona: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: zona,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(iso));
}

const CLAVES_FORMATO: Record<LocationMode, string> = {
  in_person: 'publico.eventos.formato.presencial',
  online: 'publico.eventos.formato.online',
  hybrid: 'publico.eventos.formato.hibrido',
};

const CLAVES_REGISTRO: Record<RegistrationMode, { clave: string; tono: ChipTone }> = {
  free: { clave: 'publico.eventos.registro.gratuita', tono: 'ok' },
  approval: { clave: 'publico.eventos.registro.aprobacion', tono: 'espera' },
  paid: { clave: 'publico.eventos.registro.pago', tono: 'neutro' },
};

/**
 * Página pública de un evento, sobre `evento-iawic.html` del prototipo de
 * OpenDesign: hero con ficha de datos reales, agenda por día con pestañas
 * accesibles, ponentes (roster del evento y agenda), patrocinadores por nivel y
 * lugar — sin ningún dato que la API no devuelva (ver cabecera de
 * `event-page.types.ts`).
 *
 * No se construyen: la barra de aforo confirmado/disponible (no hay ese dato
 * en `PublicEventDetail`), el bloque "cerca del recinto"/mapa SVG (sin modelo
 * de datos), el enlace a programa multisede (non-goal del plan) ni el botón
 * de descarga de dossier de patrocinadores (sin URL real).
 *
 * Carga los datos con `serverForwardHeaders()` + `TransferState`, igual que
 * antes de esta reescritura — ver el resto de páginas públicas de eventos
 * para el mismo patrón.
 */
@Component({
  selector: 'app-event-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    EnTraduccion,
    AvisoContenidoOriginal,
    EnlacePipe,
    AvisoVentaEntradas,
    DatePipe,
    DirectionsLink,
    EventNearbySection,
    RouterLink,
    TranslocoDirective,
    Alert,
    Breadcrumb,
    Chip,
    VenueMap,
    Reveal,
    ShareLinks,
    EventAgendaSection,
    EventSpeakersSection,
    MarkdownSeguro,
  ],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p class="ancho-maximo">{{ t('comun.cargando') }}</p>
      } @else if (errorDeVistaPrevia()) {
        <div class="ancho-maximo">
          <app-alert tone="error">{{ t('publico.eventos.vistaPreviaError') }}</app-alert>
        </div>
      } @else if (noEncontrado()) {
        <div class="ancho-maximo">
          <app-alert tone="error">{{ t('publico.eventos.noEncontrado') }}</app-alert>
        </div>
      } @else if (evento(); as evento) {
        @if (eventId()) {
          <div class="ancho-maximo aviso-vista-previa">
            <app-alert tone="info">{{ t('publico.eventos.vistaPrevia') }}</app-alert>
          </div>
        }
        <article [attr.data-ambito]="ambitoDelEvento()">
          <section class="hero">
            <div class="ancho-maximo">
              <app-breadcrumb
                [items]="migasDePan(evento)"
                [ariaLabel]="t('publico.eventos.ruta')"
              />
            </div>
            <div class="ancho-maximo hero__grid">
              <div>
                <div class="hero__kicker">
                  <span class="rotulo-seccion">
                    {{ evento.starts_at | date: 'd MMM' : evento.timezone }} –
                    {{ evento.ends_at | date: 'd MMM yyyy' : evento.timezone }}
                    @if (evento.location_name) {
                      · {{ evento.location_name }}
                    }
                  </span>
                  @if (evento.cancelled) {
                    <app-chip tone="apagado">{{ t('publico.eventos.cancelado.chip') }}</app-chip>
                  } @else {
                    <app-chip [tone]="registro().tono">{{ t(registro().clave) }}</app-chip>
                  }
                </div>
                @if (evento.cancelled) {
                  <app-alert tone="error" [title]="t('publico.eventos.cancelado.titulo')">
                    {{ evento.cancellation_reason || t('publico.eventos.cancelado.sinMotivo') }}
                  </app-alert>
                }
                @if (evento.cover_url) {
                  <img class="portada" [src]="evento.cover_url" [alt]="evento.title" />
                }
                <h1>
                  <app-en-traduccion [traduciendo]="traduciendo()">{{
                    evento.title
                  }}</app-en-traduccion>
                </h1>
                <app-aviso-contenido-original [servido]="evento.served_locale" />
                @if (evento.category || (evento.tags && evento.tags.length > 0)) {
                  <nav class="clasificacion" [attr.aria-label]="t('publico.eventos.clasificacion')">
                    @if (evento.category; as categoria) {
                      <a
                        class="clasificacion__categoria"
                        [routerLink]="'/eventos' | enlace"
                        [queryParams]="{ categoria: categoria.slug }"
                        >{{ categoria.name }}</a
                      >
                    }
                    @for (etiqueta of evento.tags ?? []; track etiqueta) {
                      <a
                        class="clasificacion__etiqueta"
                        [routerLink]="'/eventos' | enlace"
                        [queryParams]="{ etiqueta: etiqueta }"
                        >#{{ evento.tag_labels?.[etiqueta] ?? etiqueta }}</a
                      >
                    }
                  </nav>
                }
                @if (evento.summary) {
                  <app-en-traduccion [traduciendo]="traduciendo()" [lineas]="2">
                    <p class="hero__lede">{{ evento.summary }}</p>
                  </app-en-traduccion>
                }
                @if (evento.description) {
                  <!-- Markdown del editor del panel, saneado: nunca [innerHTML]
                       directo con texto de la organización. Los saltos simples
                       se respetan por las descripciones escritas en texto plano. -->
                  <app-en-traduccion [traduciendo]="traduciendo()" [lineas]="4">
                    <app-markdown-seguro
                      class="hero__descripcion"
                      [texto]="evento.description"
                      [saltosDeLinea]="true"
                    />
                  </app-en-traduccion>
                }
                @if (!evento.cancelled) {
                  <app-share-links
                    class="hero__compartir"
                    [url]="urlPublica(evento)"
                    [titulo]="evento.title"
                  />
                }
              </div>

              <div class="ficha">
                <div class="ficha__filas">
                  <div class="ficha__fila">
                    <span class="ficha__etiqueta">{{ t('publico.eventos.ficha.fechas') }}</span>
                    <span>
                      {{ evento.starts_at | date: 'dd.MM.yyyy' : evento.timezone }} –
                      {{ evento.ends_at | date: 'dd.MM.yyyy' : evento.timezone }}
                    </span>
                  </div>
                  @if (evento.location_name) {
                    <div class="ficha__fila">
                      <span class="ficha__etiqueta">{{ t('publico.eventos.ficha.lugar') }}</span>
                      <span>{{ evento.location_name }}</span>
                    </div>
                  }
                  <div class="ficha__fila">
                    <span class="ficha__etiqueta">{{ t('publico.eventos.ficha.formato') }}</span>
                    <span>{{ t(formato().clave) }}</span>
                  </div>
                  <div class="ficha__fila">
                    <span class="ficha__etiqueta">
                      {{ t('publico.eventos.ficha.zonaHoraria') }}
                    </span>
                    <span>{{ evento.timezone }}</span>
                  </div>
                  <!-- Idioma: el modelo de datos todavía no lo guarda. Se muestra la
                       fila con el aviso de dato pendiente, sin inventar el valor. -->
                  <div class="ficha__fila">
                    <span class="ficha__etiqueta">{{ t('publico.eventos.ficha.idioma') }}</span>
                    <span class="pendiente">{{ t('publico.eventos.datoPendiente') }}</span>
                  </div>
                  @if (!entradaGratuita()) {
                    <div class="ficha__fila">
                      <span class="ficha__etiqueta">{{ t('publico.eventos.ficha.precio') }}</span>
                      @if (precioDesde(); as precio) {
                        <span class="ficha__precio">
                          {{
                            evento.price_multiple
                              ? t('publico.eventos.precio.desde', { precio })
                              : precio
                          }}
                        </span>
                      } @else {
                        <span>{{ t('publico.eventos.registro.pagoCorto') }}</span>
                      }
                    </div>
                  }
                </div>
                <div class="ficha__cta">
                  @if (evento.capacity !== null) {
                    <div class="ficha__aforo">
                      <span class="rotulo-seccion">
                        {{ t('publico.eventos.ficha.aforo') }} · {{ evento.capacity }}
                      </span>
                      <div
                        class="seats"
                        role="img"
                        [attr.aria-label]="
                          t('publico.eventos.ficha.aforoAria', {
                            reservadas: evento.reserved_count,
                            total: evento.capacity,
                            porcentaje: ocupacion(),
                          })
                        "
                      >
                        <span [style.width.%]="ocupacion()"></span>
                      </div>
                      <p class="hint">
                        <span class="num">{{ evento.reserved_count }}</span>
                        {{ t('publico.eventos.ficha.confirmadas') }} ·
                        <span class="num">{{ plazasDisponibles() }}</span>
                        {{ t('publico.eventos.ficha.disponibles') }}
                      </p>
                    </div>
                  }
                  @if (!evento.cancelled) {
                    @if (avisoVenta(); as aviso) {
                      <app-aviso-venta-entradas [aviso]="aviso" />
                    } @else {
                      <a class="ficha__inscribirse" [routerLink]="ruta('inscribirse') | enlace">
                        {{ t('publico.eventos.inscribirse') }}
                      </a>
                      <p class="ficha__nota">{{ t('publico.eventos.ficha.sinCuenta') }}</p>
                    }
                  }
                  <p class="ficha__nota">
                    <a [routerLink]="ruta('politicas') | enlace">
                      {{ t('publico.politicas.enlace') }}
                    </a>
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section class="seccion" aria-labelledby="agenda-h2">
            <div class="ancho-maximo" appReveal>
              <div class="seccion__cabecera">
                <div>
                  <span class="rotulo-seccion">{{ t('publico.eventos.multisede.rotulo') }}</span>
                  <h2 id="agenda-h2">{{ t('publico.eventos.agenda') }}</h2>
                  <!-- .hint de evento-iawic.html:126-127: solo se ofrece el programa
                       por sede cuando el evento tiene más de una. -->
                  @if (evento.venues.length > 1) {
                    <p class="hint">
                      {{ t('publico.eventos.multisede.pregunta') }}
                      <a class="mark" [routerLink]="ruta('programa') | enlace">
                        {{ t('publico.eventos.multisede.enlace') }}
                      </a>
                    </p>
                  }
                </div>
              </div>
              @if (dias().length === 0) {
                <p class="vacio">{{ t('publico.eventos.sinAgenda') }}</p>
              } @else {
                <app-event-agenda-section
                  [dias]="dias()"
                  [org]="evento.organization.slug"
                  [eventSlug]="evento.slug"
                  [eventTimezone]="evento.timezone"
                />
              }
            </div>
          </section>

          @if (ponentes().length > 0) {
            <section class="seccion" aria-labelledby="ponentes-h2">
              <div class="ancho-maximo" appReveal>
                <div class="seccion__cabecera">
                  <span class="rotulo-seccion">{{ t('publico.eventos.ponentes') }}</span>
                  <h2 id="ponentes-h2">{{ t('publico.eventos.ponentesTitulo') }}</h2>
                </div>
                <app-event-speakers-section [ponentes]="ponentes()" />
              </div>
            </section>
          }

          @if (evento.sponsor_tiers.length > 0) {
            <section class="seccion" aria-labelledby="patrocinadores-h2">
              <div class="ancho-maximo" appReveal>
                <div class="seccion__cabecera">
                  <span class="rotulo-seccion">{{
                    t('publico.eventos.patrocinadores.titulo')
                  }}</span>
                  <h2 id="patrocinadores-h2">
                    {{ t('publico.eventos.patrocinadores.tituloExtendido') }}
                  </h2>
                </div>
                @for (nivel of evento.sponsor_tiers; track $index + nivel.name) {
                  <div class="tier" [class]="'tier--' + nivel.logo_size">
                    <div class="tier__cabecera">
                      <span class="rotulo-seccion">{{ nivel.name }}</span>
                      <span
                        class="tier__barra"
                        role="img"
                        [attr.aria-label]="t(clavePresencia(nivel.logo_size))"
                      >
                        <span [style.width.%]="presencia(nivel.logo_size)"></span>
                      </span>
                    </div>
                    <ul class="tier__logos" [class]="'tamano-' + nivel.logo_size">
                      @for (patrocinador of nivel.sponsors; track $index + patrocinador.name) {
                        <li>
                          <a [routerLink]="ruta('patrocinadores', patrocinador.id) | enlace">
                            @if (patrocinador.logo_url) {
                              <img [src]="patrocinador.logo_url" [alt]="patrocinador.name" />
                            } @else {
                              {{ patrocinador.name }}
                            }
                          </a>
                        </li>
                      }
                    </ul>
                  </div>
                }
              </div>
            </section>
          }

          @if (
            evento.location_name ||
            evento.location_address ||
            evento.online_url ||
            (evento.location_mode !== 'online' && evento.nearby_places?.length)
          ) {
            <section
              class="seccion"
              [attr.aria-labelledby]="
                evento.location_name || evento.location_address || evento.online_url
                  ? 'lugar-h2'
                  : 'cercanos-h2'
              "
            >
              <div class="ancho-maximo lugar__grid" appReveal>
                @if (evento.location_name || evento.location_address || evento.online_url) {
                  <div>
                    <span class="rotulo-seccion">{{ t('publico.eventos.lugar.rotulo') }}</span>
                    <h2 id="lugar-h2">
                      {{ evento.location_name || t('publico.eventos.lugar.titulo') }}
                    </h2>
                    @if (evento.location_address) {
                      <p class="lugar__direccion">{{ evento.location_address }}</p>
                    }
                    @if (evento.location_mode !== 'online') {
                      <app-directions-link
                        [lugar]="evento.location_name"
                        [direccion]="evento.location_address"
                      />
                    }
                    @if (evento.location_mode !== 'in_person' && evento.online_url) {
                      <p>
                        <a [href]="evento.online_url" rel="noopener noreferrer" target="_blank">
                          {{ t('publico.eventos.enlaceOnline') }}
                        </a>
                      </p>
                    }
                    @if (evento.latitude !== null && evento.longitude !== null) {
                      <app-venue-map
                        class="lugar__mapa"
                        [marcadores]="[
                          {
                            lat: evento.latitude,
                            lng: evento.longitude,
                            label: evento.location_name,
                          },
                        ]"
                        [ariaLabel]="
                          t('publico.eventos.lugar.mapaAria', {
                            lugar: evento.location_name || evento.title,
                          })
                        "
                      />
                    } @else {
                      <!-- Sin geocodificar (sin dirección, evento online, o falló):
                         no se inventa un mapa ni un esquema con datos de ejemplo. -->
                      <p class="hint pendiente lugar__mapa">
                        {{ t('publico.eventos.datoPendiente') }}
                      </p>
                    }
                  </div>
                }
                @if (evento.location_mode !== 'online' && evento.nearby_places?.length) {
                  <div>
                    <app-event-nearby-section [sitios]="evento.nearby_places!" />
                  </div>
                }
              </div>
            </section>
          }
        </article>
      }
    </ng-container>
  `,
  styleUrl: './event-page.css',
})
export class EventPage implements OnInit {
  /** Idioma de la visita, para fechas e importes. */
  private readonly idioma = inject(LOCALE_ID);
  // Sin valor en la vista previa, que llega por `eventId` (`/vista-previa/:eventId`).
  readonly org = input<string | undefined>('');
  readonly slug = input<string | undefined>('');
  /** Vista previa del panel: la ficha de cualquier evento de la organización,
   * también un borrador, desde `GET /events/{id}/preview` y solo en el navegador. */
  readonly eventId = input<string | undefined>(undefined);

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly documento = inject(DOCUMENT);
  private readonly idiomaDeLaPagina = inject(IdiomaService);
  private readonly transferState = inject(TransferState);
  private readonly aplicarTema = temaDeEvento();
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = seoDePagina();
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);
  private readonly route = inject(ActivatedRoute);
  private readonly viewportScroller = inject(ViewportScroller);

  protected readonly evento = signal<PublicEventDetail | null>(null);
  /** Mientras la IA traduce lo pendiente: esqueleto en vez del original. */
  protected readonly traduciendo = traduccionEnVivo({
    ruta: () => (this.eventId() ? null : apiEvento(this.org() ?? '', this.slug() ?? '')),
    pendiente: () => this.evento()?.translating ?? false,
    recargar: () => this.cargar(),
  });
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);
  /** En la vista previa, un fallo que no es «no existe» (permiso retirado, red,
   * servidor): quien revisa debe saber que no es que el evento falte. */
  protected readonly errorDeVistaPrevia = signal(false);

  /** Desplaza al ancla de la URL (p. ej. `#agenda-h2` desde la miga de pan
   * "Programa" de `session-page.ts`/`sponsor-page.ts`) una vez el evento ya
   * está pintado. El `anchorScrolling` del router por sí solo no basta: el
   * contenido llega en una petición HTTP aparte (`cargar()`), así que en la
   * navegación el elemento del ancla todavía no existe en el DOM cuando el
   * router intenta desplazarse — mismo motivo por el que `legal-page.ts` usa
   * un `effect()` en vez de un `afterNextRender` de una sola vez. */
  private readonly _scrollAlAncla = effect(() => {
    if (!this.evento() || this.api.isServer) {
      return;
    }
    const fragmento = this.route.snapshot.fragment;
    if (fragmento) {
      // La cabecera es `position: sticky` (64px, `public-shell.ts`): sin este
      // desplazamiento, `scrollToAnchor` deja el título de la sección tapado
      // debajo de ella en vez de justo por debajo.
      this.viewportScroller.setOffset([0, 116]);
      queueMicrotask(() => this.viewportScroller.scrollToAnchor(fragmento));
    }
  });

  protected readonly dias = computed<DiaDeAgenda[]>(() => {
    const evento = this.evento();
    const sesiones = evento?.sessions ?? [];
    const zona = evento?.timezone ?? 'UTC';
    const grupos = new Map<string, (typeof sesiones)[number][]>();
    for (const sesion of sesiones) {
      const fecha = fechaEnZona(sesion.starts_at, zona);
      const lista = grupos.get(fecha) ?? [];
      lista.push(sesion);
      grupos.set(fecha, lista);
    }
    return [...grupos.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([fecha, sesiones]) => ({ fecha, sesiones }));
  });

  /** Los ponentes enlazados al evento (`speakers`, tengan o no sesión) y, tras
   * ellos, quien sale en la agenda sin estar en ese roster (moderación, etc.)
   * solo si tiene perfil público: en la agenda ya sale con su nombre, y aquí no
   * se presenta como ponente a quien no lo es. Cada grupo, por nombre. Se deduplica por `ref`, que la API hace igual en los
   * dos sitios: quien participa en varias sesiones se queda con su primer rol. */
  protected readonly ponentes = computed<Speaker[]>(() => {
    const evento = this.evento();
    const vistos = new Map<string, Speaker>();
    const anadir = (personas: readonly PublicParticipant[]): void => {
      const nuevas = personas
        .filter((persona) => !vistos.has(persona.ref))
        .sort((a, b) => a.display_name.localeCompare(b.display_name, this.idioma));
      for (const persona of nuevas) {
        if (vistos.has(persona.ref)) continue;
        vistos.set(persona.ref, {
          ref: persona.ref,
          publicSlug: persona.public_slug,
          displayName: persona.display_name,
          roleKey: persona.role_key,
        });
      }
    };
    anadir(evento?.speakers ?? []);
    anadir(
      (evento?.sessions ?? [])
        .flatMap((sesion) => sesion.participants)
        .filter((persona) => persona.public_slug !== null),
    );
    return [...vistos.values()];
  });

  /** Absoluta y sin ancla ni query: es lo que se comparte. En el SSR,
   * `location` ya es la URL pública de la petición. */
  protected urlPublica(evento: PublicEventDetail): string {
    return `${this.documento.location.origin}${this.idiomaDeLaPagina.enlace(urlEvento(evento.organization.slug, evento.slug))}`;
  }

  protected migasDePan(evento: PublicEventDetail): BreadcrumbItem[] {
    return migasDeEvento({
      inicio: this.transloco.translate('comun.inicio'),
      organizacion: evento.organization,
      eventoSlug: evento.slug,
      eventoTitulo: evento.title,
    });
  }

  /** Ruta hacia otra página de este mismo evento. */
  protected ruta(...resto: string[]): string[] {
    const evento = this.evento();
    return rutaEvento(
      evento?.organization.slug ?? this.org() ?? '',
      evento?.slug ?? this.slug() ?? '',
      ...resto,
    );
  }

  protected readonly formato = computed(() => {
    const modo = this.evento()?.location_mode ?? 'in_person';
    return { clave: CLAVES_FORMATO[modo] };
  });

  protected readonly registro = computed(() => {
    const modo = this.evento()?.registration_mode ?? 'free';
    return CLAVES_REGISTRO[modo];
  });

  protected readonly entradaGratuita = computed(
    () => (this.evento()?.registration_mode ?? 'free') === 'free',
  );

  /** Sin entradas a la venta en un evento de pago: aviso en lugar del botón. */
  protected readonly avisoVenta = computed(() => {
    const evento = this.evento();
    return evento ? avisoDeVenta(evento, null, false, Date.now(), this.idioma) : null;
  });

  /** «Desde X €» con el tipo de entrada vigente más barato
   * (`price_from_cents`/`price_currency`). `null` si el evento es gratis o,
   * siendo de pago, no tiene ningún tipo vigente ahora mismo — el chip cae
   * entonces a la etiqueta genérica «Entrada de pago». */
  protected readonly precioDesde = computed(() => {
    const evento = this.evento();
    if (!evento || evento.price_from_cents === null || evento.price_currency === null) {
      return null;
    }
    return formatearPrecio(evento.price_from_cents, evento.price_currency, this.idioma);
  });

  /** Ocupación del aforo en porcentaje entero, acotada a 100: `reserved_count`
   * puede superar `capacity` (sobreventa o aforo ampliado a la baja). */
  protected readonly ocupacion = computed(() => {
    const evento = this.evento();
    if (!evento?.capacity) {
      return 0;
    }
    return Math.min(100, Math.round((evento.reserved_count / evento.capacity) * 100));
  });

  protected readonly plazasDisponibles = computed(() => {
    const evento = this.evento();
    if (!evento?.capacity) {
      return 0;
    }
    return Math.max(0, evento.capacity - evento.reserved_count);
  });

  /** Presencia del nivel de patrocinio, según el tamaño de logo que ya define
   * el backend (`logo_size`): no es una métrica de aportación. */
  protected presencia(tamano: string): number {
    return tamano === 'large' ? 100 : tamano === 'medium' ? 62 : 30;
  }

  protected clavePresencia(tamano: string): string {
    if (tamano === 'large') {
      return 'publico.eventos.patrocinadores.presenciaOro';
    }
    return tamano === 'medium'
      ? 'publico.eventos.patrocinadores.presenciaMedia'
      : 'publico.eventos.patrocinadores.presenciaBasica';
  }

  /** El atributo de ámbito, presente **solo** si el evento eligió plantilla. */
  protected readonly ambitoDelEvento = computed(() => (this.evento()?.theme ? 'evento' : null));

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const eventId = this.eventId();
    if (eventId) {
      await this.cargarVistaPrevia(eventId);
      return;
    }
    const clave = makeStateKey<PublicEventDetail>(`public-event:${this.org()}:${this.slug()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const evento = await firstValueFrom(
        this.http.get<PublicEventDetail>(
          this.api.url(apiEvento(this.org() ?? '', this.slug() ?? '')),
          {
            headers: this.api.serverForwardHeaders(),
          },
        ),
      );
      this.aplicar(evento);
      if (this.api.isServer) {
        this.transferState.set(clave, evento);
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        this.noEncontrado.set(true);
        this.notFound.mark();
      } else {
        this.noEncontrado.set(true);
      }
    } finally {
      this.cargando.set(false);
    }
  }

  /** Sin `TransferState` ni SSR: la ruta se pinta en el navegador, que es quien
   * tiene la sesión del equipo. */
  private async cargarVistaPrevia(eventId: string): Promise<void> {
    try {
      const evento = await firstValueFrom(
        this.http.get<PublicEventDetail>(this.api.url(`/events/${eventId}/preview`)),
      );
      this.aplicar(evento, { vistaPrevia: true });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        this.noEncontrado.set(true);
      } else {
        this.errorDeVistaPrevia.set(true);
      }
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicar(evento: PublicEventDetail, { vistaPrevia = false } = {}): void {
    this.evento.set(evento);
    // La plantilla del evento se inyecta al llegar el dato, no al construir el
    // componente: en SSR el `document` no existe al construirlo, y quitarla
    // cuando no hay tema propio es lo que deja pasar la de la organización.
    this.aplicarTema(evento.theme);
    this.seo.set({
      contenidoDelOrganizador: true,
      ...idiomasDeLaRespuesta(evento),
      title: evento.title,
      description: evento.summary ?? this.transloco.translate('publico.eventos.sinResumen'),
      image: evento.cover_url,
      canonica: urlEvento(evento.organization.slug, evento.slug),
      // «Solo con enlace»: se abre por su URL, pero los buscadores no deben indexarlo.
      noIndexar: vistaPrevia || evento.visibility === 'hidden',
    });
  }
}
