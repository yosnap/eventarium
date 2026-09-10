import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventVenues } from './event-venues';

const VENUES_URL = '/api/v1/events/e1/venues';

// El componente usa `app-address-map`, que carga leaflet de forma perezosa: se
// mockea igual que en `address-map.spec.ts` para no depender de la librería real.
vi.mock('leaflet', () => ({
  map: vi.fn(() => ({ setView: vi.fn().mockReturnThis(), invalidateSize: vi.fn(), remove: vi.fn() })),
  tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
  marker: vi.fn(() => ({ addTo: vi.fn(() => ({ setLatLng: vi.fn() })), setLatLng: vi.fn() })),
}));

function sedes() {
  return [
    {
      id: 'v1',
      name: 'Auditorio Principal',
      address: 'Calle Mayor 1, Valencia',
      capacity: 200,
      display_order: 0,
      latitude: 39.47,
      longitude: -0.376,
      geocoded_at: '2026-01-01T00:00:00Z',
    },
  ];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventVenues', () => {
  let http: HttpTestingController;

  beforeEach(() => {
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
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lista las sedes con su estado de geolocalización, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventVenues);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    http.expectOne((p) => p.url === VENUES_URL).flush(sedes());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Auditorio Principal');
    expect(texto).toContain('Geolocalizada');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige el nombre antes de dar de alta una sede', async () => {
    const fixture = TestBed.createComponent(EventVenues);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne((p) => p.url === VENUES_URL).flush([]);
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((p) => p.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('Escribe el nombre de la sede.');
  });

  it('muestra el error del backend al borrar una sede con sesiones asociadas', async () => {
    const fixture = TestBed.createComponent(EventVenues);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne((p) => p.url === VENUES_URL).flush(sedes());
    await avanzar(fixture);

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('.acciones button'),
    ) as HTMLButtonElement[];
    const eliminar = botones.find((boton) => boton.textContent?.trim() === 'Eliminar');
    eliminar?.click();
    await avanzar(fixture);

    http
      .expectOne((p) => p.url === `${VENUES_URL}/v1` && p.method === 'DELETE')
      .flush(
        { detail: 'No se puede borrar la sede: 2 sesión(es) de la agenda la tienen asignada.' },
        { status: 409, statusText: 'Conflict' },
      );
    await avanzar(fixture);

    // Mismo comportamiento que el resto de pantallas admin (p. ej.
    // `sponsor-tiers-page.spec.ts`): el mensaje mostrado es el genérico del
    // componente, no el `detail` crudo del backend.
    expect(fixture.nativeElement.textContent).toContain('No hemos podido completar la operación.');
  });
});
