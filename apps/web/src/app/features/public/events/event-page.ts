import { DatePipe, ViewportScroller } from '@angular/common';
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
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { formatearPrecio } from '../../../shared/text/formatear-precio';
import { Alert } from '../../../shared/ui/alert';
import { Breadcrumb, type BreadcrumbItem } from '../../../shared/ui/breadcrumb';
import { Chip, type ChipTone } from '../../../shared/ui/chip';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { VenueMap } from '../../../shared/ui/venue-map';
import type { LocationMode, PublicEventDetail, RegistrationMode } from './event-page.types';
import { type DiaDeAgenda, EventAgendaSection } from './sections/event-agenda-section';
import { type Speaker, EventSpeakersSection } from './sections/event-speakers-section';

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
 * accesibles, ponentes derivados de la agenda, patrocinadores por nivel y
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
    DatePipe,
    RouterLink,
    TranslocoDirective,
    Alert,
    Breadcrumb,
    Chip,
    VenueMap,
    Reveal,
    EventAgendaSection,
    EventSpeakersSection,
  ],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p class="ancho-maximo">{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <div class="ancho-maximo">
          <app-alert tone="error">{{ t('publico.eventos.noEncontrado') }}</app-alert>
        </div>
      } @else if (evento(); as evento) {
        <article>
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
                  <app-chip [tone]="registro().tono">{{ t(registro().clave) }}</app-chip>
                </div>
                @if (evento.cover_url) {
                  <img class="portada" [src]="evento.cover_url" [alt]="evento.title" />
                }
                <h1>{{ evento.title }}</h1>
                @if (evento.summary) {
                  <p class="hero__lede">{{ evento.summary }}</p>
                }
                @if (evento.description) {
                  <p class="hero__descripcion">{{ evento.description }}</p>
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
                  <a
                    class="ficha__inscribirse"
                    [routerLink]="['/eventos', evento.slug, 'inscribirse']"
                  >
                    {{ t('publico.eventos.inscribirse') }}
                  </a>
                  <p class="ficha__nota">{{ t('publico.eventos.ficha.sinCuenta') }}</p>
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
                      <a class="mark" [routerLink]="['/eventos', evento.slug, 'programa']">
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
                          <a
                            [routerLink]="[
                              '/eventos',
                              evento.slug,
                              'patrocinadores',
                              patrocinador.id,
                            ]"
                          >
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

          @if (evento.location_name || evento.location_address || evento.online_url) {
            <section class="seccion" aria-labelledby="lugar-h2">
              <div class="ancho-maximo lugar__grid" appReveal>
                <div>
                  <span class="rotulo-seccion">{{ t('publico.eventos.lugar.rotulo') }}</span>
                  <h2 id="lugar-h2">
                    {{ evento.location_name || t('publico.eventos.lugar.titulo') }}
                  </h2>
                  @if (evento.location_address) {
                    <p class="lugar__direccion">{{ evento.location_address }}</p>
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
                <div>
                  <span class="rotulo-seccion">{{ t('publico.eventos.lugar.cercaRotulo') }}</span>
                  <h2>{{ t('publico.eventos.lugar.cercaTitulo') }}</h2>
                  <!-- Alojamiento y locales cercanos: sin modelo de datos todavía, se
                       declara el hueco en vez de rellenarlo con ejemplos. -->
                  <p class="hint pendiente">{{ t('publico.eventos.lugar.cercaPendiente') }}</p>
                </div>
              </div>
            </section>
          }
        </article>
      }
    </ng-container>
  `,
  styles: `
    .hero {
      padding: var(--sp-8) 0 var(--sp-7);
      border-bottom: 1px solid var(--border);
    }
    .hero app-breadcrumb {
      display: block;
      margin-bottom: var(--sp-5);
    }
    .hero__grid {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(18.75rem, 0.65fr);
      gap: var(--sp-7);
      align-items: start;
    }
    .hero__kicker {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-4);
      align-items: center;
      margin-bottom: var(--sp-5);
    }
    .portada {
      width: 100%;
      max-height: 20rem;
      object-fit: cover;
      border-radius: var(--radius-lg);
      margin-bottom: var(--sp-4);
    }
    h1 {
      margin: 0;
    }
    .hero__lede {
      max-width: 56ch;
      color: var(--muted);
      margin-top: var(--sp-5);
    }
    .hero__descripcion {
      max-width: 64ch;
      margin-top: var(--sp-5);
      white-space: pre-line;
    }
    .ficha {
      display: grid;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
    }
    .ficha__fila {
      display: flex;
      justify-content: space-between;
      gap: var(--sp-4);
      padding: 14px var(--sp-5);
      border-bottom: 1px solid var(--border);
    }
    .ficha__fila:last-of-type {
      border-bottom: 0;
    }
    .ficha__etiqueta {
      color: var(--muted);
    }
    /* Único valor de la ficha con refuerzo visual propio: es el dato que más
       empuja a la persona a inscribirse, así que se destaca en verde y con
       más peso que el resto de filas (texto plano en gris). */
    .ficha__precio {
      color: var(--accent);
      font-weight: 700;
      font-size: 1.25rem;
    }
    .ficha__cta {
      padding: var(--sp-5);
      border-top: 1px solid var(--border);
      background-color: var(--surface-2);
      border-radius: 0 0 var(--radius-md) var(--radius-md);
      display: grid;
      gap: var(--sp-4);
    }
    /* .seats (evento-iawic.html:21): barra de ocupación del aforo. */
    .ficha__aforo {
      display: grid;
      gap: 2px;
    }
    .seats {
      height: 6px;
      border: 1px solid var(--border-strong);
      border-radius: 2px;
      overflow: hidden;
      background-color: var(--bg);
      margin: 10px 0 8px;
    }
    .seats > span {
      display: block;
      height: 100%;
      background-color: var(--accent);
    }
    .ficha__nota {
      margin: 0;
      text-align: center;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .pendiente {
      color: var(--muted);
      font-style: italic;
    }
    .ficha__inscribirse {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      min-height: 2.75rem;
      padding: 0 1.25rem;
      border-radius: var(--radius-sm);
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
      text-decoration: none;
      transition: background-color 0.15s ease;
    }
    .ficha__inscribirse:hover {
      background-color: var(--accent-hi);
    }
    .seccion {
      padding: var(--sp-8) 0;
    }
    .seccion__cabecera {
      margin-bottom: var(--sp-6);
    }
    .seccion__cabecera h2 {
      margin-top: var(--sp-1);
    }
    .vacio {
      color: var(--muted);
    }
    .tier {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      margin-bottom: var(--sp-4);
      overflow: hidden;
    }
    .tier__cabecera {
      display: flex;
      align-items: center;
      gap: var(--sp-4);
      padding: 12px var(--sp-5);
      background-color: var(--surface-2);
      border-bottom: 1px solid var(--border);
    }
    /* .tier__bar (evento-iawic.html:47-49): presencia del nivel, no una métrica. */
    .tier__barra {
      flex: 1;
      max-width: 13.75rem;
      height: 8px;
      border: 1px solid var(--border-strong);
      border-radius: 2px;
      background-color: var(--bg);
      overflow: hidden;
    }
    .tier__barra > span {
      display: block;
      height: 100%;
      background-color: var(--muted);
    }
    .tier--large .tier__barra > span {
      background-color: var(--accent);
    }
    .tier__logos {
      list-style: none;
      margin: 0;
      padding: var(--sp-5);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--sp-4);
    }
    .tier__logos img {
      display: block;
      width: auto;
      object-fit: contain;
    }
    .tier__logos.tamano-large img {
      height: 4.5rem;
    }
    .tier__logos.tamano-medium img {
      height: 3rem;
    }
    .tier__logos.tamano-small img {
      height: 2rem;
    }
    .tier__logos a {
      display: inline-block;
    }
    .lugar__direccion {
      color: var(--muted);
      white-space: pre-line;
    }
    /* .cols2 (evento-iawic.html:58): dos columnas que se apilan en pantalla estrecha. */
    .lugar__grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(18.75rem, 1fr));
      gap: var(--sp-6);
    }
    .lugar__grid h2 {
      margin: 12px 0 20px;
    }
    /* Sustituye al esquema SVG de .map (evento-iawic.html:61): mapa real
       (Leaflet, componente app-venue-map) en el mismo hueco visual. */
    .lugar__mapa {
      display: block;
      margin-top: var(--sp-5);
    }
    @media (max-width: 56.25rem) {
      .hero__grid {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class EventPage implements OnInit {
  readonly slug = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);
  private readonly route = inject(ActivatedRoute);
  private readonly viewportScroller = inject(ViewportScroller);

  protected readonly evento = signal<PublicEventDetail | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);

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

  /** Ponentes reales derivados de la agenda: no existe ningún endpoint
   * aparte de la agenda, así que se agrupan los participantes con perfil
   * público (`public_slug`), sin duplicar a quien participa en varias
   * sesiones (se queda con el primer rol con el que aparece). */
  protected readonly ponentes = computed<Speaker[]>(() => {
    const vistos = new Map<string, Speaker>();
    for (const sesion of this.evento()?.sessions ?? []) {
      for (const persona of sesion.participants) {
        if (persona.public_slug && !vistos.has(persona.public_slug)) {
          vistos.set(persona.public_slug, {
            publicSlug: persona.public_slug,
            displayName: persona.display_name,
            roleKey: persona.role_key,
          });
        }
      }
    }
    return [...vistos.values()];
  });

  protected migasDePan(evento: PublicEventDetail): BreadcrumbItem[] {
    return [
      {
        label: this.transloco.translate('publico.eventos.listadoTitulo'),
        routerLink: ['/eventos'],
      },
      { label: evento.title },
    ];
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

  /** «Desde X €» con el tipo de entrada vigente más barato
   * (`price_from_cents`/`price_currency`). `null` si el evento es gratis o,
   * siendo de pago, no tiene ningún tipo vigente ahora mismo — el chip cae
   * entonces a la etiqueta genérica «Entrada de pago». */
  protected readonly precioDesde = computed(() => {
    const evento = this.evento();
    if (!evento || evento.price_from_cents === null || evento.price_currency === null) {
      return null;
    }
    return formatearPrecio(evento.price_from_cents, evento.price_currency);
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

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PublicEventDetail>(`public-event:${this.slug()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const evento = await firstValueFrom(
        this.http.get<PublicEventDetail>(this.api.url(`/public/events/${this.slug()}`), {
          headers: this.api.serverForwardHeaders(),
        }),
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

  private aplicar(evento: PublicEventDetail): void {
    this.evento.set(evento);
    this.seo.set({
      title: evento.title,
      description: evento.summary ?? this.transloco.translate('publico.eventos.sinResumen'),
      image: evento.cover_url,
    });
  }
}
