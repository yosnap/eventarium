import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  inject,
  input,
  makeStateKey,
  signal,
} from '@angular/core';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { iniciales } from '../../../shared/text/iniciales';
import { Alert } from '../../../shared/ui/alert';
import { Breadcrumb, type BreadcrumbItem } from '../../../shared/ui/breadcrumb';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { claveTipoSesion, rolLegible } from './event-page.types';
import { resolveVideoEmbed } from './video-embed';

interface PublicParticipant {
  readonly display_name: string;
  readonly role_key: string;
  readonly public_slug: string | null;
}

interface PublicSessionDetail {
  readonly id: string;
  readonly session_type: string;
  readonly title: string;
  readonly description: string | null;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly room: string | null;
  readonly video_platform: string | null;
  readonly video_url: string | null;
  readonly materials: readonly { url?: string; label?: string }[];
  readonly participants: readonly PublicParticipant[];
  readonly event_slug: string;
  readonly event_title: string;
}

/** Clave de `localStorage` de «Guardar en mi agenda» (`ficha-sesion.html:288`):
 * sin cuenta, solo en este navegador — mismo criterio que el script del
 * prototipo, reescrito como parte del componente en vez de un `<script>`
 * inline. */
const CLAVE_AGENDA = 'eventarium-agenda';

/**
 * Página pública de una sesión (ponencia): sobre `.top`/`.side`/`.autor` de
 * la referencia (`ficha-sesion.html`), con ponentes, materiales y vídeo
 * embebido según su plataforma. Mismo patrón de carga que `EventPage`.
 *
 * Huecos de datos reales frente a la referencia, documentados aquí en vez de
 * rellenados con texto inventado: sin idioma de la sesión, sin nivel, sin
 * estado de inscripción propio de la sesión (la inscripción es del evento,
 * no de la sesión), sin previsión de grabación ni subtítulos, y sin bloque
 * "para quién es"/guion minuto a minuto/accesibilidad de sala/sesiones
 * relacionadas — nada de eso tiene un campo real en `PublicSessionDetail`,
 * así que esas secciones del prototipo no se replican.
 */
