import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import { ResetPasswordPage } from './reset-password-page';
import { AuthService } from '../../../core/auth/auth.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

describe('ResetPasswordPage', () => {
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
        { provide: AuthService, useValue: auth },
        { provide: ActivatedRoute, useValue: ruta },
      ],
    }).compileComponents();
  }

  it('sin token en la URL muestra el error de enlace no válido', async () => {
    configurar({}, rutaConToken(null));

    const fixture = TestBed.createComponent(ResetPasswordPage);
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con una contraseña sin complejidad no envía la solicitud', async () => {
    const resetPassword = vi.fn();
    configurar({ resetPassword }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(ResetPasswordPage);
    await fixture.whenStable();

    const campoPassword = fixture.nativeElement.querySelector(
      'input[type="password"]',
    ) as HTMLInputElement;
    campoPassword.value = 'sin-complejidad';
    campoPassword.dispatchEvent(new Event('input'));

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(resetPassword).not.toHaveBeenCalled();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con una contraseña válida completa la recuperación', async () => {
    const resetPassword = vi.fn().mockResolvedValue(undefined);
    configurar({ resetPassword }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(ResetPasswordPage);
    await fixture.whenStable();

    const campoPassword = fixture.nativeElement.querySelector(
      'input[type="password"]',
    ) as HTMLInputElement;
    campoPassword.value = 'Una-Contraseña-Fuerte-1!';
    campoPassword.dispatchEvent(new Event('input'));

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(resetPassword).toHaveBeenCalledWith('token-valido', 'Una-Contraseña-Fuerte-1!');
    expect(fixture.nativeElement.textContent).toContain('Contraseña actualizada');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('un token caducado o ya usado muestra el error, no un mensaje genérico', async () => {
    const resetPassword = vi.fn().mockRejectedValue(new ApiError(422, 'no válido', null));
    configurar({ resetPassword }, rutaConToken('token-caducado'));

    const fixture = TestBed.createComponent(ResetPasswordPage);
    await fixture.whenStable();

    const campoPassword = fixture.nativeElement.querySelector(
      'input[type="password"]',
    ) as HTMLInputElement;
    campoPassword.value = 'Una-Contraseña-Fuerte-1!';
    campoPassword.dispatchEvent(new Event('input'));

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('no es válido o ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
