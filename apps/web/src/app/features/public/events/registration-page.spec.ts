import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { PLATFORM_ID, Component, provideZonelessChangeDetection, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RegistrationPage } from './registration-page';
import {
  type CheckoutQuote,
  type PublicTicketType,
  PublicCheckoutService,
} from '../../../core/payments/public-checkout.service';
import {
  type RegistrationQuestion,
  RegistrationsService,
} from '../../../core/registrations/registrations.service';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

@Component({ selector: 'app-turnstile-widget', template: '' })
class TurnstileWidgetFalso {
  readonly resuelto = output<string>();
}

const PREGUNTAS: RegistrationQuestion[] = [
  {
    id: 'q-empresa',
    type: 'short_text',
    label: '¿Empresa?',
    required: true,
    options: null,
    sort_order: 0,
  },
  {
    id: 'q-camiseta',
    type: 'single_choice',
    label: '¿Talla de camiseta?',
    required: false,
    options: ['S', 'M', 'L'],
    sort_order: 1,
  },
  {
    id: 'q-talleres',
    type: 'multiple_choice',
    label: '¿Qué talleres te interesan?',
    required: false,
    options: ['IA', 'Datos'],
    sort_order: 2,
  },
];

const TIPOS_DE_ENTRADA: PublicTicketType[] = [
  { id: 'tipo-general', name: 'General', description: null, price_cents: 2000, currency: 'eur' },
];

const PRESUPUESTO: CheckoutQuote = {
  price_cents: 2000,
  discount_cents: 0,
  total_cents: 2000,
  currency: 'eur',
};

async function avanzar(fixture: { whenStable: () => Promise<unknown> }): Promise<void> {
  await fixture.whenStable();
}

