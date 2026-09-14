import 'fake-indexeddb/auto';

import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter, withComponentInputBinding, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { routes } from './app.routes';
import { AuthService } from './core/auth/auth.service';
import { ThemingService } from './core/theming/theming.service';
import { EventAgenda } from './features/admin/events/event-agenda';
import { EventDiscountCodes } from './features/admin/events/event-discount-codes';
import { EventRegistrations } from './features/admin/events/event-registrations';
import { EventSponsors } from './features/admin/events/event-sponsors';
import { EventTicketTypes } from './features/admin/events/event-ticket-types';
import es from '../../public/assets/i18n/es-ES.json';
import { themingDePrueba } from '../testing/theming.fixture';

/**
 * Recorre las rutas de `app.routes.ts` de verdad, sin espiar el router: cada caso
 * navega con `RouterTestingHarness` y busca en el DOM resultante el selector del
 * componente esperado. Una regresión de nombre de parámetro o de ruta duplicada
 * rompería esta comprobación aunque el router "resuelva algo" — que es justo el
 * fallo silencioso que preocupa a esta fase.
 */
function configurar(usuario: { is_superadmin: boolean } | null) {
  TestBed.configureTestingModule({
    imports: [
      TranslocoTestingModule.forRoot({
        langs: { 'es-ES': es },
        translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
      }),
    ],
    providers: [
      provideZonelessChangeDetection(),
      provideRouter(routes, withComponentInputBinding()),
      provideHttpClient(),
      provideHttpClientTesting(),
      {
        provide: ThemingService,
        useValue: themingDePrueba(),
      },
      {
        provide: AuthService,
        useValue: {
          isAuthenticated: signal(true),
          currentUser: signal(
            usuario
              ? {
                  id: '1',
                  email: 'persona@example.com',
                  first_name: null,
                  last_name: null,
                  is_superadmin: usuario.is_superadmin,
                }
              : null,
          ),
          refresh: async () => true,
          loadCurrentUser: async () => {
            throw new Error('no debería necesitarse: currentUser ya está resuelto');
          },
          listMyOrganizations: async () => [],
          logout: vi.fn(),
        },
      },
    ],
  });
}

/** Las 20 rutas que ya existían antes de esta fase (19 previas + la de plantillas de
 * tema, que añadió la fase 1), con el selector del componente al que deben seguir
 * resolviendo. */
const RUTAS_EXISTENTES: readonly [string, string][] = [
  ['/dashboard', 'app-dashboard-page'],
  ['/dashboard/organization', 'app-organization-page'],
  ['/dashboard/branding', 'app-branding-page'],
  ['/dashboard/roles', 'app-roles-page'],
  ['/dashboard/roles/r1', 'app-role-form'],
  ['/dashboard/members', 'app-members-page'],
  ['/dashboard/members/nuevo', 'app-member-form'],
  ['/dashboard/events', 'app-events-page'],
  ['/dashboard/events/nuevo', 'app-event-form'],
  // La raíz del evento es su escritorio (cómo va); el formulario vive en
  // `/editar`, porque a quien entra a un evento le interesa el estado antes que
  // los campos.
  ['/dashboard/events/e1', 'app-event-dashboard'],
  ['/dashboard/events/e1/editar', 'app-event-form'],
  ['/dashboard/events/e1/registrations/reg1', 'app-registration-detail-page'],
  ['/dashboard/events/e1/check-in', 'app-event-check-in'],
  ['/dashboard/events/e1/payments', 'app-event-payments'],
  ['/dashboard/sponsor-tiers', 'app-sponsor-tiers-page'],
  ['/dashboard/stripe', 'app-stripe-connection'],
  ['/dashboard/account', 'app-account-page'],
];

describe('rutas existentes: siguen resolviendo al mismo componente', () => {
  beforeEach(() => configurar({ is_superadmin: false }));

  for (const [url, selector] of RUTAS_EXISTENTES) {
    it(`${url} → ${selector}`, async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl(url);

      expect(harness.routeNativeElement?.querySelector(selector)).not.toBeNull();
    });
  }
});

describe('rutas de plataforma: guard, no solo visibilidad', () => {
  it('/admin está protegida por superadminGuard', async () => {
    configurar({ is_superadmin: true });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin');

    expect(harness.routeNativeElement?.querySelector('app-superadmin-page')).not.toBeNull();
  });

  it('/admin/plantillas está protegida por superadminGuard', async () => {
    configurar({ is_superadmin: true });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/plantillas');

    expect(harness.routeNativeElement?.querySelector('app-theme-templates-page')).not.toBeNull();
  });

  it('un autenticado sin is_superadmin no alcanza /admin', async () => {
    configurar({ is_superadmin: false });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin');

    expect(harness.routeNativeElement?.querySelector('app-superadmin-page')).toBeNull();
  });

  it('un autenticado sin is_superadmin no alcanza /admin/plantillas', async () => {
    configurar({ is_superadmin: false });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/plantillas');

    expect(harness.routeNativeElement?.querySelector('app-theme-templates-page')).toBeNull();
  });

  it('/admin/estilo está protegida por superadminGuard', async () => {
    configurar({ is_superadmin: true });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/estilo');

    expect(harness.routeNativeElement?.querySelector('app-style-guide-page')).not.toBeNull();
  });

  it('un autenticado sin is_superadmin no alcanza /admin/estilo', async () => {
    configurar({ is_superadmin: false });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/estilo');

    expect(harness.routeNativeElement?.querySelector('app-style-guide-page')).toBeNull();
  });
});

