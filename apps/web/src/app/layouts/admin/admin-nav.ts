import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

/**
 * Un enlace de navegación del panel.
 *
 * La visibilidad se declara por enlace, nunca por grupo: agrupar el catálogo de
 * componentes bajo «Plataforma» junto a superadministración no puede arrastrarle por
 * error la restricción de `is_superadmin`, que hoy no tiene (pregunta abierta 3 de
 * `plan.md`). Solo dos enlaces de esta fase la llevan: `/admin/superadmin` y
 * `/admin/superadmin/plantillas`.
 */
export interface AdminNavLink {
  readonly path: readonly string[];
  readonly labelKey: string;
  readonly exact?: boolean;
  readonly soloSuperadmin?: boolean;
}

/** Datos que necesita el grupo contextual de evento para pintarse. */
export interface AdminNavEvento {
  readonly id: string;
  readonly nombre: string | null;
  readonly cargando: boolean;
  readonly aceptaPagos: boolean;
}

export const ORGANIZATION_NAV_LINKS: readonly AdminNavLink[] = [
  { path: ['/admin'], labelKey: 'admin.escritorio', exact: true },
  { path: ['/admin/organization'], labelKey: 'admin.organizacion.titulo' },
  { path: ['/admin/branding'], labelKey: 'admin.identidadVisual' },
  { path: ['/admin/roles'], labelKey: 'admin.rolesNav' },
  { path: ['/admin/members'], labelKey: 'admin.miembrosNav' },
  { path: ['/admin/events'], labelKey: 'admin.eventsNav' },
  { path: ['/admin/sponsor-tiers'], labelKey: 'admin.sponsorTiersNav' },
  { path: ['/admin/stripe'], labelKey: 'admin.stripeNav' },
  { path: ['/admin/legal'], labelKey: 'admin.legalNav' },
];

export const PLATFORM_NAV_LINKS: readonly AdminNavLink[] = [
  { path: ['/admin/superadmin'], labelKey: 'admin.superadminNav', soloSuperadmin: true },
  {
    path: ['/admin/superadmin/plantillas'],
    labelKey: 'admin.superadmin.plantillas.titulo',
    soloSuperadmin: true,
  },
  { path: ['/admin/estilo'], labelKey: 'admin.catalogoDeComponentes' },
];

/**
 * Enlaces del grupo contextual de evento, sin el enlace de detalles ni el de salida
 * (los pinta la plantilla aparte, porque no son «una entrada más» sino la entrada y la
 * salida del ámbito).
 *
 * Las secciones de pago solo aparecen si `aceptaPagos`, con el mismo criterio que ya
 * aplicaba `event-form.ts` antes de esta fase: `registrationMode() === 'paid'`.
 */
export function enlacesDeEvento(eventId: string, aceptaPagos: boolean): readonly AdminNavLink[] {
  const enlaces: AdminNavLink[] = [
    { path: ['/admin/events', eventId, 'agenda'], labelKey: 'admin.events.agenda.titulo' },
    {
      path: ['/admin/events', eventId, 'patrocinadores'],
      labelKey: 'admin.events.sponsors.titulo',
    },
  ];
  if (aceptaPagos) {
    enlaces.push(
      { path: ['/admin/events', eventId, 'entradas'], labelKey: 'admin.events.ticketTypes.titulo' },
      {
        path: ['/admin/events', eventId, 'descuentos'],
        labelKey: 'admin.events.discountCodes.titulo',
      },
    );
  }
  enlaces.push({
    path: ['/admin/events', eventId, 'inscripciones'],
    labelKey: 'admin.events.registrations.titulo',
  });
  enlaces.push({
    path: ['/admin/events', eventId, 'check-in'],
    labelKey: 'admin.events.checkIn.titulo',
  });
  if (aceptaPagos) {
    enlaces.push({
      path: ['/admin/events', eventId, 'payments'],
      labelKey: 'admin.events.payments.titulo',
    });
  }
  return enlaces;
}

