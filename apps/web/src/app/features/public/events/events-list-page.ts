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
 *
 * Fila `.ev` sobre la referencia (`descubrir-eventos.html:32-40`): tarjeta
 * completa como enlace único, bloque de fecha (día + mes en mono), título y
 * metadatos. La referencia también trae buscador y filtros por etiqueta
 * (`.searchbar`/`.tags`) — **fuera de alcance**: el *Non-goal* del plan excluye
 * explícitamente el buscador facetado que `events-list-page.ts` no tiene hoy.
 * No se muestra `cover_url` en la fila: la referencia no lleva imagen en este
 * patrón de lista (sí la lleva la ficha del evento).
 */
@Component({
  selector: 'app-events-list-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Alert],
  template: `
    <ng-container *transloco="let t">
      <div class="ancho-maximo">
        <h1>{{ t('publico.eventos.listadoTitulo') }}</h1>

        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (eventos().length === 0) {
          <p class="vacio">{{ t('publico.eventos.sinEventos') }}</p>
        } @else {
          <div class="lista">
            @for (evento of eventos(); track evento.slug) {
              <a class="ev" [routerLink]="['/eventos', evento.slug]">
                <span class="ev-fecha">
                  <span class="ev-dia">{{ evento.starts_at | date: 'dd' }}</span>
                  <span class="ev-mes">{{ evento.starts_at | date: 'MMM' }}</span>
                </span>
                <span class="ev-cuerpo">
                  <h3>{{ evento.title }}</h3>
                  <span class="ev-meta">
                    @if (evento.location_name) {
                      <span>{{ evento.location_name }}</span>
                    }
                    @if (evento.summary) {
                      <span>{{ evento.summary }}</span>
                    }
                  </span>
                </span>
              </a>
            }
          </div>
        }
      </div>
    </ng-container>
  `,
  styles: `
    .ancho-maximo {
      padding: var(--space-lg) 0;
    }
    .vacio {
      color: var(--muted);
    }
    .lista {
      display: grid;
      gap: var(--space-md);
    }
    /* .ev (eventarium.css:32-35): la fila entera es el enlace. */
    .ev {
      display: grid;
      grid-template-columns: 104px minmax(0, 1fr);
      align-items: center;
      gap: var(--space-lg);
      padding: var(--space-lg);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      text-decoration: none;
      color: inherit;
      transition:
        border-color 0.15s,
        background-color 0.15s;
    }
    .ev:hover {
      border-color: var(--faint);
      background-color: var(--surface-hi);
    }
    /* .ev__date (eventarium.css:36-39). */
    .ev-fecha {
      display: grid;
      justify-items: center;
      padding: 12px 8px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      text-align: center;
    }
    .ev-dia {
      font-family: var(--font-display);
      font-size: 2.1rem;
      line-height: 0.95;
      text-transform: uppercase;
    }
    .ev-mes {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .ev-cuerpo h3 {
      margin: 0;
    }
    .ev-meta {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-md);
      margin-top: 8px;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    @media (max-width: 47.5rem) {
      .ev {
        grid-template-columns: 74px minmax(0, 1fr);
        gap: var(--space-md);
      }
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
