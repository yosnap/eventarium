import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type ElementRef,
  type OnInit,
  PendingTasks,
  TransferState,
  computed,
  inject,
  input,
  makeStateKey,
  signal,
  viewChildren,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { Alert } from '../../../shared/ui/alert';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { type MarcadorDeMapa, VenueMap } from '../../../shared/ui/venue-map';
import type { PublicEventDetail, PublicEventSession, PublicVenue } from './event-page.types';
import { type EstiloDeSede, estiloDeSede } from './venue-colors';
import { VenueGridSection } from './sections/venue-grid-section';
import { VenueListSection } from './sections/venue-list-section';

/** Día de programa ya agrupado: fecha calendario en la zona del evento. */
interface DiaDePrograma {
  readonly fecha: string;
  readonly sesiones: readonly PublicEventSession[];
}

/** Fecha calendario (`AAAA-MM-DD`) de un instante, en la zona del evento. */
function fechaEnZona(iso: string, zona: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: zona,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(iso));
}

/**
 * Programa multisede de un evento, sobre `evento-multisede.html` del prototipo.
 *
 * Solo tiene sentido con dos o más sedes: la ficha de evento enlaza aquí en ese
 * caso, y si se llega con una sola sede se muestra igualmente (degradado, sin
 * parrilla cruzada) en vez de dar un 404 — la URL es válida aunque el evento no
 * use sedes.
 *
 * La parrilla cruza día × sede; los controles filtran por día y por sede. La
 * vista de lista es la misma información para pantallas estrechas (ver
 * `venue-list-section.ts`).
 */
