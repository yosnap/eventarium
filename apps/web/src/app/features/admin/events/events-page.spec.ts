import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { EventsPage } from './events-page';

function pagina() {
  return {
    items: [
      {
        id: 'e1',
        slug: 'iawic-2026',
        title: 'IA Week in Cascais 2026',
        status: 'draft',
        starts_at: '2026-10-01T09:00:00Z',
      },
    ],
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventsPage', () => {
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

  it('lista los eventos y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventsPage);
    await avanzar(fixture);
    http.expectOne((peticion) => peticion.url === '/api/v1/events').flush(pagina());
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('IA Week in Cascais 2026');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('filtra por estado al cambiar el selector', async () => {
    const fixture = TestBed.createComponent(EventsPage);
    await avanzar(fixture);
    http.expectOne((peticion) => peticion.url === '/api/v1/events').flush(pagina());
    await avanzar(fixture);

    const select = fixture.nativeElement.querySelector('#filtro-estado') as HTMLSelectElement;
    select.value = 'published';
    select.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const peticion = http.expectOne((peticion) => peticion.url === '/api/v1/events');
    expect(peticion.request.params.get('status')).toBe('published');
    peticion.flush({ items: [] });
  });
});
