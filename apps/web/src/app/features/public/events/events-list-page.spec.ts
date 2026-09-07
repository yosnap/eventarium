import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventsListPage } from './events-list-page';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventsListPage', () => {
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

  it('lista los eventos publicados sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events')
      .flush([
        {
          slug: 'iawic-2026',
          title: 'IA Week in Cascais 2026',
          summary: 'El evento del año.',
          cover_url: null,
          starts_at: '2026-10-01T09:00:00Z',
          location_name: 'Sala principal',
        },
      ]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('IA Week in Cascais 2026');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra el mensaje de "sin eventos" cuando el listado está vacío', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http.expectOne((peticion) => peticion.url === '/api/v1/public/events').flush([]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Todavía no hay eventos publicados');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