@Component({
  selector: 'app-session-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert, Breadcrumb, Reveal],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p class="ancho-maximo">{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <p class="ancho-maximo">
          <app-alert tone="error">{{ t('publico.eventos.noEncontrado') }}</app-alert>
        </p>
      } @else if (sesion(); as sesion) {
        <article class="ancho-maximo">
          <app-breadcrumb
            [items]="migasDePan(sesion)"
            [ariaLabel]="t('publico.eventos.sesion.ruta')"
          />

          <div class="top" appReveal>
            <div>
              <span class="rotulo-seccion">
                {{ t(claveTipoSesion(sesion.session_type)) }}
                @if (sesion.room) {
                  · {{ sesion.room }}
                }
              </span>
              <h1>{{ sesion.title }}</h1>

              <div class="cuando">
                <span
                  ><strong>{{ sesion.starts_at | date: 'EEE d.MM.yyyy' }}</strong></span
                >
                <span>
                  <strong>
                    {{ sesion.starts_at | date: 'HH:mm' }} –
                    {{ sesion.ends_at | date: 'HH:mm' }}
                  </strong>
                </span>
                <span>{{ duracion(sesion, t) }}</span>
              </div>

              @if (sesion.description) {
                <p class="prosa">{{ sesion.description }}</p>
              }

              @if (sesion.participants.length > 0) {
                <div class="autor">
                  @for (persona of sesion.participants; track persona.display_name) {
                    <div class="autor__persona">
                      <span class="autor__marca" aria-hidden="true">{{
                        iniciales(persona.display_name)
                      }}</span>
                      <div>
                        @if (persona.public_slug) {
                          <a [routerLink]="['/ponentes', persona.public_slug]">
                            {{ persona.display_name }}
                          </a>
                        } @else {
                          <span>{{ persona.display_name }}</span>
                        }
                        <div class="hint">{{ rolLegible(persona.role_key, t) }}</div>
                      </div>
                    </div>
                  }
                </div>
              }
            </div>

            <aside class="lateral" aria-label="{{ t('publico.eventos.sesion.datosAria') }}">
              <div class="lateral__fila">
                <span class="muted">{{ t('publico.eventos.sesion.lado.formato') }}</span>
                <span>{{ t(claveTipoSesion(sesion.session_type)) }}</span>
              </div>
              @if (sesion.room) {
                <div class="lateral__fila">
                  <span class="muted">{{ t('publico.eventos.sesion.lado.sala') }}</span>
                  <span>{{ sesion.room }}</span>
                </div>
              }
              <div class="lateral__cta">
                <button
                  type="button"
                  class="guardar"
                  [class.guardar--activo]="guardada()"
                  [attr.aria-pressed]="guardada()"
                  (click)="alternarGuardado()"
                >
                  {{
                    guardada()
                      ? t('publico.eventos.sesion.agenda.quitar')
                      : t('publico.eventos.sesion.agenda.guardar')
                  }}
                </button>
                <p class="lateral__nota">
                  {{
                    guardada()
                      ? t('publico.eventos.sesion.agenda.notaGuardada')
                      : t('publico.eventos.sesion.agenda.notaNoGuardada')
                  }}
                </p>
              </div>
            </aside>
          </div>

          @if (embed(); as video) {
            <section class="seccion" appReveal>
              <div class="seccion__cabecera">
                <span class="rotulo-seccion">{{ t('publico.eventos.video') }}</span>
                <h2>{{ t('publico.eventos.video') }}</h2>
              </div>
              @if (video.kind === 'iframe' && safeVideoSrc(); as src) {
                <iframe
                  class="video"
                  [src]="src"
                  title="{{ t('publico.eventos.video') }}"
                  allow="autoplay; encrypted-media; picture-in-picture"
                  allowfullscreen
                ></iframe>
              } @else {
                <a [href]="video.src" rel="noopener noreferrer" target="_blank">
                  {{ t('publico.eventos.verVideo') }}
                </a>
              }
            </section>
          }

          @if (sesion.materials.length > 0) {
            <section class="seccion" appReveal>
              <div class="seccion__cabecera">
                <span class="rotulo-seccion">{{ t('publico.eventos.materiales') }}</span>
                <h2>{{ t('publico.eventos.materiales') }}</h2>
              </div>
              <div class="mat">
                @for (material of sesion.materials; track $index) {
                  @if (material.url) {
                    <a
                      class="mat__item"
                      [href]="material.url"
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {{ material.label || material.url }}
                    </a>
                  }
                }
              </div>
            </section>
          }
        </article>
      }
    </ng-container>
  `,
  styles: `
    .ancho-maximo {
      padding: var(--space-lg) 0;
    }
    app-breadcrumb {
      display: block;
      margin-bottom: var(--sp-5);
    }
    /* .top (ficha-sesion.html:17-18): cabecera + panel lateral, apilados bajo
       el punto de corte de la referencia (860px). */
    .top {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(16.25rem, 20rem);
      gap: var(--sp-7);
      align-items: start;
      margin-top: var(--sp-5);
      padding-bottom: var(--sp-7);
      border-bottom: 1px solid var(--border);
    }
    @media (max-width: 53.75rem) {
      .top {
        grid-template-columns: 1fr;
      }
    }
    h1 {
      max-width: 20ch;
      margin-top: var(--sp-4);
      line-height: 1.05;
    }
    .cuando {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-4);
      margin-top: var(--sp-5);
      font-family: var(--font-mono);
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .cuando strong {
      color: var(--fg);
      font-weight: 400;
    }
    .prosa {
      max-width: 66ch;
      color: var(--muted);
      margin-top: var(--sp-5);
    }
    /* .autor (ficha-sesion.html:25-26): ponente(s) de la sesión, leídos de
       la lista de participantes — sin bio ni empresa, ese dato vive en el
       perfil del ponente, no se reescribe aquí. */
    .autor {
      display: grid;
      gap: var(--sp-4);
      margin-top: var(--sp-6);
      padding-top: var(--sp-5);
      border-top: 1px solid var(--border);
    }
    .autor__persona {
      display: flex;
      gap: var(--sp-4);
      align-items: center;
    }
    .autor__marca {
      flex: 0 0 auto;
      width: 3.375rem;
      height: 3.375rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--surface);
      display: grid;
      place-items: center;
      font-family: var(--font-display);
      font-size: 1.35rem;
      letter-spacing: 0.04em;
      color: var(--muted);
      padding-top: 4px;
    }
    .hint {
      color: var(--muted);
      font-size: var(--fs-sm);
      margin-top: 4px;
    }
    .lateral {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
    }
    .lateral__fila {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: baseline;
      gap: var(--space-sm) var(--space-md);
      padding: 13px 1.25rem;
      border-bottom: 1px solid var(--border);
    }
    .lateral__cta {
      padding: 1.25rem;
      border-top: 1px solid var(--border);
    }
    .guardar {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      min-height: 2.75rem;
      padding: 0 1.25rem;
      border: 1px solid transparent;
      border-radius: var(--radius-sm);
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
      font-family: inherit;
      font-size: inherit;
      cursor: pointer;
      transition:
        background-color 0.15s ease,
        border-color 0.15s ease,
        color 0.15s ease;
    }
    .guardar:hover {
      background-color: var(--accent-hi);
    }
    .guardar--activo {
      background-color: transparent;
      border-color: var(--border-strong);
      color: var(--fg);
    }
    .guardar--activo:hover {
      background-color: var(--surface-hi);
    }
    .lateral__nota {
      margin: 10px 0 0;
      text-align: center;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .seccion {
      padding-top: var(--sp-7);
    }
    .seccion__cabecera {
      margin-bottom: var(--sp-5);
    }
    .seccion__cabecera h2 {
      margin-top: var(--sp-1);
    }
    .video {
      width: 100%;
      aspect-ratio: 16 / 9;
      border: none;
      border-radius: var(--radius-md);
    }
    /* .mat (ficha-sesion.html:57-58): lista de materiales reales únicamente —
       sin las filas "Tras el evento" de la referencia, que anticipan
       materiales que el backend todavía no tiene. */
    .mat {
      display: grid;
      gap: 0;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      max-width: 70ch;
    }
    .mat__item {
      display: block;
      padding: 14px 1.25rem;
      border-bottom: 1px solid var(--border);
      color: inherit;
    }
    .mat__item:last-child {
      border-bottom: 0;
    }
    .mat__item:hover {
      background-color: var(--surface-hi);
    }
  `,
})
export class SessionPage implements OnInit {
  readonly slug = input.required<string>();
  readonly sessionId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);
  private readonly sanitizer = inject(DomSanitizer);

  protected readonly sesion = signal<PublicSessionDetail | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);
  protected readonly embed = signal<ReturnType<typeof resolveVideoEmbed>>(null);
  protected readonly guardada = signal(false);

  protected readonly iniciales = iniciales;
  protected readonly rolLegible = rolLegible;
  protected readonly claveTipoSesion = claveTipoSesion;

  /**
   * `[src]` de un `iframe` exige una `SafeResourceUrl`: Angular la bloquearía si
   * no se marca como segura. Es seguro marcarla aquí porque `resolveVideoEmbed`
   * siempre construye el valor desde un prefijo propio fijo (dominio del
   * reproductor oficial de cada plataforma), nunca a partir de la URL cruda
   * guardada por quien edita la sesión.
   */
  protected safeVideoSrc(): SafeResourceUrl | null {
    const video = this.embed();
    return video?.kind === 'iframe'
      ? this.sanitizer.bypassSecurityTrustResourceUrl(video.src)
      : null;
  }

  /** Eventos › evento › Programa (ancla a la agenda del evento, clicable) ›
   * charla actual (sin enlace, es la página en la que ya está la persona). */
  protected migasDePan(sesion: PublicSessionDetail): BreadcrumbItem[] {
    return [
      {
        label: this.transloco.translate('publico.eventos.listadoTitulo'),
        routerLink: ['/eventos'],
      },
      { label: sesion.event_title, routerLink: ['/eventos', sesion.event_slug] },
      {
        label: this.transloco.translate('publico.eventos.multisede.rotulo'),
        routerLink: ['/eventos', sesion.event_slug],
        fragment: 'agenda-h2',
      },
      { label: sesion.title },
    ];
  }

  /** Duración real de la sesión en minutos, con la misma escala de claves
   * i18n que `events-list-page.ts` (`duracion.minutos`/`duracion.horas`),
   * pero sin redondear a la hora completa: una charla de 90 min se lee mejor
   * como «1 h 30 min» que como «2 h». */
  protected duracion(
    sesion: PublicSessionDetail,
    traducir: (clave: string, params?: Record<string, unknown>) => string,
  ): string {
    const minutos = Math.round(
      (new Date(sesion.ends_at).getTime() - new Date(sesion.starts_at).getTime()) / 60_000,
    );
    if (minutos < 60) {
      return traducir('publico.eventos.duracion.minutos', { n: minutos });
    }
    const horas = Math.floor(minutos / 60);
    const resto = minutos % 60;
    const horasTexto = traducir('publico.eventos.duracion.horas', { n: horas });
    return resto === 0
      ? horasTexto
      : `${horasTexto} ${traducir('publico.eventos.duracion.minutos', { n: resto })}`;
  }

  ngOnInit(): void {
    if (!this.api.isServer) {
      this.guardada.set(this.leerAgenda().includes(this.idAgenda()));
    }
    void this.tareasPendientes.run(() => this.cargar());
  }

  private idAgenda(): string {
    return `${this.slug()}:${this.sessionId()}`;
  }

  private leerAgenda(): string[] {
    try {
      const bruto = localStorage.getItem(CLAVE_AGENDA);
      return bruto ? (JSON.parse(bruto) as string[]) : [];
    } catch {
      return [];
    }
  }

  /** «Guardar en mi agenda» (`ficha-sesion.html:286-317`): sin cuenta, solo
   * en este navegador. Si `localStorage` falla (modo privado, cuota), el
   * estado en memoria sigue reflejando el clic — solo no persiste entre
   * recargas, nunca se rompe el botón. */
  protected alternarGuardado(): void {
    if (this.api.isServer) {
      return;
    }
    const lista = this.leerAgenda();
    const id = this.idAgenda();
    const indice = lista.indexOf(id);
    if (indice === -1) {
      lista.push(id);
    } else {
      lista.splice(indice, 1);
    }
    try {
      localStorage.setItem(CLAVE_AGENDA, JSON.stringify(lista));
    } catch {
      // Ver docstring: solo se pierde la persistencia, no el estado visible.
    }
    this.guardada.set(indice === -1);
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PublicSessionDetail>(
      `public-session:${this.slug()}:${this.sessionId()}`,
    );
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const sesion = await firstValueFrom(
        this.http.get<PublicSessionDetail>(
          this.api.url(`/public/events/${this.slug()}/sessions/${this.sessionId()}`),
          { headers: this.api.serverForwardHeaders() },
        ),
      );
      this.aplicar(sesion);
      if (this.api.isServer) {
        this.transferState.set(clave, sesion);
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

  private aplicar(sesion: PublicSessionDetail): void {
    this.sesion.set(sesion);
    this.embed.set(
      resolveVideoEmbed(sesion.video_platform, sesion.video_url, this.api.currentHost()),
    );
    this.seo.set({
      title: `${sesion.title} · ${sesion.event_title}`,
      description: sesion.description ?? this.transloco.translate('publico.eventos.sinResumen'),
    });
  }
}