describe('RegistrationPage', () => {
  function configurar(
    registrations: Partial<RegistrationsService>,
    checkout: Partial<PublicCheckoutService> = {},
    plataforma: 'browser' | 'server' = 'browser',
  ) {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: plataforma },
        { provide: RegistrationsService, useValue: registrations },
        {
          provide: PublicCheckoutService,
          useValue: { getTicketTypes: vi.fn().mockResolvedValue([]), ...checkout },
        },
      ],
    })
      .overrideComponent(RegistrationPage, {
        remove: { imports: [TurnstileWidget] },
        add: { imports: [TurnstileWidgetFalso] },
      })
      .compileComponents();
  }

  function crearFixture() {
    const fixture = TestBed.createComponent(RegistrationPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    return fixture;
  }

  describe('evento gratuito', () => {
    beforeEach(() => {
      configurar({
        getQuestions: vi.fn().mockResolvedValue(PREGUNTAS),
        submit: vi.fn().mockResolvedValue('Si los datos son correctos, recibirás un correo.'),
      });
    });

    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renderiza el formulario en tema claro sin violaciones de accesibilidad', async () => {
      document.documentElement.setAttribute('data-theme', 'light');
      const fixture = crearFixture();
      await avanzar(fixture);

      expect(fixture.nativeElement.textContent).toContain('¿Empresa?');
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    it('renderiza las preguntas por tipo sin violaciones de accesibilidad', async () => {
      const fixture = crearFixture();
      await avanzar(fixture);

      const texto = fixture.nativeElement.textContent;
      expect(texto).toContain('¿Empresa?');
      expect(texto).toContain('¿Talla de camiseta?');
      expect(texto).toContain('¿Qué talleres te interesan?');
      expect(fixture.nativeElement.querySelectorAll('input[type="radio"]').length).toBe(3);
      expect(fixture.nativeElement.querySelectorAll('input[type="checkbox"]').length).toBe(2 + 3); // talleres + 3 consentimientos
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    it('bloquea el envío si falta una pregunta obligatoria o el consentimiento', async () => {
      const fixture = crearFixture();
      await avanzar(fixture);
      const registrations = TestBed.inject(RegistrationsService);

      (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
        new Event('submit'),
      );
      await avanzar(fixture);

      expect(registrations.submit).not.toHaveBeenCalled();
      expect(fixture.nativeElement.textContent).toContain('obligatoria');
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    it('con los datos obligatorios completos envía la inscripción', async () => {
      const fixture = crearFixture();
      await avanzar(fixture);
      const registrations = TestBed.inject(RegistrationsService);
      const nativeElement = fixture.nativeElement as HTMLElement;

      const campoEmail = nativeElement.querySelector('input[type="email"]') as HTMLInputElement;
      campoEmail.value = 'asistente@example.com';
      campoEmail.dispatchEvent(new Event('input'));

      const campoNombre = nativeElement.querySelectorAll('input')[1] as HTMLInputElement;
      campoNombre.value = 'Asistente de Prueba';
      campoNombre.dispatchEvent(new Event('input'));

      const campoEmpresa = nativeElement.querySelectorAll('input')[2] as HTMLInputElement;
      campoEmpresa.value = 'Acme';
      campoEmpresa.dispatchEvent(new Event('input'));

      // Los 2 checkboxes de "talleres" van antes que los 3 de consentimiento en el
      // DOM; el de tratamiento de datos es el primero de los tres.
      const checkboxes = Array.from(
        nativeElement.querySelectorAll('input[type="checkbox"]'),
      ) as HTMLInputElement[];
      const checkboxDatos = checkboxes[2];
      checkboxDatos.checked = true;
      checkboxDatos.dispatchEvent(new Event('change'));

      (nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
      await avanzar(fixture);

      expect(registrations.submit).toHaveBeenCalledWith(
        'iawic-2026',
        expect.objectContaining({
          email: 'asistente@example.com',
          fullName: 'Asistente de Prueba',
          dataProcessingAccepted: true,
        }),
      );
      expect(fixture.nativeElement.textContent).toContain('Si los datos son correctos');
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });
  });

  describe('evento de pago', () => {
    function rellenarCamposObligatorios(nativeElement: HTMLElement): void {
      const campoEmail = nativeElement.querySelector('input[type="email"]') as HTMLInputElement;
      campoEmail.value = 'asistente@example.com';
      campoEmail.dispatchEvent(new Event('input'));

      const campoNombre = nativeElement.querySelectorAll('input')[1] as HTMLInputElement;
      campoNombre.value = 'Asistente de Prueba';
      campoNombre.dispatchEvent(new Event('input'));

      const checkboxDatos = nativeElement.querySelector(
        '#insc-tratamiento-datos',
      ) as HTMLInputElement;
      checkboxDatos.checked = true;
      checkboxDatos.dispatchEvent(new Event('change'));
    }

    it('ofrece la selección de tipo de entrada cuando el evento vende entradas', async () => {
      configurar(
        { getQuestions: vi.fn().mockResolvedValue([]) },
        { getTicketTypes: vi.fn().mockResolvedValue(TIPOS_DE_ENTRADA) },
      );
      const fixture = crearFixture();
      await avanzar(fixture);

      expect(fixture.nativeElement.textContent).toContain('General');
      expect(fixture.nativeElement.textContent).toContain('20.00');
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    it('bloquea el envío si no se elige un tipo de entrada', async () => {
      configurar(
        { getQuestions: vi.fn().mockResolvedValue([]) },
        { getTicketTypes: vi.fn().mockResolvedValue(TIPOS_DE_ENTRADA), quote: vi.fn() },
      );
      const fixture = crearFixture();
      await avanzar(fixture);
      const checkout = TestBed.inject(PublicCheckoutService);
      rellenarCamposObligatorios(fixture.nativeElement);

      (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
        new Event('submit'),
      );
      await avanzar(fixture);

      expect(checkout.quote).not.toHaveBeenCalled();
      expect(fixture.nativeElement.textContent).toContain('Elige un tipo de entrada');
    });

    it('pide presupuesto al elegir un tipo y redirige a la URL de Stripe al enviar', async () => {
      const startCheckout = vi
        .fn()
        .mockResolvedValue({ message: 'ok', checkout_url: 'https://checkout.stripe.com/sesion' });
      configurar(
        { getQuestions: vi.fn().mockResolvedValue([]) },
        {
          getTicketTypes: vi.fn().mockResolvedValue(TIPOS_DE_ENTRADA),
          quote: vi.fn().mockResolvedValue(PRESUPUESTO),
          startCheckout,
        },
      );
      const fixture = crearFixture();
      await avanzar(fixture);
      const checkout = TestBed.inject(PublicCheckoutService);
      const nativeElement = fixture.nativeElement as HTMLElement;

      const radioTipo = nativeElement.querySelector(
        'input[name="tipo-entrada"]',
      ) as HTMLInputElement;
      radioTipo.dispatchEvent(new Event('change'));
      await avanzar(fixture);

      expect(checkout.quote).toHaveBeenCalledWith(
        'iawic-2026',
        expect.objectContaining({ ticketTypeId: 'tipo-general' }),
      );
      expect(nativeElement.textContent).toContain('20.00');

      rellenarCamposObligatorios(nativeElement);

      const asignacionDeUrl = vi.fn();
      Object.defineProperty(window, 'location', {
        value: {
          ...window.location,
          set href(url: string) {
            asignacionDeUrl(url);
          },
        },
        writable: true,
      });

      (nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
      await avanzar(fixture);

      expect(startCheckout).toHaveBeenCalledWith(
        'iawic-2026',
        expect.objectContaining({ ticketTypeId: 'tipo-general', email: 'asistente@example.com' }),
      );
      expect(asignacionDeUrl).toHaveBeenCalledWith('https://checkout.stripe.com/sesion');
    });

    it('en modo servidor (SSR) nunca navega, aunque reciba una URL de pago', async () => {
      const startCheckout = vi
        .fn()
        .mockResolvedValue({ message: 'ok', checkout_url: 'https://checkout.stripe.com/sesion' });
      configurar(
        { getQuestions: vi.fn().mockResolvedValue([]) },
        {
          getTicketTypes: vi.fn().mockResolvedValue(TIPOS_DE_ENTRADA),
          quote: vi.fn().mockResolvedValue(PRESUPUESTO),
          startCheckout,
        },
        'server',
      );
      const fixture = crearFixture();
      await avanzar(fixture);
      const nativeElement = fixture.nativeElement as HTMLElement;

      const radioTipo = nativeElement.querySelector(
        'input[name="tipo-entrada"]',
      ) as HTMLInputElement;
      radioTipo.dispatchEvent(new Event('change'));
      await avanzar(fixture);
      rellenarCamposObligatorios(nativeElement);

      const asignacionDeUrl = vi.fn();
      Object.defineProperty(window, 'location', {
        value: {
          ...window.location,
          set href(url: string) {
            asignacionDeUrl(url);
          },
        },
        writable: true,
      });

      (nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
      await avanzar(fixture);

      expect(startCheckout).toHaveBeenCalled();
      expect(asignacionDeUrl).not.toHaveBeenCalled();
    });
  });
});
