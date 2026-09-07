import { Component, provideZonelessChangeDetection, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RegisterPage } from './register-page';
import { AuthService } from '../../../core/auth/auth.service';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

/**
 * Sustituye el widget real: es un iframe de terceros que carga un script externo y no
 * tiene sentido probarlo aquí (se comprueba manualmente, ver `docs/accesibilidad.md`).
 */
@Component({ selector: 'app-turnstile-widget', template: '' })
class TurnstileWidgetFalso {
  readonly resuelto = output<string>();
}

describe('RegisterPage', () => {
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
        provideRouter([]),
        { provide: AuthService, useValue: { register: vi.fn().mockResolvedValue(undefined) } },
      ],
    })
      .overrideComponent(RegisterPage, {
        remove: { imports: [TurnstileWidget] },
        add: { imports: [TurnstileWidgetFalso] },
      })
      .compileComponents();
  });

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(RegisterPage);
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige correo y una contraseña de al menos 8 caracteres', async () => {
    const fixture = TestBed.createComponent(RegisterPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    const formulario = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    formulario.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(auth.register).not.toHaveBeenCalled();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('una contraseña sin complejidad muestra el indicador y bloquea el envío', async () => {
    const fixture = TestBed.createComponent(RegisterPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    const campoPassword = fixture.nativeElement.querySelector(
      'input[type="password"]',
    ) as HTMLInputElement;
    campoPassword.value = 'sin-mayuscula-ni-numero';
    campoPassword.dispatchEvent(new Event('input'));
    campoPassword.dispatchEvent(new Event('blur'));
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('app-password-strength ul')).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('mayúscula, minúscula');

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(auth.register).not.toHaveBeenCalled();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige que la repetición de la contraseña coincida', async () => {
    const fixture = TestBed.createComponent(RegisterPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    const [campoPassword, campoConfirmar] = Array.from(
      fixture.nativeElement.querySelectorAll('input[type="password"]'),
    ) as HTMLInputElement[];

    campoPassword.value = 'Una-Contraseña-Fuerte-1!';
    campoPassword.dispatchEvent(new Event('input'));
    campoConfirmar.value = 'Otra-Diferente-1!';
    campoConfirmar.dispatchEvent(new Event('input'));
    campoConfirmar.dispatchEvent(new Event('blur'));
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('no coinciden');

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(auth.register).not.toHaveBeenCalled();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con datos válidos y contraseñas iguales envía el registro', async () => {
    const fixture = TestBed.createComponent(RegisterPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    const campoEmail = fixture.nativeElement.querySelector(
      'input[type="email"]',
    ) as HTMLInputElement;
    campoEmail.value = 'valido@example.com';
    campoEmail.dispatchEvent(new Event('input'));

    const [campoPassword, campoConfirmar] = Array.from(
      fixture.nativeElement.querySelectorAll('input[type="password"]'),
    ) as HTMLInputElement[];
    campoPassword.value = 'Una-Contraseña-Fuerte-1!';
    campoPassword.dispatchEvent(new Event('input'));
    campoConfirmar.value = 'Una-Contraseña-Fuerte-1!';
    campoConfirmar.dispatchEvent(new Event('input'));

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(auth.register).toHaveBeenCalledWith(
      'valido@example.com',
      'Una-Contraseña-Fuerte-1!',
      '',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
