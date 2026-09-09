import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PaymentReturnPage } from './payment-return';
import { PublicCheckoutService } from '../../../core/payments/public-checkout.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function rutaCon(parametros: Record<string, string>) {
  return { snapshot: { queryParamMap: convertToParamMap(parametros) } };
}

describe('PaymentReturnPage', () => {
  function configurar(checkout: Partial<PublicCheckoutService>, ruta: unknown) {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        { provide: PublicCheckoutService, useValue: checkout },
        { provide: ActivatedRoute, useValue: ruta },
      ],
    }).compileComponents();
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sin `registration_id` ni `slug` en la URL muestra un error, sin consultar nada', async () => {
    const getStatus = vi.fn();
    configurar({ getStatus }, rutaCon({}));

    const fixture = TestBed.createComponent(PaymentReturnPage);
    await fixture.whenStable();

    expect(getStatus).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('No hemos podido comprobar');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('consulta el estado real y nunca da el pago por confirmado por el mero retorno de Stripe', async () => {
    const getStatus = vi.fn().mockResolvedValue({
      registration_status: 'confirmed',
      payment_status: 'paid',
    });
    configurar({ getStatus }, rutaCon({ registration_id: 'reg-1', slug: 'iawic-2026' }));

    const fixture = TestBed.createComponent(PaymentReturnPage);
    await fixture.whenStable();

    // El estado inicial es «comprobando», nunca «confirmado» de entrada: solo
    // pasa a confirmado después de que la respuesta del backend lo diga.
    expect(getStatus).toHaveBeenCalledWith('iawic-2026', 'reg-1');
    expect(fixture.nativeElement.textContent).toContain('¡Pago confirmado!');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con el pago aún pendiente, anuncia el estado por `aria-live` y reintenta a mano', async () => {
    const getStatus = vi.fn().mockResolvedValue({
      registration_status: 'pending_payment',
      payment_status: 'pending',
    });
    configurar({ getStatus }, rutaCon({ registration_id: 'reg-1', slug: 'iawic-2026' }));

    const fixture = TestBed.createComponent(PaymentReturnPage);
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="polite"]');
    expect(zonaAnuncio?.textContent).toContain('todavía no se ha confirmado');

    const boton = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(boton).toBeTruthy();
    // `(click)` está en el host `<app-button>`, no en el `<button>` nativo
    // interno: el evento tiene que poder subir por el árbol para llegar a él.
    boton.dispatchEvent(new Event('click', { bubbles: true }));
    await fixture.whenStable();
    await fixture.whenStable();

    expect(getStatus).toHaveBeenCalledTimes(2);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('una inscripción cancelada o un pago caducado se muestran como fallidos, no como pendientes', async () => {
    const getStatus = vi.fn().mockResolvedValue({
      registration_status: 'cancelled',
      payment_status: 'expired',
    });
    configurar({ getStatus }, rutaCon({ registration_id: 'reg-1', slug: 'iawic-2026' }));

    const fixture = TestBed.createComponent(PaymentReturnPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('No hemos podido confirmar tu pago');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('un error de red al consultar el estado no se confunde con un pago fallido', async () => {
    const getStatus = vi.fn().mockRejectedValue(new Error('red caída'));
    configurar({ getStatus }, rutaCon({ registration_id: 'reg-1', slug: 'iawic-2026' }));

    const fixture = TestBed.createComponent(PaymentReturnPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('No hemos podido comprobar');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('reintenta automáticamente un número acotado de veces mientras el pago sigue pendiente', async () => {
    vi.useFakeTimers();
    const getStatus = vi.fn().mockResolvedValue({
      registration_status: 'pending_payment',
      payment_status: 'pending',
    });
    configurar({ getStatus }, rutaCon({ registration_id: 'reg-1', slug: 'iawic-2026' }));

    TestBed.createComponent(PaymentReturnPage);
    await vi.advanceTimersByTimeAsync(0);
    expect(getStatus).toHaveBeenCalledTimes(1);

    // Cinco reintentos automáticos como máximo (2s + 4s + 8s + 8s + 8s): tras
    // agotarlos, ninguna espera adicional dispara una consulta más por sí sola.
    await vi.advanceTimersByTimeAsync(2000 + 4000 + 8000 + 8000 + 8000);
    expect(getStatus).toHaveBeenCalledTimes(6);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(getStatus).toHaveBeenCalledTimes(6);
  });
});
