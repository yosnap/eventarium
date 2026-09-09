import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { EventForm } from './event-form';

function eventoDetalle() {
  return {
    id: 'e1',
    slug: 'iawic-2026',
    title: 'IA Week in Cascais 2026',
    summary: null,
    cover_url: null,
    status: 'draft',
    starts_at: '2026-10-01T09:00:00Z',
    ends_at: '2026-10-02T18:00:00Z',
    location_mode: 'in_person',
    payment_checkout_window_minutes: 45,
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar(id: string | null) {
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
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap(id ? { id } : {}) } },
      },
    ],
  });
}

describe('EventForm', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('modo alta: sin violaciones de accesibilidad y sin pedir el evento', async () => {
    configurar(null);
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(EventForm);
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('app-event-agenda')).toBeNull();
    const campoVentana = fixture.nativeElement.querySelector(
      '#evento-ventana-pago',
    ) as HTMLInputElement;
    expect(campoVentana.value).toBe('30');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('modo alta: 29 o 1440 minutos de ventana de pago se bloquean en el cliente', async () => {
    configurar(null);
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(EventForm);
    await avanzar(fixture);

    const campoVentana = fixture.nativeElement.querySelector(
      '#evento-ventana-pago',
    ) as HTMLInputElement;
    campoVentana.value = '29';
    campoVentana.dispatchEvent(new Event('input'));
    campoVentana.dispatchEvent(new Event('blur'));
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Debe estar entre 30 y 1439 minutos.');
  });

  it('modo edición: carga el evento y la agenda, sin violaciones de accesibilidad', async () => {
    configurar('e1');
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(EventForm);
    await avanzar(fixture);
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1').flush(eventoDetalle());
    await avanzar(fixture);
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
    await avanzar(fixture);

    expect((fixture.nativeElement.querySelector('#evento-titulo') as HTMLInputElement).value).toBe(
      'IA Week in Cascais 2026',
    );
    expect(
      (fixture.nativeElement.querySelector('#evento-ventana-pago') as HTMLInputElement).value,
    ).toBe('45');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
