import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  computed,
  inject,
  input,
  makeStateKey,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

interface PublicParticipant {
  readonly display_name: string;
  readonly role_key: string;
  readonly public_slug: string | null;
}

interface PublicEventSession {
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
}

interface PublicSponsor {
  readonly name: string;
  readonly logo_url: string | null;
  readonly website: string | null;
}

interface PublicSponsorTier {
  readonly name: string;
  readonly logo_size: 'large' | 'medium' | 'small';
  readonly sponsors: readonly PublicSponsor[];
}

interface PublicEventDetail {
  readonly slug: string;
  readonly title: string;
  readonly summary: string | null;
  readonly description: string | null;
  readonly cover_url: string | null;
  readonly timezone: string;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly location_mode: string;
  readonly location_name: string | null;
  readonly location_address: string | null;
  readonly online_url: string | null;
  readonly sessions: readonly PublicEventSession[];
  readonly sponsor_tiers: readonly PublicSponsorTier[];
}

interface DiaDeAgenda {
  readonly fecha: string;
  readonly sesiones: readonly PublicEventSession[];
}

/** `starts_at` (UTC) al día en hora local, sin arrastrar la zona horaria del navegador
 * al agrupar por fecha (mismo criterio que el editor de agenda del panel). */
function fechaLocal(iso: string): string {
  const fecha = new Date(iso);
  return new Date(fecha.getTime() - fecha.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

/**
 * Página pública de un evento: hero, lugar, agenda agrupada por día con sus
 * sesiones y participantes, y etiquetas OG para compartir.
 *
 * Carga los datos con `serverForwardHeaders()` + `TransferState`, siguiendo el
 * mismo patrón que `ThemingService` — nunca el de una página que solo espera un
 * `import()` sin pedir nada a la API, que en SSR serviría el hueco vacío o, peor,
 * datos de otra organización.
 */
@Component({
  selector: 'app-event-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <app-alert tone="error">{{ t('publico.eventos.noEncontrado') }}</app-alert>
      } @else if (evento(); as evento) {
        <article class="ancho-maximo">
          @if (evento.cover_url) {
            <img class="portada" [src]="evento.cover_url" [alt]="evento.title" />
          }
          <h1>{{ evento.title }}</h1>
          @if (evento.summary) {
            <p class="resumen">{{ evento.summary }}</p>
          }
          <p class="lugar">
            {{ evento.starts_at | date: 'fullDate' }}
            @if (evento.location_name) {
              · {{ evento.location_name }}
            }
            @if (evento.location_mode === 'online' && evento.online_url) {
              ·
              <a [href]="evento.online_url" rel="noopener noreferrer" target="_blank">
                {{ t('publico.eventos.enlaceOnline') }}
              </a>
            }
          </p>
          @if (evento.description) {
            <p class="descripcion">{{ evento.description }}</p>
          }

          <a class="inscribirse" [routerLink]="['/eventos', evento.slug, 'inscribirse']">
            {{ t('publico.eventos.inscribirse') }}
          </a>

          <h2>{{ t('publico.eventos.agenda') }}</h2>
          @if (dias().length === 0) {
            <p>{{ t('publico.eventos.sinAgenda') }}</p>
          }
          @for (dia of dias(); track dia.fecha) {
            <h3>{{ dia.fecha + 'T00:00:00' | date: 'fullDate' }}</h3>
            <ul class="sesiones">
              @for (sesion of dia.sesiones; track sesion.id) {
                <li>
                  <app-card>
                    <a [routerLink]="['/eventos', evento.slug, 'sesiones', sesion.id]">
                      <strong>{{ sesion.title }}</strong>
                    </a>
                    <span class="horario">
                      {{ sesion.starts_at | date: 'shortTime' }} –
                      {{ sesion.ends_at | date: 'shortTime' }}
                      @if (sesion.room) {
                        · {{ sesion.room }}
                      }
                    </span>
                    @if (sesion.participants.length > 0) {
                      <ul class="participantes">
                        @for (persona of sesion.participants; track persona.display_name) {
                          <li>
                            @if (persona.public_slug) {
                              <a [routerLink]="['/ponentes', persona.public_slug]">
                                {{ persona.display_name }}
                              </a>
                            } @else {
                              {{ persona.display_name }}
                            }
                            ({{ persona.role_key }})
                          </li>
                        }
                      </ul>
                    }
                  </app-card>
                </li>
              }
            </ul>
          }

          @if (evento.sponsor_tiers.length > 0) {
            <h2>{{ t('publico.eventos.patrocinadores.titulo') }}</h2>
            @for (nivel of evento.sponsor_tiers; track nivel.name) {
              <h3>{{ nivel.name }}</h3>
              <ul class="patrocinadores" [class]="'tamano-' + nivel.logo_size">
                @for (patrocinador of nivel.sponsors; track patrocinador.name) {
                  <li>
                    @if (patrocinador.website) {
                      <a [href]="patrocinador.website" rel="noopener noreferrer" target="_blank">
                        @if (patrocinador.logo_url) {
                          <img [src]="patrocinador.logo_url" [alt]="patrocinador.name" />
                        } @else {
                          {{ patrocinador.name }}
                        }
                      </a>
                    } @else if (patrocinador.logo_url) {
                      <img [src]="patrocinador.logo_url" [alt]="patrocinador.name" />
                    } @else {
                      <span>{{ patrocinador.name }}</span>
                    }
                  </li>
                }
              </ul>
            }
          }
        </article>
      }
    </ng-container>
  `,
  styles: `
    .ancho-maximo {
      padding: var(--space-lg) 0;
    }
    .portada {
      width: 100%;
      max-height: 320px;
      object-fit: cover;
      border-radius: var(--radius-lg);
    }
    h1 {
      margin: var(--space-md) 0 0;
    }
    .resumen {
      font-size: 1.125rem;
      color: var(--muted);
    }
    .lugar {
      color: var(--muted);
    }
    .inscribirse {
      display: inline-block;
      margin-top: var(--space-md);
      padding: var(--space-sm) var(--space-lg);
      border-radius: var(--radius-sm);
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
      text-decoration: none;
    }
    .inscribirse:hover {
      background-color: var(--accent-hi);
    }
    .sesiones {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-md);
    }
    .horario {
      display: block;
      color: var(--muted);
      font-size: 0.875rem;
    }
    .participantes {
      list-style: none;
      margin: var(--space-sm) 0 0;
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      font-size: 0.875rem;
    }
    .patrocinadores {
      list-style: none;
      margin: 0 0 var(--space-md);
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-lg);
    }
    .patrocinadores img {
      display: block;
      width: auto;
      object-fit: contain;
    }
    .patrocinadores.tamano-large img {
      height: 4.5rem;
    }
    .patrocinadores.tamano-medium img {
      height: 3rem;
    }
    .patrocinadores.tamano-small img {
      height: 2rem;
    }
    .patrocinadores a {
      display: inline-block;
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

  protected readonly evento = signal<PublicEventDetail | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);

  protected readonly dias = computed<DiaDeAgenda[]>(() => {
    const sesiones = this.evento()?.sessions ?? [];
    const grupos = new Map<string, PublicEventSession[]>();
    for (const sesion of sesiones) {
      const fecha = fechaLocal(sesion.starts_at);
      const lista = grupos.get(fecha) ?? [];
      lista.push(sesion);
      grupos.set(fecha, lista);
    }
    return [...grupos.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([fecha, sesiones]) => ({ fecha, sesiones }));
  });

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PublicEventDetail>(`public-event:${this.slug()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
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
