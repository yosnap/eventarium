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

interface SocialLink {
  readonly kind: string;
  readonly url: string;
}

interface HistoryItem {
  readonly event_slug: string;
  readonly event_title: string;
  readonly session_id: string;
  readonly session_title: string;
  readonly starts_at: string;
  readonly role_key: string;
}

interface PublicSpeakerProfile {
  readonly display_name: string;
  readonly public_slug: string;
  readonly fields: Record<string, string>;
  readonly social_links: readonly SocialLink[];
  readonly history: readonly HistoryItem[];
}

interface EventoConSesiones {
  readonly slug: string;
  readonly title: string;
  readonly sesiones: readonly HistoryItem[];
}

const CAMPOS_A_ETIQUETA: Record<string, string> = {
  bio: 'publico.ponentes.bio',
  titular: 'publico.ponentes.titular',
  empresa: 'publico.ponentes.empresa',
  curriculum: 'publico.ponentes.curriculum',
  web: 'publico.ponentes.web',
  contacto: 'publico.ponentes.contacto',
};

/**
 * Página pública de un ponente: la lista blanca de campos de la fase 3 (nunca
 * `profile_data` completo), redes sociales y el historial de sesiones agrupado
 * por evento con enlace a cada uno.
 */
@Component({
  selector: 'app-speaker-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (noEncontrado()) {
        <app-alert tone="error">{{ t('publico.ponentes.noEncontrado') }}</app-alert>
      } @else if (perfil(); as perfil) {
        <article>
          <h1>{{ perfil.display_name }}</h1>

          @for (clave of camposOrdenados; track clave) {
            @if (perfil.fields[clave]; as valor) {
              <section>
                <h2>{{ t(etiquetaDe(clave)) }}</h2>
                <p>{{ valor }}</p>
              </section>
            }
          }

          @if (perfil.social_links.length > 0) {
            <nav [attr.aria-label]="t('publico.ponentes.redes')">
              <ul class="redes">
                @for (enlace of perfil.social_links; track enlace.kind) {
                  <li>
                    <a [href]="enlace.url" rel="noopener noreferrer" target="_blank">
                      {{ enlace.kind }}
                    </a>
                  </li>
                }
              </ul>
            </nav>
          }

          @if (eventos().length > 0) {
            <h2>{{ t('publico.ponentes.historial') }}</h2>
            @for (evento of eventos(); track evento.slug) {
              <h3>
                <a [routerLink]="['/eventos', evento.slug]">{{ evento.title }}</a>
              </h3>
              <ul class="sesiones">
                @for (sesion of evento.sesiones; track sesion.session_id) {
                  <li>
                    <a [routerLink]="['/eventos', evento.slug, 'sesiones', sesion.session_id]">
                      {{ sesion.session_title }}
                    </a>
                    <span class="rol">
                      ({{ sesion.role_key }}, {{ sesion.starts_at | date: 'mediumDate' }})
                    </span>
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
    h1 {
      margin: var(--space-md) 0;
    }
    section {
      margin-bottom: var(--space-md);
    }
    section h2 {
      font-size: 1rem;
      margin-bottom: var(--space-xs);
    }
    .redes,
    .sesiones {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-xs);
    }
    .redes {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-md);
    }
    .rol {
      color: var(--color-text-muted, #6b7280);
      font-size: 0.875rem;
    }
  `,
})
export class SpeakerPage implements OnInit {
  readonly publicSlug = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly notFound = inject(NotFoundStatusService);
  private readonly transloco = inject(TranslocoService);

  protected readonly camposOrdenados = Object.keys(CAMPOS_A_ETIQUETA);

  protected readonly perfil = signal<PublicSpeakerProfile | null>(null);
  protected readonly cargando = signal(true);
  protected readonly noEncontrado = signal(false);

  protected readonly eventos = computed<EventoConSesiones[]>(() => {
    const historial = this.perfil()?.history ?? [];
    const porEvento = new Map<string, EventoConSesiones>();
    for (const item of historial) {
      const existente = porEvento.get(item.event_slug);
      if (existente) {
        (existente.sesiones as HistoryItem[]).push(item);
      } else {
        porEvento.set(item.event_slug, {
          slug: item.event_slug,
          title: item.event_title,
          sesiones: [item],
        });
      }
    }
    return [...porEvento.values()].sort((a, b) => a.title.localeCompare(b.title));
  });

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  protected etiquetaDe(clave: string): string {
    return CAMPOS_A_ETIQUETA[clave] ?? clave;
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<PublicSpeakerProfile>(`public-speaker:${this.publicSlug()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      return;
    }

    try {
      const perfil = await firstValueFrom(
        this.http.get<PublicSpeakerProfile>(this.api.url(`/public/speakers/${this.publicSlug()}`), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.aplicar(perfil);
      if (this.api.isServer) {
        this.transferState.set(clave, perfil);
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

  private aplicar(perfil: PublicSpeakerProfile): void {
    this.perfil.set(perfil);
    this.seo.set({
      title: perfil.display_name,
      description: perfil.fields['bio'] ?? this.transloco.translate('publico.eventos.sinResumen'),
    });
  }
}
