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

function eventoDetalle(overrides: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    slug: 'iawic-2026',
    title: 'IA Week in Cascais 2026',
    starts_at: '2026-10-01T09:00:00Z',
    ends_at: '2026-10-02T18:00:00Z',
    location_mode: 'in_person',
    timezone: 'Europe/Madrid',
    payment_checkout_window_minutes: 45,
    ...overrides,
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
        useValue: { snapshot: { paramMap: convertToParamMap(id ? { eventId: id } : {}) } },
      },
    ],
  });
}

/** `EventDetails` (delegado desde `EventForm` en modo edición) pide sus propios
 * datos —solo portada y estado, ya no arrastra ninguna sección del evento—: se
 * vacía aquí para no dejar la petición pendiente en `http.verify()`. */
async function flushEventDetails(
  http: HttpTestingController,
  fixture: ComponentFixture<unknown>,
): Promise<void> {
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1' && peticion.method === 'GET')
    .flush({ cover_url: null, status: 'draft' });
  await avanzar(fixture);
}

describe('EventForm', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('modo alta: sin violaciones de accesibilidad y sin pedir el evento ni delegar en EventDetails', async () => {
    configurar(null);
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(EventForm);
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('app-event-details')).toBeNull();
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

  it('modo edición: carga los datos base y delega el resto en EventDetails', async () => {
    configurar('e1');
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(EventForm);
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1' && peticion.method === 'GET')
      .flush(eventoDetalle());
    await avanzar(fixture);

    expect((fixture.nativeElement.querySelector('#evento-titulo') as HTMLInputElement).value).toBe(
      'IA Week in Cascais 2026',
    );
    expect(
      (fixture.nativeElement.querySelector('#evento-ventana-pago') as HTMLInputElement).value,
    ).toBe('45');
    expect(
      (fixture.nativeElement.querySelector('#evento-zona-horaria-nativo') as HTMLSelectElement)
        .value,
    ).toBe('Europe/Madrid');
    expect(fixture.nativeElement.querySelector('app-event-details')).not.toBeNull();

    await flushEventDetails(http, fixture);

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
