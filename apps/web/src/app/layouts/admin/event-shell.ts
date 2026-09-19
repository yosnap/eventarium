import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { enlacesDeEvento } from './admin-nav';
import { EventScope } from './event-scope';

/**
 * Envoltorio de todas las pantallas de un evento (`events/:eventId/**`):
 * flecha de vuelta a la lista, título con el nombre del evento y las
 * secciones como pestañas horizontales — Resumen, Editar datos, Agenda,
 * Diseño, Patrocinadores, Ponentes, Inscripciones, Check-in, Contabilidad
 * (más Entradas/Descuentos/Pagos si el evento acepta pagos).
 *
 * Antes cada sección tenía su propia entrada en el menú lateral, mezclada
 * con la navegación de organización — confuso, y "editar datos" no se
 * distinguía de las demás porque no llevaba el mismo indicador de activo.
 * Las pestañas viven arriba, en el ámbito del evento, y `AdminNav` vuelve a
 * limitarse a los dos grupos estables (organización/plataforma).
 *
 * `enlacesDeEvento()` (en `admin-nav.ts`) sigue siendo la única fuente de
 * las etiquetas y la condición de pago: aquí solo se añaden Resumen y
 * Editar datos, que no son «una pestaña más» sino la entrada al ámbito.
 */
@Component({
  selector: 'app-event-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <div class="cabecera-evento">
        <a
          routerLink="/dashboard/events"
          class="volver"
          [attr.aria-label]="t('admin.nav.volverAEventosAria')"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path d="M15 18l-6-6 6-6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </a>
        <h1>
          {{
            t('admin.nav.editandoEvento', {
              nombre: eventScope.nombreEvento() ?? t('admin.nav.eventoCargando'),
            })
          }}
        </h1>
      </div>

      <nav class="pestanas" [attr.aria-label]="t('admin.nav.pestanasDeEvento')">
        <a
          [routerLink]="['/dashboard/events', eventId()]"
          routerLinkActive="activa"
          [routerLinkActiveOptions]="{ exact: true }"
        >
          {{ t('admin.nav.resumenEvento') }}
        </a>
        <a [routerLink]="['/dashboard/events', eventId(), 'editar']" routerLinkActive="activa">
          {{ t('admin.nav.editarEvento') }}
        </a>
        @for (enlace of enlaces(); track enlace.path.join('/')) {
          <a [routerLink]="enlace.path" routerLinkActive="activa">{{ t(enlace.labelKey) }}</a>
        }
      </nav>

      <router-outlet />
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    :host > * + * {
      margin-top: var(--space-lg);
    }
    .cabecera-evento {
      display: flex;
      align-items: center;
      gap: var(--space-md);
    }
    .volver {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 2.5rem;
      height: 2.5rem;
      border-radius: var(--radius-sm);
      color: var(--muted);
      flex-shrink: 0;
    }
    .volver:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
    .volver svg {
      width: 1.25rem;
      height: 1.25rem;
    }
    h1 {
      margin: 0;
      font-size: 1.25rem;
    }
    /* Tira de pestañas horizontal: activa = borde inferior + color de acento,
     * nunca la barra lateral que ya se retiró del menú de organización. */
    .pestanas {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs);
      border-bottom: 1px solid var(--border);
    }
    .pestanas a {
      padding: var(--space-sm) var(--space-md);
      border-bottom: 2px solid transparent;
      color: var(--muted);
      font-size: var(--fs-sm);
      font-weight: 500;
      text-decoration: none;
      white-space: nowrap;
    }
    .pestanas a:hover {
      color: var(--fg);
    }
    .pestanas a.activa {
      border-bottom-color: var(--accent);
      color: var(--fg);
    }
  `,
})
export class EventShell {
  readonly eventId = input.required<string>();

  protected readonly eventScope = inject(EventScope);

  protected readonly enlaces = computed(() =>
    enlacesDeEvento(this.eventId(), this.eventScope.registrationMode() === 'paid'),
  );
}
