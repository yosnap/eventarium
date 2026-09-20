import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { StripeConnection } from './stripe-connection';

const ME_URL = '/api/v1/organizations/me';
const ORG_ID = 'org-1';
const STRIPE_URL = `/api/v1/organizations/${ORG_ID}/stripe`;

function estadoNoConectado() {
  return {
    connected: false,
    charges_enabled: false,
    payouts_enabled: false,
    details_submitted: false,
    connected_at: null,
    deauthorized_at: null,
    last_synced_at: null,
  };
}

function estadoOperativo() {
  return {
    connected: true,
    charges_enabled: true,
    payouts_enabled: true,
    details_submitted: true,
    connected_at: '2026-09-09T10:00:00Z',
    deauthorized_at: null,
    last_synced_at: '2026-09-09T10:05:00Z',
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar(queryParams: Record<string, string> = {}): void {
  TestBed.configureTestingModule({
    imports: [
      TranslocoTestingModule.forRoot({
        langs: { 'es-ES': es },
        translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
      }),
    ],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { queryParamMap: convertToParamMap(queryParams) } },
      },
    ],
  });
}

describe('StripeConnection', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('sin conexión: muestra el estado y sin violaciones de accesibilidad', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(StripeConnection);
    await avanzar(fixture);
    http.expectOne((p) => p.url === ME_URL).flush({ id: ORG_ID });
    await avanzar(fixture);
    http.expectOne((p) => p.method === 'GET' && p.url === STRIPE_URL).flush(estadoNoConectado());
    await avanzar(fixture);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain(
      'Todavía no has conectado ninguna cuenta de Stripe.',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('operativa: pide el estado persistido, no sincroniza al cargar', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(StripeConnection);
    await avanzar(fixture);
    http.expectOne((p) => p.url === ME_URL).flush({ id: ORG_ID });
    await avanzar(fixture);
    http.expectOne((p) => p.method === 'GET' && p.url === STRIPE_URL).flush(estadoOperativo());
    await avanzar(fixture);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain(
      'Cuenta conectada y operativa: ya puedes vender entradas de pago.',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('al volver del onboarding, sincroniza en vez de leer el estado persistido', async () => {
    configurar({ onboarding: 'retorno' });
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(StripeConnection);
    await avanzar(fixture);
    http.expectOne((p) => p.url === ME_URL).flush({ id: ORG_ID });
    await avanzar(fixture);
    const sync = http.expectOne((p) => p.method === 'POST' && p.url === `${STRIPE_URL}/sync`);
    sync.flush(estadoOperativo());
    await avanzar(fixture);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain(
      'Cuenta conectada y operativa: ya puedes vender entradas de pago.',
    );
  });

  it('desautorizada: ofrece reconectar', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(StripeConnection);
    await avanzar(fixture);
    http.expectOne((p) => p.url === ME_URL).flush({ id: ORG_ID });
    await avanzar(fixture);
    http
      .expectOne((p) => p.method === 'GET' && p.url === STRIPE_URL)
      .flush({
        ...estadoOperativo(),
        charges_enabled: false,
        deauthorized_at: '2026-09-01T00:00:00Z',
      });
    await avanzar(fixture);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Reconectar con Stripe');
  });
});
