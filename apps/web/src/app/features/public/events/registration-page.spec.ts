import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PLATFORM_ID, Component, provideZonelessChangeDetection, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Meta, Title } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { type Mock, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
import { ApiError } from '../../../core/api/error.interceptor';
import {
  type PoliticasPublicas,
  PublicPoliciesService,
} from '../../../core/policies/public-policies.service';
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
    politicas: Partial<PublicPoliciesService> | null = null,
  ) {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
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
        {
          provide: PublicPoliciesService,
          // Por defecto, un evento sin textos propios del organizador.
          useValue: politicas ?? {
            obtener: vi.fn().mockResolvedValue({ organization_name: '', policies: [] }),
          },
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

    it('pone un título propio y, al llegar el evento, lo completa sin heredar nada', async () => {
      const meta = TestBed.inject(Meta);
      meta.updateTag({ property: 'og:description', content: 'Descripción del evento anterior' });
      const fixture = crearFixture();
      fixture.detectChanges();
      const titulo = TestBed.inject(Title);
      expect(titulo.getTitle()).toBe('Inscripción');

      TestBed.inject(HttpTestingController)
        .expectOne((peticion) => peticion.url.endsWith('/public/events/iawic-2026'))
        .flush({ title: 'IA Week', summary: null, cover_url: null, theme: null });
      await avanzar(fixture);

      expect(titulo.getTitle()).toBe('Inscripción · IA Week');
      expect(meta.getTag('property="og:description"')?.content).toBe(es.publico.eventos.sinResumen);
    });

    it('si falla la carga del evento, se queda con su título y no con el anterior', async () => {
      TestBed.inject(Title).setTitle('Congreso anterior');
      const fixture = crearFixture();
      fixture.detectChanges();

      TestBed.inject(HttpTestingController)
        .expectOne((peticion) => peticion.url.endsWith('/public/events/iawic-2026'))
        .flush(null, { status: 500, statusText: 'Error' });
      await avanzar(fixture);

      expect(TestBed.inject(Title).getTitle()).toBe('Inscripción');
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

    it('muestra los pasos y el texto de un evento gratuito', async () => {
      const fixture = crearFixture();
      await avanzar(fixture);

      const texto = fixture.nativeElement.textContent;
      expect(texto).toContain('Tus datos');
      expect(texto).toContain('Confirmación por email');
      expect(texto).toContain('Este evento es gratuito');
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
          // Sin textos del organizador no se acepta nada.
          acceptedPolicyVersionIds: [],
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

    it('muestra los pasos y el texto de un evento de pago', async () => {
      configurar(
        { getQuestions: vi.fn().mockResolvedValue([]) },
        { getTicketTypes: vi.fn().mockResolvedValue(TIPOS_DE_ENTRADA) },
      );
      const fixture = crearFixture();
      await avanzar(fixture);

      const texto = fixture.nativeElement.textContent;
      expect(texto).toContain('Tus datos y entrada');
      expect(texto).toContain('Pago');
      expect(texto).toContain('pago seguro');
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

  describe('con políticas del organizador', () => {
    const POLITICAS: PoliticasPublicas = {
      organization_name: 'IA Week',
      policies: [
        {
          version_id: 'v-condiciones',
          kind: 'condiciones',
          version: 1,
          content: 'Condiciones',
          created_at: '2026-09-23T10:00:00Z',
        },
        {
          version_id: 'v-privacidad',
          kind: 'privacidad',
          version: 2,
          content: 'Privacidad',
          created_at: '2026-09-23T10:00:00Z',
        },
      ],
    };
    let obtener: Mock<PublicPoliciesService['obtener']>;
    let submit: Mock<RegistrationsService['submit']>;

    beforeEach(() => {
      obtener = vi.fn<PublicPoliciesService['obtener']>().mockResolvedValue(POLITICAS);
      submit = vi
        .fn<RegistrationsService['submit']>()
        .mockResolvedValue('Si los datos son correctos, recibirás un correo.');
      configurar({ getQuestions: vi.fn().mockResolvedValue([]), submit }, {}, 'browser', {
        obtener,
      });
    });

    function rellenar(nativeElement: HTMLElement, aceptarPoliticas: boolean): void {
      const campoEmail = nativeElement.querySelector('input[type="email"]') as HTMLInputElement;
      campoEmail.value = 'asistente@example.com';
      campoEmail.dispatchEvent(new Event('input'));
      const campoNombre = nativeElement.querySelectorAll('input')[1] as HTMLInputElement;
      campoNombre.value = 'Asistente de Prueba';
      campoNombre.dispatchEvent(new Event('input'));
      const datos = nativeElement.querySelector('#insc-tratamiento-datos') as HTMLInputElement;
      datos.checked = true;
      datos.dispatchEvent(new Event('change'));
      const politicas = nativeElement.querySelector('#insc-politicas') as HTMLInputElement;
      politicas.checked = aceptarPoliticas;
      politicas.dispatchEvent(new Event('change'));
    }

    function rellenarSinPoliticas(nativeElement: HTMLElement): void {
      const campoEmail = nativeElement.querySelector('input[type="email"]') as HTMLInputElement;
      campoEmail.value = 'asistente@example.com';
      campoEmail.dispatchEvent(new Event('input'));
      const campoNombre = nativeElement.querySelectorAll('input')[1] as HTMLInputElement;
      campoNombre.value = 'Asistente de Prueba';
      campoNombre.dispatchEvent(new Event('input'));
      const datos = nativeElement.querySelector('#insc-tratamiento-datos') as HTMLInputElement;
      datos.checked = true;
      datos.dispatchEvent(new Event('change'));
    }

    async function enviar(fixture: ReturnType<typeof crearFixture>): Promise<void> {
      (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
        new Event('submit'),
      );
      await avanzar(fixture);
    }

    it('pinta la casilla con el nombre del organizador y enlaza sus textos', async () => {
      const fixture = crearFixture();
      await avanzar(fixture);
      const raiz = fixture.nativeElement as HTMLElement;
      expect(raiz.textContent).toContain('He leído y acepto las condiciones de IA Week.');
      const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
      expect(enlaces).toContain('/eventos/iawic-2026/politicas');
      // Hay privacidad del organizador: la casilla de datos enlaza a ella.
      expect(enlaces).toContain('/eventos/iawic-2026/politicas#privacidad');
      await esperarSinViolacionesDeAccesibilidad(raiz);
    });

    it('sin marcar la casilla no se envía', async () => {
      const fixture = crearFixture();
      await avanzar(fixture);
      rellenar(fixture.nativeElement, false);
      await enviar(fixture);
      expect(submit).not.toHaveBeenCalled();
      expect(fixture.nativeElement.textContent).toContain(
        'Debes aceptar las condiciones del organizador',
      );
    });

    it('al marcarla envía las versiones que se muestran', async () => {
      const fixture = crearFixture();
      await avanzar(fixture);
      rellenar(fixture.nativeElement, true);
      await enviar(fixture);
      expect(submit).toHaveBeenCalledWith(
        'iawic-2026',
        expect.objectContaining({
          acceptedPolicyVersionIds: ['v-condiciones', 'v-privacidad'],
        }),
      );
    });

    it('si no se pueden cargar, avisa, no deja enviar y permite reintentar', async () => {
      obtener.mockReset();
      obtener.mockRejectedValueOnce(new Error('red')).mockResolvedValue(POLITICAS);
      const fixture = crearFixture();
      await avanzar(fixture);
      fixture.detectChanges();
      const raiz = fixture.nativeElement as HTMLElement;
      expect(raiz.textContent).toContain('No se han podido cargar las condiciones');
      expect(raiz.querySelector('#insc-politicas')).toBeNull();

      await enviar(fixture);
      expect(submit).not.toHaveBeenCalled();

      const reintentar = Array.from(raiz.querySelectorAll('button')).find(
        (boton) => boton.textContent?.trim() === 'Reintentar',
      ) as HTMLButtonElement;
      reintentar.click();
      await avanzar(fixture);
      fixture.detectChanges();
      expect(raiz.querySelector('#insc-politicas')).not.toBeNull();
    });

    it('si la API no tiene el endpoint (404), se inscribe como sin textos', async () => {
      obtener.mockReset();
      obtener.mockRejectedValue(new ApiError(404, 'No encontrado', { status: 404 }));
      const fixture = crearFixture();
      await avanzar(fixture);
      fixture.detectChanges();
      const raiz = fixture.nativeElement as HTMLElement;
      expect(raiz.querySelector('#insc-politicas')).toBeNull();
      expect(raiz.textContent).not.toContain('No se han podido cargar las condiciones');

      rellenarSinPoliticas(raiz);
      await enviar(fixture);
      expect(submit).toHaveBeenCalledWith(
        'iawic-2026',
        expect.objectContaining({ acceptedPolicyVersionIds: [] }),
      );
    });

    it('si cambiaron a mitad, recarga, desmarca y conserva lo escrito', async () => {
      submit.mockRejectedValueOnce(
        new ApiError(409, 'Las condiciones han cambiado', {
          status: 409,
          code: 'politicas_cambiadas',
        }),
      );
      const fixture = crearFixture();
      await avanzar(fixture);
      rellenar(fixture.nativeElement, true);
      // Como en el navegador: tras el clic hay un ciclo de render antes de enviar.
      await avanzar(fixture);
      fixture.detectChanges();
      await enviar(fixture);
      await avanzar(fixture);
      fixture.detectChanges();

      const raiz = fixture.nativeElement as HTMLElement;
      expect(obtener).toHaveBeenCalledTimes(2);
      expect((raiz.querySelector('#insc-politicas') as HTMLInputElement).checked).toBe(false);
      expect(raiz.textContent).toContain('han cambiado mientras rellenabas el formulario');
      expect((raiz.querySelector('input[type="email"]') as HTMLInputElement).value).toBe(
        'asistente@example.com',
      );
    });
  });

  describe('compra con políticas del organizador', () => {
    it('envía las versiones al checkout y trata el 409 igual que la inscripción', async () => {
      const startCheckout = vi.fn<PublicCheckoutService['startCheckout']>().mockRejectedValueOnce(
        new ApiError(409, 'Las condiciones han cambiado', {
          status: 409,
          code: 'politicas_cambiadas',
        }),
      );
      const obtener = vi.fn<PublicPoliciesService['obtener']>().mockResolvedValue({
        organization_name: 'IA Week',
        policies: [
          {
            version_id: 'v-reembolsos',
            kind: 'reembolsos',
            version: 1,
            content: 'Sin reembolsos',
            created_at: '2026-09-23T10:00:00Z',
          },
        ],
      });
      configurar(
        { getQuestions: vi.fn().mockResolvedValue([]) },
        {
          getTicketTypes: vi.fn().mockResolvedValue(TIPOS_DE_ENTRADA),
          quote: vi.fn().mockResolvedValue(PRESUPUESTO),
          startCheckout,
        },
        'browser',
        { obtener },
      );
      const fixture = crearFixture();
      await avanzar(fixture);
      fixture.detectChanges();
      const raiz = fixture.nativeElement as HTMLElement;

      (raiz.querySelector('input[name="tipo-entrada"]') as HTMLInputElement).dispatchEvent(
        new Event('change'),
      );
      await avanzar(fixture);
      const campoEmail = raiz.querySelector('input[type="email"]') as HTMLInputElement;
      campoEmail.value = 'compra@example.com';
      campoEmail.dispatchEvent(new Event('input'));
      const campoNombre = raiz.querySelectorAll('input')[1] as HTMLInputElement;
      campoNombre.value = 'Compradora';
      campoNombre.dispatchEvent(new Event('input'));
      for (const id of ['#insc-tratamiento-datos', '#insc-politicas']) {
        const casilla = raiz.querySelector(id) as HTMLInputElement;
        casilla.checked = true;
        casilla.dispatchEvent(new Event('change'));
      }
      await avanzar(fixture);
      fixture.detectChanges();

      (raiz.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
      await avanzar(fixture);
      fixture.detectChanges();

      expect(startCheckout).toHaveBeenCalledWith(
        'iawic-2026',
        expect.objectContaining({ acceptedPolicyVersionIds: ['v-reembolsos'] }),
      );
      expect(obtener).toHaveBeenCalledTimes(2);
      expect((raiz.querySelector('#insc-politicas') as HTMLInputElement).checked).toBe(false);
      expect(raiz.textContent).toContain('han cambiado mientras rellenabas el formulario');
    });
  });
});
