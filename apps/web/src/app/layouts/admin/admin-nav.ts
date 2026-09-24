import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthService } from '../../core/auth/auth.service';

/**
 * Un enlace de navegación del panel.
 */
export interface AdminNavLink {
  readonly path: readonly string[];
  readonly labelKey: string;
  readonly exact?: boolean;
  readonly soloSuperadmin?: boolean;
}

export const ORGANIZATION_NAV_LINKS: readonly AdminNavLink[] = [
  { path: ['/dashboard'], labelKey: 'admin.escritorio', exact: true },
  { path: ['/dashboard/organization'], labelKey: 'admin.organizacion.titulo' },
  { path: ['/dashboard/branding'], labelKey: 'admin.identidadVisual' },
  { path: ['/dashboard/politicas'], labelKey: 'admin.politicas.nav' },
  { path: ['/dashboard/roles'], labelKey: 'admin.rolesNav' },
  { path: ['/dashboard/members'], labelKey: 'admin.miembrosNav' },
  { path: ['/dashboard/events'], labelKey: 'admin.eventsNav' },
  { path: ['/dashboard/sponsor-tiers'], labelKey: 'admin.sponsorTiersNav' },
  { path: ['/dashboard/stripe'], labelKey: 'admin.stripeNav' },
  // Sin `soloSuperadmin`: es una pantalla del panel de organización, y quien no
  // sea propietario ve el aviso de solo lectura que devuelve el backend.
  { path: ['/dashboard/ia'], labelKey: 'admin.ia.organizacion.titulo' },
  { path: ['/dashboard/mcp'], labelKey: 'admin.mcp.nav' },
];

export const PLATFORM_NAV_LINKS: readonly AdminNavLink[] = [
  { path: ['/admin'], labelKey: 'admin.superadminNav', exact: true, soloSuperadmin: true },
  {
    path: ['/admin/identidad'],
    labelKey: 'admin.plataforma.identidad.titulo',
    soloSuperadmin: true,
  },
  { path: ['/admin/legales'], labelKey: 'admin.plataforma.legales.titulo', soloSuperadmin: true },
  // Cookies y analítica externa: lectura para todo el personal de plataforma
  // (fase 3 del plan de cookies) — sin `soloSuperadmin`, visible también para
  // `soporte`. La etiqueta lleva la palabra «cookies»: la causa raíz que
  // motivó el plan fue buscar esa palabra en el menú y no encontrarla.
  {
    path: ['/admin/analitica-externa'],
    labelKey: 'admin.plataforma.analitica.titulo',
  },
  {
    path: ['/admin/plantillas'],
    labelKey: 'admin.superadmin.plantillas.titulo',
    soloSuperadmin: true,
  },
  // Suplantar y el directorio de usuarios aceptan también el rol de
  // plataforma `soporte` en el backend (`require_platform_staff`, plan
  // `260916-0810-usuarios-y-permisos-plataforma`): sin `soloSuperadmin`,
  // listos para cuando el guard del panel se abra a ese rol.
  // Credencial del proveedor de IA e interruptores de servicio: solo superadmin,
  // igual que el guard de sus rutas.
  { path: ['/admin/ia'], labelKey: 'admin.ia.plataforma.titulo', soloSuperadmin: true },
  { path: ['/admin/servicios'], labelKey: 'admin.ia.servicios.titulo', soloSuperadmin: true },
  { path: ['/admin/suplantar'], labelKey: 'admin.plataforma.impersonar.titulo' },
  { path: ['/admin/usuarios'], labelKey: 'admin.plataforma.usuarios.titulo' },
  // La caja de piezas con la que se construyen la landing y la presentación del
  // portal, y de la que salen las plantillas que luego usan las organizaciones
  // (mismo papel que cumple para Luma): trabajo de quien administra la
  // instalación, no de un organizador.
  { path: ['/admin/estilo'], labelKey: 'admin.catalogoDeComponentes', soloSuperadmin: true },
];

/**
 * Enlaces de las pestañas de un evento (`EventShell`), sin Resumen ni Editar
 * datos ni el enlace de vuelta a la lista — esos los pinta `EventShell`
 * aparte, porque no son «una pestaña más» sino la entrada y la salida del
 * ámbito.
 *
 * Las secciones de pago solo aparecen si `aceptaPagos`, con el mismo criterio que ya
 * aplicaba `event-form.ts` antes de esta fase: `registrationMode() === 'paid'`.
 */
