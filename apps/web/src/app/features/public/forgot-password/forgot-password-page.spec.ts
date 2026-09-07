import { Component, provideZonelessChangeDetection, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ForgotPasswordPage } from './forgot-password-page';
import { AuthService } from '../../../core/auth/auth.service';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

@Component({ selector: 'app-turnstile-widget', template: '' })
class TurnstileWidgetFalso {
  readonly resuelto = output<string>();
}

describe('ForgotPasswordPage', () => {
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
        {
          provide: AuthService,
          useValue: { forgotPassword: vi.fn().mockResolvedValue(undefined) },
        },
      ],
    })
      .overrideComponent(ForgotPasswordPage, {
        remove: { imports: [TurnstileWidget] },
        add: { imports: [TurnstileWidgetFalso] },
      })
      .compileComponents();
  });

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige un correo válido y no envía la solicitud si falta', async () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(auth.forgotPassword).not.toHaveBeenCalled();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un correo válido pide la recuperación y muestra el mismo mensaje siempre', async () => {
    const fixture = TestBed.createComponent(ForgotPasswordPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    const campoEmail = fixture.nativeElement.querySelector(
      'input[type="email"]',
    ) as HTMLInputElement;
    campoEmail.value = 'valido@example.com';
    campoEmail.dispatchEvent(new Event('input'));

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(auth.forgotPassword).toHaveBeenCalledWith('valido@example.com', '');
    expect(fixture.nativeElement.textContent).toContain('Revisa tu correo');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
