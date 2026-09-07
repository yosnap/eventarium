import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  inject,
  makeStateKey,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

interface PublicEventSummary {
  readonly slug: string;
  readonly title: string;
  readonly summary: string | null;
  readonly cover_url: string | null;
  readonly starts_at: string;
  readonly location_name: string | null;
}

const CLAVE = makeStateKey<PublicEventSummary[]>('public-events-list');

/**
 * Listado público de eventos publicados de la organización. Página fija de esta
 * fase, sin integrarse en el sistema de bloques del branding: ese sistema no
 * existe todavía (`organization_branding` solo tiene plantilla, colores,
 * tipografías y redes sociales).
 */
@Component({
  selector: 'app-events-list-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('publico.eventos.listadoTitulo') }}</h1>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (eventos().length === 0) {
        <p>{{ t('publico.eventos.sinEventos') }}</p>
      } @else {
        <ul class="eventos">
          @for (evento of eventos(); track evento.slug) {
            <li>
              <app-card>
                <a [routerLink]="['/eventos', evento.slug]">
                  @if (evento.cover_url) {
                    <img [src]="evento.cover_url" [alt]="evento.title" />
                  }
                  <h2>{{ evento.title }}</h2>
                </a>
                <p class="fecha">
                  {{ evento.starts_at | date: 'fullDate' }}
                  @if (evento.location_name) {
                    · {{ evento.location_name }}
                  }
                </p>
                @if (evento.summary) {
                  <p>{{ evento.summary }}</p>
                }
              </app-card>
            </li>
          }
        </ul>
      }
    </ng-container>
  `,
  styles: `
    .eventos {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-lg);
      grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
    }
    .eventos img {
      width: 100%;
      max-height: 160px;
      object-fit: cover;
      border-radius: var(--radius-md);
    }
    .eventos a {
      color: inherit;
      text-decoration: none;
    }
    .eventos h2 {
      margin: var(--space-sm) 0 0;
      font-size: 1.125rem;
    }
    .fecha {
      color: var(--color-text-muted, #6b7280);
      font-size: 0.875rem;
    }
  `,
})
export class EventsListPage implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly transloco = inject(TranslocoService);

  protected readonly eventos = signal<PublicEventSummary[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    this.seo.set({ title: this.transloco.translate('publico.eventos.listadoTitulo') });

    const transferido = this.transferState.get(CLAVE, null);
    if (transferido) {
      this.transferState.remove(CLAVE);
      this.eventos.set(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const eventos = await firstValueFrom(
        this.http.get<PublicEventSummary[]>(this.api.url('/public/events'), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.eventos.set(eventos);
      if (this.api.isServer) {
        this.transferState.set(CLAVE, eventos);
      }
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('publico.eventos.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }
}
