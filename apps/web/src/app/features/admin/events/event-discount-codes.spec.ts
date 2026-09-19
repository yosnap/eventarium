import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventDiscountCodes } from './event-discount-codes';

const EVENT_URL = '/api/v1/events/e1';
const TICKET_TYPES_URL = '/api/v1/events/e1/ticket-types';
const DISCOUNT_CODES_URL = '/api/v1/events/e1/discount-codes';

function flushEventoDePago(http: HttpTestingController): void {
  http
    .expectOne((p) => p.url === EVENT_URL && p.method === 'GET')
    .flush({ registration_mode: 'paid' });
}

function tipos() {
  return [{ id: 't1', name: 'General' }];
}

function codigos() {
  return [
    {
      id: 'c1',
      code: 'VERANO2026',
      discount_type: 'percentage',
      discount_value: 20,
      max_uses: 10,
      valid_from: null,
      valid_until: null,
      ticket_type_id: null,
      used_count: 3,
    },
  ];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventDiscountCodes', () => {
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

  it('lista los códigos de descuento con su uso derivado, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventDiscountCodes);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    flushEventoDePago(http);
    await avanzar(fixture);

    http.expectOne((p) => p.url === TICKET_TYPES_URL).flush(tipos());
    http.expectOne((p) => p.url === DISCOUNT_CODES_URL && p.method === 'GET').flush(codigos());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('VERANO2026');
    expect(texto).toContain('3 de 10 usos');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige código y valor de descuento válidos antes de dar de alta un código', async () => {
    const fixture = TestBed.createComponent(EventDiscountCodes);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    flushEventoDePago(http);
    await avanzar(fixture);
    http.expectOne((p) => p.url === TICKET_TYPES_URL).flush([]);
    http.expectOne((p) => p.url === DISCOUNT_CODES_URL && p.method === 'GET').flush([]);
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((p) => p.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain('Escribe el código de descuento.');
  });

  it('en un evento sin pagos, explica que los códigos de descuento no aplican y no pide listas', async () => {
    const fixture = TestBed.createComponent(EventDiscountCodes);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http
      .expectOne((p) => p.url === EVENT_URL && p.method === 'GET')
      .flush({
        registration_mode: 'approval',
      });
    await avanzar(fixture);

    http.expectNone((p) => p.url === TICKET_TYPES_URL);
    http.expectNone((p) => p.url === DISCOUNT_CODES_URL);
    expect(fixture.nativeElement.textContent).toContain('Este evento no acepta pagos');
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
  });
});
