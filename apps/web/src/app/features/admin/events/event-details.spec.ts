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
    .flush({ cover_url: null, status: 'draft', ...overrides });
}

describe('EventDetails', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('pinta solo portada y estado, sin ninguna sección del evento', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const fixture = await crearComponente();
    flushCargaBase(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('app-event-venues')).toBeNull();
    expect(raiz.querySelector('app-event-agenda')).toBeNull();
    expect(raiz.querySelector('app-event-sponsors')).toBeNull();
    expect(raiz.querySelector('app-event-registrations')).toBeNull();
    expect(raiz.querySelector('app-event-ticket-types')).toBeNull();
    expect(raiz.querySelector('app-event-discount-codes')).toBeNull();
    expect(raiz.textContent).toContain('Portada');
    expect(raiz.textContent).toContain('Estado');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('publicar cambia el estado mostrado', async () => {
    configurar();
    http = TestBed.inject(HttpTestingController);
    const fixture = await crearComponente();
    flushCargaBase(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const publicar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Publicar'),
    );
    publicar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1' && peticion.method === 'PATCH')
      .flush({ cover_url: null, status: 'published' });
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Publicado');
  });
});
