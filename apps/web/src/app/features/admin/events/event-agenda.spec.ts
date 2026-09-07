import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { EventAgenda } from './event-agenda';

function sesiones() {
  return [
    {
      id: 's1',
      session_type: 'talk',
      title: 'Charla de apertura',
      starts_at: '2026-10-01T09:00:00Z',
      ends_at: '2026-10-01T10:00:00Z',
      room: 'Sala A',
      video_platform: null,
      video_url: null,
      materials: [{ url: 'https://ejemplo.com/slides.pdf' }],
      sort_order: 0,
    },
  ];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventAgenda', () => {
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

  it('lista las sesiones agrupadas por día y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventAgenda);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/sessions')
      .flush(sesiones());
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Charla de apertura');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('añade una sesión nueva con el formulario', async () => {
    const fixture = TestBed.createComponent(EventAgenda);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/sessions').flush([]);
    await avanzar(fixture);

    const titulo = fixture.nativeElement.querySelector('#sesion-titulo') as HTMLInputElement;
    titulo.value = 'Nueva sesión';
    titulo.dispatchEvent(new Event('input'));
    const inicio = fixture.nativeElement.querySelector('#sesion-inicio') as HTMLInputElement;
    inicio.value = '2026-10-01T11:00';
    inicio.dispatchEvent(new Event('input'));
    const fin = fixture.nativeElement.querySelector('#sesion-fin') as HTMLInputElement;
    fin.value = '2026-10-01T12:00';
    fin.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/events/e1/sessions' && peticion.method === 'POST',
    );
    expect(peticion.request.body.title).toBe('Nueva sesión');
    peticion.flush({
      id: 's2',
      session_type: 'talk',
      title: 'Nueva sesión',
      starts_at: '2026-10-01T11:00:00Z',
      ends_at: '2026-10-01T12:00:00Z',
      room: null,
      video_platform: null,
      video_url: null,
      materials: [],
      sort_order: 0,
    });
    await avanzar(fixture);

    http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/sessions').flush(sesiones());
  });
});
