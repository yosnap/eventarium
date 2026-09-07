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
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('modo edición: carga el evento y la agenda, sin violaciones de accesibilidad', async () => {
    configurar('e1');
    http = TestBed.inject(HttpTestingController);

    const fixture = TestBed.createComponent(EventForm);
    await avanzar(fixture);
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1').flush(eventoDetalle());
    await avanzar(fixture);
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/sessions').flush([]);
    await avanzar(fixture);

    expect((fixture.nativeElement.querySelector('#evento-titulo') as HTMLInputElement).value).toBe(
      'IA Week in Cascais 2026',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
