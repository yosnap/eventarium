import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventRegistrations } from './event-registrations';

function pagina(items: unknown[] = ITEMS, total = items.length, offset = 0) {
  return { items, total, limit: 20, offset };
}

const ITEMS = [
  {
    id: 'r1',
    email: 'persona@example.com',
    full_name: 'Persona de Prueba',
    status: 'pending_approval',
    created_at: '2026-10-01T09:00:00Z',
    verified_at: '2026-10-01T09:05:00Z',
    confirmed_at: null,
    waitlist_promoted_at: null,
    waitlist_promotion_expires_at: null,
  },
];

const STATS = {
  initiated: 10,
  verified: 8,
  pending_approval: 1,
  confirmed: 5,
  rejected: 1,
  cancelled: 0,
  waitlisted: 1,
  verified_conversion_rate: 0.8,
  confirmed_conversion_rate: 0.5,
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** Flujo de peticiones que dispara el componente al iniciar: listado, estadísticas
 * y las preguntas del formulario de inscripción (subcomponente siempre presente). */
function flushCargaInicial(
  http: HttpTestingController,
  itemsPage: ReturnType<typeof pagina> = pagina(),
): void {
  http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations').flush(itemsPage);
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
    .flush(STATS);
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
    .flush([]);
}

describe('EventRegistrations', () => {
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
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lista las inscripciones con sus estadísticas y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('persona@example.com');
    expect(fixture.nativeElement.textContent).toContain('Persona de Prueba');
    expect(fixture.nativeElement.textContent).toContain('80.0%');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('ofrece aprobar y rechazar una inscripción pendiente de aprobación, y refresca tras la acción', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    const botonAprobar = Array.from(fixture.nativeElement.querySelectorAll('button')).find(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Aprobar',
    ) as HTMLButtonElement | undefined;
    expect(botonAprobar).toBeTruthy();
    botonAprobar?.click();
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) =>
        peticion.url === '/api/v1/events/e1/registrations/r1/approve' && peticion.method === 'POST',
    );
    peticion.flush({ ...ITEMS[0], status: 'confirmed' });
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations')
      .flush(pagina([{ ...ITEMS[0], status: 'confirmed' }]));
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
      .flush(STATS);
    await avanzar(fixture);
  });

  it('filtra por estado y vuelve a pedir el listado', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    const select = fixture.nativeElement.querySelector(
      '#registros-filtro-estado',
    ) as HTMLSelectElement;
    select.value = 'confirmed';
    select.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/events/e1/registrations',
    );
    expect(peticion.request.params.get('status')).toBe('confirmed');
    peticion.flush(pagina([]));
    await avanzar(fixture);
  });
});
