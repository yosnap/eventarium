import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { RegistrationDetailPage } from './registration-detail-page';

const DETALLE = {
  id: 'r1',
  email: 'persona@example.com',
  full_name: 'Persona de Prueba',
  status: 'pending_approval',
  created_at: '2026-10-01T09:00:00Z',
  verified_at: '2026-10-01T09:05:00Z',
  confirmed_at: null,
  waitlist_promoted_at: null,
  waitlist_promotion_expires_at: null,
  approved_at: null,
  rejected_at: null,
  cancelled_at: null,
  answers: [{ question_id: 'q1', label: '¿Camiseta?', value: 'M' }],
  consent: {
    data_processing_accepted_at: '2026-10-01T09:00:00Z',
    marketing_accepted_at: null,
    recording_accepted_at: '2026-10-01T09:00:00Z',
  },
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar(): void {
  TestBed.configureTestingModule({
    imports: [
      TranslocoTestingModule.forRoot({
        langs: { 'es-ES': es },
        translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
      }),
    ],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([errorInterceptor])),
      provideHttpClientTesting(),
      provideRouter([]),
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: { paramMap: convertToParamMap({ id: 'e1', registrationId: 'r1' }) },
        },
      },
    ],
  });
}

describe('RegistrationDetailPage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    configurar();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('muestra los datos, respuestas y consentimientos, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(RegistrationDetailPage);
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/r1')
      .flush(DETALLE);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('persona@example.com');
    expect(fixture.nativeElement.textContent).toContain('¿Camiseta?');
    expect(fixture.nativeElement.textContent).toContain('Comunicaciones comerciales: no aceptado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('aprueba la inscripción y recarga el detalle', async () => {
    const fixture = TestBed.createComponent(RegistrationDetailPage);
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/r1')
      .flush(DETALLE);
    await avanzar(fixture);

    const botonAprobar = Array.from(fixture.nativeElement.querySelectorAll('button')).find(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Aprobar',
    ) as HTMLButtonElement | undefined;
    botonAprobar?.click();
    await avanzar(fixture);

    http
      .expectOne(
        (peticion) =>
          peticion.url === '/api/v1/events/e1/registrations/r1/approve' &&
          peticion.method === 'POST',
      )
      .flush({ ...DETALLE, status: 'confirmed' });
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/r1')
      .flush({ ...DETALLE, status: 'confirmed' });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Confirmada');
  });

  it('muestra el mensaje de error de la API si la acción falla', async () => {
    const fixture = TestBed.createComponent(RegistrationDetailPage);
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/r1')
      .flush(DETALLE);
    await avanzar(fixture);

    const botonRechazar = Array.from(fixture.nativeElement.querySelectorAll('button')).find(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Rechazar',
    ) as HTMLButtonElement | undefined;
    botonRechazar?.click();
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/r1/reject')
      .flush(
        { title: 'Conflicto', detail: 'La inscripción ya no está pendiente de aprobación.' },
        { status: 409, statusText: 'Conflict' },
      );
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain(
      'La inscripción ya no está pendiente de aprobación.',
    );
  });
});
