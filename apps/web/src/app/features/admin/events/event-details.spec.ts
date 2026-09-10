import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { EventDetails } from './event-details';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar() {
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
      provideRouter([]),
    ],
  });
}

async function crearComponente(eventId = 'e1'): Promise<ComponentFixture<EventDetails>> {
  const fixture = TestBed.createComponent(EventDetails);
  fixture.componentRef.setInput('eventId', eventId);
  await avanzar(fixture);
  return fixture;
}

function flushCargaBase(
  http: HttpTestingController,
  overrides: Record<string, unknown> = {},
): void {
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1')
    .flush({
      cover_url: null,
      status: 'draft',
      registration_mode: 'free',
      ...overrides,
    });
}

function flushSedes(http: HttpTestingController): void {
  // `EventVenues` y `EventAgenda` (para su selector de sede) piden las sedes cada
  // uno por su cuenta: hay dos peticiones idénticas en vuelo a la vez.
  for (const peticion of http.match((p) => p.url === '/api/v1/events/e1/venues')) {
    peticion.flush([]);
  }
}

function flushSeccionesLibresDePago(http: HttpTestingController): void {
  flushSedes(http);
  http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/sessions').flush([]);
  http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/members').flush([]);
  http
    .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/members')
    .flush({ items: [], total: 0, limit: 200, offset: 0 });
  http
    .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/sponsor-tiers')
    .flush({ items: [], total: 0, limit: 100, offset: 0 });
  http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/sponsors').flush([]);
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations')
    .flush({ items: [], total: 0, limit: 20, offset: 0 });
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
    .flush({
      initiated: 0,
      verified: 0,
      pending_approval: 0,
      confirmed: 0,
      rejected: 0,
      cancelled: 0,
      waitlisted: 0,
      verified_conversion_rate: null,
      confirmed_conversion_rate: null,
    });
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
    .flush([]);
}

describe('EventDetails', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('evento gratuito: pinta agenda, patrocinadores e inscripciones, sin entradas ni descuentos', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const fixture = await crearComponente();
    flushCargaBase(http);
    await avanzar(fixture);
    flushSeccionesLibresDePago(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('app-event-venues')).not.toBeNull();
    expect(raiz.querySelector('app-event-agenda')).not.toBeNull();
    expect(raiz.querySelector('app-event-sponsors')).not.toBeNull();
    expect(raiz.querySelector('app-event-registrations')).not.toBeNull();
    expect(raiz.querySelector('app-event-ticket-types')).toBeNull();
    expect(raiz.querySelector('app-event-discount-codes')).toBeNull();
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('evento de pago: añade entradas, descuentos y el aviso de Stripe', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const fixture = await crearComponente();
    flushCargaBase(http, { registration_mode: 'paid' });
    await avanzar(fixture);
    flushSedes(http);
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/sessions').flush([]);
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/members').flush([]);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/members')
      .flush({ items: [], total: 0, limit: 200, offset: 0 });
    http
      .expectOne((peticion) => peticion.url === '/api/v1/organizations/me/sponsor-tiers')
      .flush({ items: [], total: 0, limit: 100, offset: 0 });
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/sponsors').flush([]);
    // `app-event-ticket-types` y `app-event-discount-codes` comprueban por su cuenta el
    // modo de inscripción del evento antes de mostrar su gestor (fase 3): cada uno pide
    // el evento de nuevo.
    for (const peticion of http.match((p) => p.method === 'GET' && p.url === '/api/v1/events/e1')) {
      peticion.flush({ cover_url: null, status: 'draft', registration_mode: 'paid' });
    }
    await avanzar(fixture);
    for (const peticion of http.match((p) => p.url === '/api/v1/events/e1/ticket-types')) {
      peticion.flush([]);
    }
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/discount-codes').flush([]);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations')
      .flush({ items: [], total: 0, limit: 20, offset: 0 });
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
      .flush({
        initiated: 0,
        verified: 0,
        pending_approval: 0,
        confirmed: 0,
        rejected: 0,
        cancelled: 0,
        waitlisted: 0,
        verified_conversion_rate: null,
        confirmed_conversion_rate: null,
      });
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
      .flush([]);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('app-event-ticket-types')).not.toBeNull();
    expect(raiz.querySelector('app-event-discount-codes')).not.toBeNull();
    expect(raiz.textContent).toContain(
      'no podrá publicarse hasta conectar y verificar una cuenta de Stripe',
    );
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('publicar cambia el estado mostrado', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const fixture = await crearComponente();
    flushCargaBase(http);
    await avanzar(fixture);
    flushSeccionesLibresDePago(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const publicar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Publicar'),
    );
    publicar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1' && peticion.method === 'PATCH')
      .flush({ cover_url: null, status: 'published', registration_mode: 'free' });
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Publicado');
  });
});