@Component({
  selector: 'app-event-venues-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    RouterLink,
    TranslocoDirective,
    Alert,
    Reveal,
    VenueMap,
    VenueGridSection,
    VenueListSection,
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
            <div class="ancho-maximo" appReveal>
              <a class="volver" routerLink="/eventos">{{ t('publico.eventos.todosLosEventos') }}</a>
              <span class="rotulo-seccion">{{ evento.title }}</span>
              <h1>
                {{ dias().length }} {{ t('publico.eventos.multisede.tituloIntro') }}
                <span class="mark">{{ sedes().length }} {{ t(sufijoSedes()) }}</span>
              </h1>
              <p class="hero__intro">{{ t('publico.eventos.multisede.intro') }}</p>

              @if (sedes().length > 0) {
                <div class="sedes-grid">
                  @for (sede of sedes(); track sede.id; let i = $index) {
                    <div class="sede">
                      <span class="sede__nombre">
                        <span
                          class="punto"
                          [style.background-color]="estiloDeSede(i).relleno"
                          [style.border-color]="estiloDeSede(i).borde"
                          aria-hidden="true"
                        ></span>
                        <strong>{{ sede.name }}</strong>
                      </span>
                      <p class="hint sede__detalle">
                        @if (sede.capacity !== null) {
                          {{ t('publico.eventos.multisede.aforoSede', { n: sede.capacity }) }}
                          @if (sede.address) {
                            <br />
                          }
                        }
                        {{ sede.address }}
                      </p>
                    </div>
                  }
                </div>
              }
            </div>
          </section>

          @if (dias().length > 0) {
            <div class="controles">
              <div class="ancho-maximo controles__in">
                <div
                  class="dias"
                  role="tablist"
                  [attr.aria-label]="t('publico.eventos.diasAria')"
                >
                  @for (dia of dias(); track dia.fecha; let indice = $index) {
                    <button
                      #pestana
                      type="button"
                      role="tab"
                      [id]="'programa-tab-' + indice"
                      [attr.aria-selected]="indice === diaActivo()"
                      [tabIndex]="indice === diaActivo() ? 0 : -1"
                      (click)="seleccionarDia(indice, false)"
                      (keydown)="alPulsarTecla($event, indice)"
                    >
                      {{ dia.fecha + 'T00:00:00Z' | date: 'EEE dd' : 'UTC' }}
                    </button>
                  }
                </div>

                @if (sedes().length > 1) {
                  <div class="sedes" role="group" [attr.aria-label]="t('publico.eventos.multisede.sedesAria')">
                    @for (sede of sedes(); track sede.id; let i = $index) {
                      <button
                        type="button"
                        [attr.aria-pressed]="sedeVisible(sede.id)"
                        [attr.aria-label]="
                          t('publico.eventos.multisede.verSedeAria', { nombre: sede.name })
                        "
                        (click)="alternarSede(sede.id)"
                      >
                        <span
                          class="punto"
                          [class.punto--apagado]="!sedeVisible(sede.id)"
                          [style.background-color]="estiloDeSede(i).relleno"
                          [style.border-color]="estiloDeSede(i).borde"
                          aria-hidden="true"
                        ></span>
                        {{ sede.name }}
                      </button>
                    }
                  </div>
                }

                <p class="hint resumen" role="status" aria-live="polite">{{ resumen() }}</p>
              </div>
            </div>

            <section>
              <div class="ancho-maximo" appReveal>
                <div class="solo-ancho">
                  <app-venue-grid-section
                    [sesiones]="diaActivoSesiones()"
                    [sedes]="sedes()"
                    [sedesVisibles]="sedesVisibles()"
                    [fecha]="diaFecha()"
                    [eventTimezone]="evento.timezone"
                  />
                </div>
                <div class="solo-estrecho">
                  <app-venue-list-section
                    [sesiones]="diaActivoSesiones()"
                    [sedes]="sedes()"
                    [sedesVisibles]="sedesVisibles()"
                    [eventTimezone]="evento.timezone"
                  />
                </div>
              </div>
            </section>
          } @else {
            <section class="seccion">
              <div class="ancho-maximo">
                <p class="vacio">{{ t('publico.eventos.sinAgenda') }}</p>
              </div>
            </section>
          }

          <section class="seccion mover">
            <div class="ancho-maximo" appReveal>
              <span class="rotulo-seccion">{{ t('publico.eventos.multisede.mover') }}</span>
              <h2>{{ t('publico.eventos.multisede.moverTitulo') }}</h2>
              <!-- Tiempos de trayecto entre sedes: sin modelo de datos todavía. Se
                   declara el hueco en vez de rellenarlo con ejemplos. -->
              <p class="hint pendiente">{{ t('publico.eventos.multisede.moverPendiente') }}</p>
              @if (marcadoresDeSedes().length > 0) {
                <app-venue-map
                  class="mover__mapa"
                  [marcadores]="marcadoresDeSedes()"
                  [ariaLabel]="t('publico.eventos.multisede.mapaAria')"
                />
              }
              <p>
                <a [routerLink]="['/eventos', evento.slug]">
                  {{ t('publico.eventos.agenda') }} →
                </a>
              </p>
            </div>
          </section>
        </article>
      }
    </ng-container>
  `,
  styles: `
    .hero {
      padding: var(--sp-8) 0 var(--sp-6);
      border-bottom: 1px solid var(--border);
    }
    .volver {
      display: inline-flex;
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: var(--sp-5);
    }
    .volver:hover {
      color: var(--fg);
    }
    .hero h1 {
      font-size: var(--fs-h1);
      max-width: 18ch;
      margin-top: 16px;
    }
    .hero__intro {
      max-width: 58ch;
      color: var(--muted);
      margin-top: var(--sp-5);
    }
    /* .venues (evento-multisede.html:14). */
    .sedes-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
      gap: var(--sp-4);
      margin-top: var(--sp-6);
    }
    /* .venue (evento-multisede.html:15). */
    .sede {
      padding: var(--sp-5);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
    }
    .sede__nombre {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .sede__detalle {
      margin-top: 8px;
    }
    /* .controls (evento-multisede.html:22-24): se queda fija bajo la cabecera. */
    .controles {
      position: sticky;
      top: 64px;
      z-index: 30;
      padding: var(--sp-4) 0;
      background: var(--nav-bg);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }
    .controles__in {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-4);
      align-items: center;
    }
    .dias,
    .sedes {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
    }
    .dias button,
    .sedes button {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 2.375rem;
      padding: 0 14px;
      border: 0;
      border-radius: 3px;
      background-color: transparent;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.11em;
      text-transform: uppercase;
      cursor: pointer;
      transition:
        background-color 0.15s,
        color 0.15s;
    }
    .dias button:hover,
    .sedes button:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
    .dias button[aria-selected='true'] {
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
    }
    /* .sedes button[aria-pressed] (evento-multisede.html:31-32). */
    .sedes button[aria-pressed='true'] {
      background-color: var(--surface-hi);
      color: var(--fg);
      box-shadow: inset 0 -2px 0 var(--fg);
    }
    /* Tamaño/forma fijos; el color lo pone estiloDeSede() por [style.*]. */
    .punto {
      flex: 0 0 auto;
      width: 10px;
      height: 10px;
      border-radius: 2px;
      border: 1px solid var(--faint);
    }
    .punto--apagado {
      opacity: 0.35;
    }
    .resumen {
      margin-left: auto;
    }
    .seccion {
      padding: var(--sp-8) 0;
    }
    .mover {
      border-top: 1px solid var(--border);
    }
    .mover h2 {
      margin: 12px 0 20px;
    }
    .mover__mapa {
      display: block;
      margin: var(--sp-5) 0;
      max-width: 40rem;
    }
    .pendiente {
      font-style: italic;
    }
    .vacio {
      color: var(--muted);
    }
    /* La parrilla y la lista son la misma información: se muestra una u otra
       según el ancho, igual que la referencia (evento-multisede.html:71-75). No
       se consulta el ancho desde JavaScript porque el primer render ocurre en el
       servidor, sin ventana. */
    .solo-estrecho {
      display: none;
    }
    @media (max-width: 51.25rem) {
      .controles {
        position: static;
      }
      .solo-ancho {
        display: none;
      }
      .solo-estrecho {
        display: block;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .controles {
        backdrop-filter: none;
      }
    }
  `,
})
export class EventVenuesPage implements OnInit {
  readonly slug = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);
  private readonly pestanas = viewChildren<ElementRef<HTMLButtonElement>>('pestana');

  protected readonly evento = signal<PublicEventDetail | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);

  protected readonly diaActivo = signal(0);
  /** Sedes visibles: por defecto todas. El filtro es del visitante, no del modelo. */
  protected readonly sedesVisibles = signal<readonly string[]>([]);

  protected readonly sedes = computed<readonly PublicVenue[]>(() => this.evento()?.venues ?? []);

  /** Sedes visibles con coordenadas conocidas, listas para `app-venue-map`. Si
   * ninguna tiene coordenadas (geocodificación fail-open, puede fallar), el
   * array queda vacío y el bloque de mapa no se pinta. */
  protected readonly marcadoresDeSedes = computed<readonly MarcadorDeMapa[]>(() => {
    const visibles = this.sedesVisibles();
    return this.sedes()
      .map((sede, indice) => ({ sede, indice }))
      .filter(
        ({ sede }) =>
          visibles.includes(sede.id) && sede.latitude !== null && sede.longitude !== null,
      )
      .map(({ sede, indice }) => ({
        lat: sede.latitude as number,
        lng: sede.longitude as number,
        label: sede.name,
        color: estiloDeSede(indice).relleno,
      }));
  });

  protected readonly dias = computed<readonly DiaDePrograma[]>(() => {
    const evento = this.evento();
    const sesiones = evento?.sessions ?? [];
    const zona = evento?.timezone ?? 'UTC';
    const grupos = new Map<string, PublicEventSession[]>();
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

  protected readonly diaActivoSesiones = computed<readonly PublicEventSession[]>(
    () => this.dias()[this.diaActivo()]?.sesiones ?? [],
  );

  protected readonly diaFecha = computed(() => this.dias()[this.diaActivo()]?.fecha ?? '');

  /** Solo cuenta lo que se está viendo: el resumen es del filtro, no del evento. */
  protected readonly resumen = computed(() => {
    const visibles = this.sedesVisibles();
    const sesiones = this.diaActivoSesiones().filter((sesion) =>
      sesion.venue_id ? visibles.includes(sesion.venue_id) : false,
    );
    const etiquetaSedes = visibles.length === 1 ? 'sedeSingular' : 'sedePlural';
    const etiquetaSesiones = sesiones.length === 1 ? 'sesionSingular' : 'sesionPlural';
    return `${visibles.length} ${this.traducir(`publico.eventos.multisede.${etiquetaSedes}`)} · ${
      sesiones.length
    } ${this.traducir(`publico.eventos.multisede.${etiquetaSesiones}`)}`;
  });

  protected sufijoSedes(): string {
    return this.sedes().length === 1
      ? 'publico.eventos.multisede.sedeSingular'
      : 'publico.eventos.multisede.sedePlural';
  }

  protected estiloDeSede(indice: number): EstiloDeSede {
    return estiloDeSede(indice);
  }

  protected sedeVisible(id: string): boolean {
    return this.sedesVisibles().includes(id);
  }

  protected alternarSede(id: string): void {
    const actuales = this.sedesVisibles();
    this.sedesVisibles.set(
      actuales.includes(id) ? actuales.filter((sede) => sede !== id) : [...actuales, id],
    );
  }

  protected seleccionarDia(indice: number, enfocar: boolean): void {
    this.diaActivo.set(indice);
    if (enfocar) {
      this.pestanas()[indice]?.nativeElement.focus();
    }
  }

  protected alPulsarTecla(evento: KeyboardEvent, indice: number): void {
    const total = this.dias().length;
    let siguiente: number | null = null;
    if (evento.key === 'ArrowRight') {
      siguiente = (indice + 1) % total;
    } else if (evento.key === 'ArrowLeft') {
      siguiente = (indice - 1 + total) % total;
    }
    if (siguiente !== null) {
      evento.preventDefault();
      this.seleccionarDia(siguiente, true);
    }
  }

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private traducir(clave: string): string {
    return this.transloco.translate(clave);
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
      this.noEncontrado.set(true);
      if (error instanceof ApiError && error.status === 404) {
        this.notFound.mark();
      }
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicar(evento: PublicEventDetail): void {
    this.evento.set(evento);
    this.sedesVisibles.set(evento.venues.map((sede) => sede.id));
    this.seo.set({
      title: `${evento.title} · ${this.traducir('publico.eventos.multisede.rotulo')}`,
      description: evento.summary ?? this.traducir('publico.eventos.sinResumen'),
      image: evento.cover_url,
    });
  }
}