/**
 * Navegación del panel agrupada por ámbito: Organización, Evento (contextual) y
 * Plataforma. Cada grupo es un `<nav>` con `aria-labelledby` hacia su propio
 * encabezado — nunca un `<div>` con texto en negrita, que un lector de pantalla no
 * anuncia como agrupación.
 */
@Component({
  selector: 'app-admin-nav',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouterLinkActive, TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <h2 id="admin-nav-organizacion-titulo" class="grupo-titulo">
        {{ t('admin.nav.grupoOrganizacion') }}
      </h2>
      <nav [attr.aria-labelledby]="'admin-nav-organizacion-titulo'">
        <ul>
          @for (enlace of ORGANIZATION_NAV_LINKS; track enlace.path.join('/')) {
            <li>
              <a
                [routerLink]="enlace.path"
                routerLinkActive="activo"
                [routerLinkActiveOptions]="{ exact: !!enlace.exact }"
              >
                {{ t(enlace.labelKey) }}
              </a>
            </li>
          }
        </ul>
      </nav>

      @if (evento(); as datosEvento) {
        <h2 id="admin-nav-evento-titulo" class="grupo-titulo">
          {{ datosEvento.nombre ?? t('admin.nav.eventoCargando') }}
        </h2>
        <nav [attr.aria-labelledby]="'admin-nav-evento-titulo'">
          <ul>
            <li>
              <a
                [routerLink]="['/admin/events', datosEvento.id]"
                routerLinkActive="activo"
                [routerLinkActiveOptions]="{ exact: true }"
              >
                {{ t('admin.nav.detallesEvento') }}
              </a>
            </li>
            @for (enlace of enlacesEvento(); track enlace.path.join('/')) {
              <li>
                <a [routerLink]="enlace.path" routerLinkActive="activo">
                  {{ t(enlace.labelKey) }}
                </a>
              </li>
            }
            <li>
              <a routerLink="/admin/events">{{ t('admin.nav.volverAEventos') }}</a>
            </li>
          </ul>
        </nav>
      }

      <h2 id="admin-nav-plataforma-titulo" class="grupo-titulo">
        {{ t('admin.nav.grupoPlataforma') }}
      </h2>
      <nav [attr.aria-labelledby]="'admin-nav-plataforma-titulo'">
        <ul>
          @for (enlace of plataforma(); track enlace.path.join('/')) {
            <li>
              <a [routerLink]="enlace.path" routerLinkActive="activo">
                {{ t(enlace.labelKey) }}
              </a>
            </li>
          }
        </ul>
      </nav>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .grupo-titulo {
      margin: var(--space-md) 0 var(--space-xs);
      padding: 0 var(--space-md);
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--color-text-muted, #6b7280);
    }
    .grupo-titulo:first-child {
      margin-top: 0;
    }
    nav {
      padding: 0 var(--space-md);
    }
    ul {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-xs);
    }
    a {
      display: block;
      padding: var(--space-sm) var(--space-md);
      border-radius: var(--radius-md);
      color: var(--color-text);
      text-decoration: none;
    }
    a.activo {
      background-color: var(--color-primary);
      color: var(--color-primary-contrast);
    }
  `,
})
export class AdminNav {
  /** Persona superadministradora: gobierna solo los enlaces con `soloSuperadmin`. */
  readonly isSuperadmin = input<boolean>(false);
  /** `null` cuando no hay evento activo o cuando su carga ha fallado: en ambos casos
   * el grupo desaparece y la navegación vuelve a los dos grupos estables. */
  readonly evento = input<AdminNavEvento | null>(null);

  protected readonly ORGANIZATION_NAV_LINKS = ORGANIZATION_NAV_LINKS;

  protected readonly plataforma = computed(() =>
    PLATFORM_NAV_LINKS.filter((enlace) => !enlace.soloSuperadmin || this.isSuperadmin()),
  );

  protected readonly enlacesEvento = computed(() => {
    const datosEvento = this.evento();
    return datosEvento ? enlacesDeEvento(datosEvento.id, datosEvento.aceptaPagos) : [];
  });
}
