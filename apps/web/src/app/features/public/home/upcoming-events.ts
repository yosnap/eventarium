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
import { TranslocoDirective } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { Reveal } from '../../../shared/ui/reveal.directive';

interface ResumenDeEvento {
  readonly slug: string;
  readonly title: string;
  readonly summary: string | null;
  readonly starts_at: string;
}

const CLAVE = makeStateKey<ResumenDeEvento[]>('home-upcoming-events');

/**
 * Rejilla de próximos eventos en la portada, sobre `.screens`/`.sc` de la
 * referencia (`index.html:18-26,76-137`). La referencia enlaza ahí a las
 * otras pantallas del PROTOTIPO (nueve maquetas); aquí no hay ningún
 * equivalente real que enlazar, así que la rejilla pasa a mostrar los
 * eventos publicados de verdad — mismo endpoint que `events-list-page.ts`,
 * mismo criterio de "no pintar lo que la API no devuelve" (decisión del
 * usuario, no una lectura literal de la referencia).
 *
 * Se muestra solo si hay al menos un evento: una organización sin eventos
 * todavía no gana una sección vacía con un título sin contenido debajo.
 */
@Component({
  selector: 'app-upcoming-events',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Reveal],
  template: `
    <ng-container *transloco="let t">
      @if (eventos().length > 0) {
        <section class="proximos" appReveal>
          <div class="ancho-maximo proximos-en">
            <p class="rotulo-seccion">{{ t('publico.eventos.proximosRotulo') }}</p>
            <h2>{{ t('publico.eventos.proximosTitulo') }}</h2>
            <div class="rejilla">
              @for (evento of eventos(); track evento.slug; let indice = $index) {
                <a
                  class="tarjeta"
                  [routerLink]="['/eventos', evento.slug]"
                  appReveal
                  [index]="indice"
                >
                  <span class="fecha">{{ evento.starts_at | date: 'longDate' }}</span>
                  <h3>{{ evento.title }}</h3>
                  @if (evento.summary) {
                    <p>{{ evento.summary }}</p>
                  }
                  <span class="ir">{{ t('publico.eventos.verEvento') }} →</span>
                </a>
              }
            </div>
          </div>
        </section>
      }
    </ng-container>
  `,
  styles: `
    .proximos-en {
      padding: var(--space-xl) 0;
    }
    h2 {
      margin: 6px 0 0;
    }
    .rejilla {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(17.5rem, 1fr));
      gap: var(--space-md);
      margin-top: var(--space-lg);
    }
    /* .sc (eventarium.css, index.html:19-26): tarjeta completa como enlace,
       con salida "Abrir →" fijada al pie mediante margin-top:auto. */
    .tarjeta {
      display: flex;
      flex-direction: column;
      gap: var(--space-sm);
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
    .tarjeta:hover {
      border-color: var(--faint);
      background-color: var(--surface-hi);
    }
    .fecha {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--accent);
    }
    .tarjeta h3 {
      margin: 0;
    }
    .tarjeta p {
      margin: 0;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .ir {
      margin-top: auto;
      padding-top: var(--space-sm);
      border-top: 1px solid var(--border);
      font-size: var(--fs-sm);
    }
  `,
})
export class UpcomingEvents implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);

  protected readonly eventos = signal<ResumenDeEvento[]>([]);

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const transferido = this.transferState.get(CLAVE, null);
    if (transferido) {
      this.transferState.remove(CLAVE);
      this.eventos.set(transferido);
      return;
    }

    try {
      const eventos = await firstValueFrom(
        this.http.get<ResumenDeEvento[]>(this.api.url('/public/events'), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.eventos.set(eventos);
      if (this.api.isServer) {
        this.transferState.set(CLAVE, eventos);
      }
    } catch {
      // Silencioso a propósito: la portada no depende de esta sección para ser
      // útil, y ya existe el listado completo en /eventos con su propio
      // manejo de error visible si de verdad falla la API.
    }
  }
}
