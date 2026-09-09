import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventPayments } from './event-payments';

const PAYMENTS_URL = '/api/v1/events/e1/payments';

function pagos() {
  return [
    {
      id: 'p1',
      registration_id: 'r1',
      email: 'persona@example.com',
      ticket_type_name: 'General',
      status: 'paid',
      amount_cents: 1000,
      discount_cents: 0,
      currency: 'eur',
      refunded_cents: 0,
      paid_at: '2026-09-01T10:00:00Z',
      no_auto_refund_reason: null,
      refunds: [],
    },
  ];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventPayments', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    // jsdom no implementa `showModal`/`close` de `<dialog>`: se sustituyen
    // por dobles mínimos que solo reflejan el atributo `open`, suficiente
    // para que el componente (que delega el foco/`Escape` en el navegador)
    // no lance en el entorno de pruebas.
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      };
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      };
    } else {
      vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (
        this: HTMLDialogElement,
      ) {
        this.setAttribute('open', '');
      });
      vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (
        this: HTMLDialogElement,
      ) {
        this.removeAttribute('open');
      });
    }

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
    vi.restoreAllMocks();
  });

  it('lista los pagos del evento sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventPayments);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    http.expectOne((p) => p.url === PAYMENTS_URL && p.method === 'GET').flush(pagos());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('persona@example.com');
    expect(texto).toContain('General');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('abre el diálogo de reembolso preseleccionando el importe pendiente', async () => {
    const fixture = TestBed.createComponent(EventPayments);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne((p) => p.url === PAYMENTS_URL && p.method === 'GET').flush(pagos());
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('button.secundario') as HTMLButtonElement)?.click();
    await avanzar(fixture);

    const dialogo = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    expect(dialogo.hasAttribute('open')).toBe(true);
    const importe = fixture.nativeElement.querySelector('#reembolso-importe') as HTMLInputElement;
    expect(importe.value).toBe('10.00');
  });

  it('reembolso total revoca siempre la entrada, sin mostrar la casilla', async () => {
    const fixture = TestBed.createComponent(EventPayments);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne((p) => p.url === PAYMENTS_URL && p.method === 'GET').flush(pagos());
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('button.secundario') as HTMLButtonElement)?.click();
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const solicitud = http.expectOne(
      (p) => p.url === `${PAYMENTS_URL}/p1/refund` && p.method === 'POST',
    );
    expect(solicitud.request.body).toEqual({ revoke_ticket: true });
    solicitud.flush({ status: 'in_progress', refund_id: 'ref1' });
    await avanzar(fixture);

    http.expectOne((p) => p.url === PAYMENTS_URL && p.method === 'GET').flush(pagos());
    await avanzar(fixture);
    expect(fixture.nativeElement.textContent).toContain('Reembolso en curso');
  });
});