export function enlacesDeEvento(eventId: string, aceptaPagos: boolean): readonly AdminNavLink[] {
  const enlaces: AdminNavLink[] = [
    { path: ['/dashboard/events', eventId, 'agenda'], labelKey: 'admin.events.agenda.titulo' },
    { path: ['/dashboard/events', eventId, 'diseno'], labelKey: 'admin.events.design.titulo' },
    {
      path: ['/dashboard/events', eventId, 'patrocinadores'],
      labelKey: 'admin.events.sponsors.titulo',
    },
  ];
  if (aceptaPagos) {
    enlaces.push(
      {
        path: ['/dashboard/events', eventId, 'entradas'],
        labelKey: 'admin.events.ticketTypes.titulo',
      },
      {
        path: ['/dashboard/events', eventId, 'descuentos'],
        labelKey: 'admin.events.discountCodes.titulo',
      },
    );
  }
  enlaces.push({
    path: ['/dashboard/events', eventId, 'ponentes'],
    labelKey: 'admin.events.speakers.rotulo',
  });
  enlaces.push({
    path: ['/dashboard/events', eventId, 'politicas'],
    labelKey: 'admin.politicas.nav',
  });
  enlaces.push({
    path: ['/dashboard/events', eventId, 'inscripciones'],
    labelKey: 'admin.events.registrations.titulo',
  });
  enlaces.push({
    path: ['/dashboard/events', eventId, 'check-in'],
    labelKey: 'admin.events.checkIn.titulo',
  });
  if (aceptaPagos) {
    enlaces.push({
      path: ['/dashboard/events', eventId, 'payments'],
      labelKey: 'admin.events.payments.titulo',
    });
  }
  enlaces.push({
    path: ['/dashboard/events', eventId, 'contabilidad'],
    labelKey: 'admin.events.accounting.titulo',
  });
  return enlaces;
}

/**
 * Navegación del panel, agrupada por ámbito y **acotada al panel en el que está**.
 *
 * Los dos paneles son árboles de ruta distintos —`/dashboard` (organización) y
 * `/admin` (plataforma)— y comparten este componente, así que la plantilla decide
 * qué grupo pinta. Ofrecer los enlaces del otro panel no solo sobra: manda a quien
 * navega a un árbol donde el guard lo va a rebotar.
 *
 * Cada grupo es un `<nav>` con `aria-labelledby` hacia su propio encabezado —
 * nunca un `<div>` con texto en negrita, que un lector de pantalla no anuncia como
 * agrupación.
 */
@Component({
  selector: 'app-admin-nav',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, RouterLinkActive, TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      @if (plataforma()) {
        <h2 id="admin-nav-plataforma-titulo" class="grupo-titulo">
          {{ t('admin.nav.grupoPlataforma') }}
        </h2>
        <nav [attr.aria-labelledby]="'admin-nav-plataforma-titulo'">
          <ul>
            @for (enlace of enlacesDePlataforma(); track enlace.path.join('/')) {
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
      } @else {
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
      }
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
      color: var(--muted);
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
    /* .side a del prototipo (panel-organizador.html:7-11): fs-sm, muted,
       hover con surface-hi; el activo es fondo tenue + barra inset de accent,
       no un bloque de acento completo. */
    a {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      min-height: 40px;
      padding: 0 12px;
      border-radius: var(--radius-sm);
      color: var(--muted);
      font-size: var(--fs-sm);
      text-decoration: none;
      transition:
        background-color 0.15s,
        color 0.15s;
    }
    a:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
    a.activo {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
  `,
})
export class AdminNav {
  private readonly auth = inject(AuthService);

  /** `true` cuando el panel pintado es el de la plataforma (`/admin`). */
  readonly plataforma = input<boolean>(false);

  protected readonly ORGANIZATION_NAV_LINKS = ORGANIZATION_NAV_LINKS;

  /** `PLATFORM_NAV_LINKS` sin los enlaces `soloSuperadmin` para quien no lo
   * es — hoy el guard del panel ya exige superadmin para entrar aquí
   * siquiera, así que en la práctica no filtra nada todavía; deja el panel
   * listo para el día en que se abra también a `soporte`. */
  protected readonly enlacesDePlataforma = computed(() => {
    const esSuperadmin = this.auth.currentUser()?.is_superadmin ?? false;
    return PLATFORM_NAV_LINKS.filter((enlace) => !enlace.soloSuperadmin || esSuperadmin);
  });
}
