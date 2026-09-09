import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventTicketTypes } from './event-ticket-types';

const TICKET_TYPES_URL = '/api/v1/events/e1/ticket-types';

function tipos() {
  return [
    {
      id: 't1',
      name: 'General',
      description: null,
      price_cents: 1000,
      currency: 'eur',
      max_quantity: 100,
      sales_start_at: null,
      sales_end_at: null,
      sort_order: 0,
      is_active: true,
    },
    {
      id: 't2',
      name: 'VIP',
      description: null,
      price_cents: 5000,
      currency: 'eur',
      max_quantity: null,
      sales_start_at: null,
      sales_end_at: null,
      sort_order: 1,
      is_active: true,
    },
  ];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventTicketTypes', () => {
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

  it('lista los tipos de entrada del evento, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventTicketTypes);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    http.expectOne((p) => p.url === TICKET_TYPES_URL && p.method === 'GET').flush(tipos());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('General');
    expect(texto).toContain('VIP');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige nombre y precio válido antes de dar de alta un tipo de entrada', async () => {
    const fixture = TestBed.createComponent(EventTicketTypes);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne((p) => p.url === TICKET_TYPES_URL && p.method === 'GET').flush([]);
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((p) => p.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('Escribe el nombre del tipo de entrada.');
  });
});