describe('rutas de sección nuevas: entregan eventId al componente, no solo resuelven', () => {
  beforeEach(() => configurar({ is_superadmin: false }));

  const CASOS: readonly [string, string, new (...args: never[]) => { eventId: () => string }][] = [
    ['/dashboard/events/e1/agenda', 'app-event-agenda', EventAgenda],
    ['/dashboard/events/e1/entradas', 'app-event-ticket-types', EventTicketTypes],
    ['/dashboard/events/e1/descuentos', 'app-event-discount-codes', EventDiscountCodes],
    ['/dashboard/events/e1/patrocinadores', 'app-event-sponsors', EventSponsors],
    ['/dashboard/events/e1/inscripciones', 'app-event-registrations', EventRegistrations],
  ];

  for (const [url, selector, tipo] of CASOS) {
    it(`${url} → ${selector} con eventId = 'e1'`, async () => {
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl(url);

      expect(harness.routeNativeElement?.querySelector(selector)).not.toBeNull();
      const instancia = harness.fixture.debugElement.query(By.directive(tipo))?.componentInstance;
      expect(instancia).toBeTruthy();
      expect(instancia.eventId()).toBe('e1');
    });
  }
});

describe('redirecciones de las rutas antiguas del panel', () => {
  beforeEach(() => configurar({ is_superadmin: true }));

  // Las rutas del panel vivían todas bajo `/admin`, sin distinguir ámbito. Al
  // separar los dos paneles (organización en `/dashboard`, plataforma en
  // `/admin`), los enlaces guardados y los marcadores tienen que seguir
  // llegando a su sitio. Estas pruebas fijan el destino de cada una, porque el
  // orden y la forma de las redirecciones son justo lo que se rompe en silencio:
  // un comodín de más capturaría las rutas nuevas de plataforma.
  const CASOS: readonly [string, string][] = [
    // `/acceder` en sí redirige a quien ya tiene sesión (`guestGuard`), así que el
    // destino final de un marcador antiguo a `/admin/login` es el panel, no el
    // formulario.
    ['/admin/login', '/dashboard'],
    ['/admin/superadmin', '/admin'],
    ['/admin/superadmin/plantillas', '/admin/plantillas'],
    ['/admin/superadmin/identidad', '/admin/identidad'],
    ['/admin/superadmin/legales', '/admin/legales'],
    ['/admin/superadmin/suplantar', '/admin/suplantar'],
    ['/admin/organization', '/dashboard/organization'],
    ['/admin/branding', '/dashboard/branding'],
    ['/admin/roles', '/dashboard/roles'],
    ['/admin/roles/r1', '/dashboard/roles/r1'],
    ['/admin/members', '/dashboard/members'],
    ['/admin/members/nuevo', '/dashboard/members/nuevo'],
    ['/admin/events', '/dashboard/events'],
    ['/admin/events/e1', '/dashboard/events/e1'],
    ['/admin/events/e1/inscripciones', '/dashboard/events/e1/inscripciones'],
    ['/admin/events/e1/registrations/reg1', '/dashboard/events/e1/registrations/reg1'],
    ['/admin/stripe', '/dashboard/stripe'],
    // Sin destino propio: la pantalla de páginas legales de organización se
    // retiró (son siempre las de plataforma), así que un marcador antiguo a
    // cualquiera de sus dos nombres vuelve al escritorio.
    ['/admin/legal', '/dashboard'],
    ['/dashboard/legal', '/dashboard'],
    // Sentido contrario a las de arriba: el catálogo de componentes vivió una
    // temporada en `/dashboard/estilo` antes de volver a `/admin`.
    ['/dashboard/estilo', '/admin/estilo'],
  ];

  for (const [origen, destino] of CASOS) {
    it(`${origen} → ${destino}`, async () => {
      const router = TestBed.inject(Router);
      await router.navigateByUrl(origen);
      expect(router.url).toBe(destino);
    });
  }

  it('las rutas nuevas de plataforma NO las captura la redirección del organizador', async () => {
    // El fallo que esto previene: con un `admin/:a` genérico, `/admin/plantillas`
    // acabaría en `/dashboard/plantillas` y el panel de plataforma sería
    // inalcanzable por URL.
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/plantillas');
    expect(router.url).toBe('/admin/plantillas');
  });
});
