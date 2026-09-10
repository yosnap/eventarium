import { Component, provideZonelessChangeDetection, output, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { VerifyEmailPage } from './verify-email-page';
import { AuthService } from '../../../core/auth/auth.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
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

@Component({ selector: 'app-turnstile-widget', template: '' })
class TurnstileWidgetFalso {
  readonly resuelto = output<string>();
}

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

describe('VerifyEmailPage', () => {
  function configurar(auth: Partial<AuthService>, ruta: unknown) {
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
        { provide: AuthService, useValue: auth },
        { provide: ActivatedRoute, useValue: ruta },
        { provide: ThemingService, useValue: themingDePrueba() },
      ],
    })
      .overrideComponent(VerifyEmailPage, {
        remove: { imports: [TurnstileWidget] },
        add: { imports: [TurnstileWidgetFalso] },
      })
      .compileComponents();
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('sin token en la URL muestra el error y no tiene violaciones de accesibilidad', async () => {
    configurar({ verifyEmail: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(VerifyEmailPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('sin token en la URL muestra el error en tema claro sin violaciones', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    configurar({ verifyEmail: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(VerifyEmailPage);
    await fixture.whenStable();

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token válido lo consume y muestra el éxito', async () => {
    const verifyEmail = vi.fn().mockResolvedValue(undefined);
    configurar({ verifyEmail }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(VerifyEmailPage);
    await fixture.whenStable();

    expect(verifyEmail).toHaveBeenCalledWith('token-valido');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token caducado ofrece el formulario de reenvío', async () => {
    const verifyEmail = vi.fn().mockRejectedValue(new Error('caducado'));
    configurar({ verifyEmail, resendVerification: vi.fn() }, rutaConToken('token-caducado'));

    const fixture = TestBed.createComponent(VerifyEmailPage);
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('no es válido o ha caducado');
    expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
