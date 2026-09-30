import { PLATFORM_ID, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { VerifyRegistrationPage } from './verify-registration-page';
import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { themingDePrueba } from '../../../../testing/theming.fixture';

/** Mismo doble mínimo que `layouts/shells.spec.ts`: sin él, `AuthFrame`
 * inyectaría el `ThemingService` real, que necesita `HttpClient`. */

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

const EVENTO = {
  organization: { slug: 'acme', name: 'Acme', page_public: false },
  slug: 'congreso',
  title: 'Congreso de IA',
  starts_at: '2026-10-01T07:00:00Z',
  ends_at: '2026-10-01T16:30:00Z',
  timezone: 'Europe/Madrid',
  location: 'Palacio de Congresos',
};

describe('VerifyRegistrationPage', () => {
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

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('en el servidor no consume el token y pinta el estado de comprobación', () => {
    const verify = vi.fn();
    configurar({ verify }, rutaConToken('token-de-un-solo-uso'));
    TestBed.overrideProvider(PLATFORM_ID, { useValue: 'server' });

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    fixture.detectChanges();

    expect(verify).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Comprobando el enlace');
    expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe(
      'noindex, nofollow',
    );
  });

  it('sin token en la URL muestra el error y no tiene violaciones de accesibilidad', async () => {
    configurar({ verify: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('sin token en la URL muestra el error en tema claro sin violaciones', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    configurar({ verify: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token válido lo consume y muestra el mensaje de la API', async () => {
    const verify = vi
      .fn()
      .mockResolvedValue({ message: 'Tu inscripción está confirmada.', status: 'confirmed' });
    configurar({ verify }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    expect(verify).toHaveBeenCalledWith('token-valido');
    expect(fixture.nativeElement.textContent).toContain('Tu inscripción está confirmada.');
    expect(fixture.nativeElement.textContent).toContain('Inscripción confirmada');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con estado pendiente de aprobación muestra el chip correspondiente', async () => {
    const verify = vi.fn().mockResolvedValue({
      message: 'Tu inscripción está pendiente de aprobación.',
      status: 'pending_approval',
    });
    configurar({ verify }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Pendiente de aprobación');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con la plaza confirmada ofrece añadir el evento al calendario, fuera del aria-live', async () => {
    const verify = vi.fn().mockResolvedValue({
      message: 'Tu inscripción está confirmada.',
      status: 'confirmed',
      event: EVENTO,
    });
    configurar({ verify }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Google Calendar');
    expect(texto).toContain('Outlook');
    expect(texto).toContain('Apple Calendar');
    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).not.toContain('Google Calendar');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('pendiente de aprobación no propone el calendario: la plaza aún no es segura', async () => {
    const verify = vi.fn().mockResolvedValue({
      message: 'Tu inscripción está pendiente de aprobación.',
      status: 'pending_approval',
      event: null,
    });
    configurar({ verify }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('app-add-to-calendar')).toBeNull();
  });

  it('con un token caducado muestra el error genérico', async () => {
    const verify = vi.fn().mockRejectedValue(new Error('caducado'));
    configurar({ verify }, rutaConToken('token-caducado'));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
