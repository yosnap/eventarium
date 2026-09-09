import 'fake-indexeddb/auto';

import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
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
        useValue: {
          branding: signal(null),
          error: signal(null),
          templateKey: signal('classic'),
          organizationName: signal('Organización de prueba'),
        },
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
  ['/admin', 'app-dashboard-page'],
  ['/admin/organization', 'app-organization-page'],
  ['/admin/branding', 'app-branding-page'],
  ['/admin/roles', 'app-roles-page'],
  ['/admin/roles/r1', 'app-role-form'],
  ['/admin/members', 'app-members-page'],
  ['/admin/members/nuevo', 'app-member-form'],
  ['/admin/events', 'app-events-page'],
  ['/admin/events/nuevo', 'app-event-form'],
  ['/admin/events/e1', 'app-event-form'],
  ['/admin/events/e1/registrations/reg1', 'app-registration-detail-page'],
  ['/admin/events/e1/check-in', 'app-event-check-in'],
  ['/admin/events/e1/payments', 'app-event-payments'],
  ['/admin/sponsor-tiers', 'app-sponsor-tiers-page'],
  ['/admin/stripe', 'app-stripe-connection'],
  ['/admin/legal', 'app-legal-pages-page'],
  ['/admin/account', 'app-account-page'],
  ['/admin/estilo', 'app-style-guide-page'],
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

describe('rutas de superadministración: guard, no solo visibilidad', () => {
  it('/admin/superadmin sigue protegida por superadminGuard', async () => {
    configurar({ is_superadmin: true });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/superadmin');

    expect(harness.routeNativeElement?.querySelector('app-superadmin-page')).not.toBeNull();
  });

  it('/admin/superadmin/plantillas sigue protegida por superadminGuard', async () => {
    configurar({ is_superadmin: true });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/superadmin/plantillas');

    expect(harness.routeNativeElement?.querySelector('app-theme-templates-page')).not.toBeNull();
  });

  it('un autenticado sin is_superadmin no alcanza /admin/superadmin', async () => {
    configurar({ is_superadmin: false });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/superadmin');

    expect(harness.routeNativeElement?.querySelector('app-superadmin-page')).toBeNull();
  });

  it('un autenticado sin is_superadmin no alcanza /admin/superadmin/plantillas', async () => {
    configurar({ is_superadmin: false });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/superadmin/plantillas');

    expect(harness.routeNativeElement?.querySelector('app-theme-templates-page')).toBeNull();
  });

  it('el mismo usuario sin is_superadmin sí alcanza /admin/estilo', async () => {
    configurar({ is_superadmin: false });
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/admin/estilo');

    expect(harness.routeNativeElement?.querySelector('app-style-guide-page')).not.toBeNull();
  });
});

describe('rutas de sección nuevas: entregan eventId al componente, no solo resuelven', () => {
  beforeEach(() => configurar({ is_superadmin: false }));

  const CASOS: readonly [string, string, new (...args: never[]) => { eventId: () => string }][] = [
    ['/admin/events/e1/agenda', 'app-event-agenda', EventAgenda],
    ['/admin/events/e1/entradas', 'app-event-ticket-types', EventTicketTypes],
    ['/admin/events/e1/descuentos', 'app-event-discount-codes', EventDiscountCodes],
    ['/admin/events/e1/patrocinadores', 'app-event-sponsors', EventSponsors],
    ['/admin/events/e1/inscripciones', 'app-event-registrations', EventRegistrations],
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
