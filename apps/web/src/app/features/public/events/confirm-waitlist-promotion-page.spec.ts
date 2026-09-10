import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ConfirmWaitlistPromotionPage } from './confirm-waitlist-promotion-page';
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

describe('ConfirmWaitlistPromotionPage', () => {
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

  it('sin token en la URL muestra el error y no tiene violaciones de accesibilidad', async () => {
    configurar({ confirmWaitlistPromotion: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(ConfirmWaitlistPromotionPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('sin token en la URL muestra el error en tema claro sin violaciones', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    configurar({ confirmWaitlistPromotion: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(ConfirmWaitlistPromotionPage);
    await fixture.whenStable();

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token válido lo consume y muestra el mensaje de la API', async () => {
    const confirmWaitlistPromotion = vi
      .fn()
      .mockResolvedValue({ message: 'Tu plaza está confirmada.' });
    configurar({ confirmWaitlistPromotion }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(ConfirmWaitlistPromotionPage);
    await fixture.whenStable();

    expect(confirmWaitlistPromotion).toHaveBeenCalledWith('token-valido');
    expect(fixture.nativeElement.textContent).toContain('Tu plaza está confirmada.');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token caducado muestra el error genérico', async () => {
    const confirmWaitlistPromotion = vi.fn().mockRejectedValue(new Error('caducado'));
    configurar({ confirmWaitlistPromotion }, rutaConToken('token-caducado'));

    const fixture = TestBed.createComponent(ConfirmWaitlistPromotionPage);
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
