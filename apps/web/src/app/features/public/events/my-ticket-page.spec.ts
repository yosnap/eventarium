import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import { MyTicketPage } from './my-ticket-page';
import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

/** Mismo doble mínimo que `layouts/shells.spec.ts`: sin él, `AuthFrame`
 * inyectaría el `ThemingService` real, que necesita `HttpClient`. */
function themingDePrueba() {
  return {
    branding: signal(null),
    error: signal(null),
    templateKey: signal('classic'),
    organizationName: signal('Organización de prueba'),
  };
}

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

describe('MyTicketPage', () => {
  function configurar(registrations: Partial<RegistrationsService>, ruta: unknown) {
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
        { provide: RegistrationsService, useValue: registrations },
        { provide: ActivatedRoute, useValue: ruta },
        { provide: ThemingService, useValue: themingDePrueba() },
      ],
    }).compileComponents();
  }

  it('sin token en la URL muestra el error y no tiene violaciones de accesibilidad', async () => {
    configurar({ getMyTicket: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(MyTicketPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('una inscripción confirmada muestra el QR, no un mensaje de estado', async () => {
    const getMyTicket = vi
      .fn()
      .mockResolvedValue({ status: 'confirmed', full_name: 'Persona de Prueba', has_qr: true });
    const myTicketQrUrl = vi
      .fn()
      .mockReturnValue('/api/v1/public/registrations/my-ticket/qr?token=abc');
    configurar({ getMyTicket, myTicketQrUrl }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(MyTicketPage);
    await fixture.whenStable();

    expect(getMyTicket).toHaveBeenCalledWith('token-valido');
    expect(fixture.nativeElement.textContent).toContain('Persona de Prueba');
    const imagen = fixture.nativeElement.querySelector('img') as HTMLImageElement;
    expect(imagen.src).toContain('/my-ticket/qr');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('una inscripción cancelada muestra el estado sin QR', async () => {
    const getMyTicket = vi
      .fn()
      .mockResolvedValue({ status: 'cancelled', full_name: 'Persona de Prueba', has_qr: false });
    configurar({ getMyTicket }, rutaConToken('token-cancelado'));

    const fixture = TestBed.createComponent(MyTicketPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Tu inscripción está cancelada');
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token no válido muestra el error genérico', async () => {
    const getMyTicket = vi.fn().mockRejectedValue(new Error('no válido'));
    configurar({ getMyTicket }, rutaConToken('token-invalido'));

    const fixture = TestBed.createComponent(MyTicketPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el marco del QR mantiene fondo claro también con el tema oscuro activo', async () => {
    document.documentElement.removeAttribute('data-theme');
    const getMyTicket = vi
      .fn()
      .mockResolvedValue({ status: 'confirmed', full_name: 'Persona de Prueba', has_qr: true });
    const myTicketQrUrl = vi
      .fn()
      .mockReturnValue('/api/v1/public/registrations/my-ticket/qr?token=abc');
    configurar({ getMyTicket, myTicketQrUrl }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(MyTicketPage);
    await fixture.whenStable();

    const marco = fixture.nativeElement.querySelector('.marco-qr') as HTMLElement;
    expect(marco).not.toBeNull();
    expect(getComputedStyle(marco).backgroundColor).toBe('rgb(255, 255, 255)');
  });
});
