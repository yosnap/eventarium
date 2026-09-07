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
import { Alert } from '../../../shared/ui/alert';
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

/**
 * Página pública de una sesión (ponencia): detalle, ponentes, materiales y
 * vídeo embebido según su plataforma. Mismo patrón de carga que `EventPage`.
 */
@Component({
  selector: 'app-session-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <app-alert tone="error">{{ t('publico.eventos.noEncontrado') }}</app-alert>
      } @else if (sesion(); as sesion) {
        <article>
          <a [routerLink]="['/eventos', sesion.event_slug]">{{ sesion.event_title }}</a>
          <h1>{{ sesion.title }}</h1>
          <p class="horario">
            {{ sesion.starts_at | date: 'fullDate' }} · {{ sesion.starts_at | date: 'shortTime' }} –
            {{ sesion.ends_at | date: 'shortTime' }}
            @if (sesion.room) {
              · {{ sesion.room }}
            }
          </p>

          @if (sesion.participants.length > 0) {
            <h2>{{ t('publico.eventos.ponentes') }}</h2>
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

          @if (sesion.description) {
            <p class="descripcion">{{ sesion.description }}</p>
          }

          @if (embed(); as video) {
            <h2>{{ t('publico.eventos.video') }}</h2>
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
          }

          @if (sesion.materials.length > 0) {
            <h2>{{ t('publico.eventos.materiales') }}</h2>
            <ul class="materiales">
              @for (material of sesion.materials; track $index) {
                @if (material.url) {
                  <li>
                    <a [href]="material.url" rel="noopener noreferrer" target="_blank">
                      {{ material.label || material.url }}
                    </a>
                  </li>
                }
              }
            </ul>
          }
        </article>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin: var(--space-md) 0 0;
    }
    .horario {
      color: var(--color-text-muted, #6b7280);
    }
    .participantes,
    .materiales {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-xs);
    }
    .video {
      width: 100%;
      aspect-ratio: 16 / 9;
      border: none;
      border-radius: var(--radius-md);
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

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PublicSessionDetail>(
      `public-session:${this.slug()}:${this.sessionId()}`,
    );
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
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
