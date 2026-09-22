import { Component, provideZonelessChangeDetection, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MisEventosSolicitarPage } from './mis-eventos-solicitar-page';
import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

/** Mismo doble que `forgot-password-page.spec.ts`: sin él, el widget real
 * intentaría cargar el script de Turnstile. */
@Component({ selector: 'app-turnstile-widget', template: '' })
class TurnstileWidgetFalso {
  readonly resuelto = output<string>();
}

describe('MisEventosSolicitarPage', () => {
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
          provide: RegistrationsService,
          useValue: {
            requestMisEventosAccess: vi.fn().mockResolvedValue({ message: 'ok' }),
          },
        },
      ],
    })
      .overrideComponent(MisEventosSolicitarPage, {
        remove: { imports: [TurnstileWidget] },
        add: { imports: [TurnstileWidgetFalso] },
      })
      .compileComponents();
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(MisEventosSolicitarPage);
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige un correo válido y no envía la solicitud si falta', async () => {
    const fixture = TestBed.createComponent(MisEventosSolicitarPage);
    await fixture.whenStable();
    const registrations = TestBed.inject(RegistrationsService);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(registrations.requestMisEventosAccess).not.toHaveBeenCalled();
  });

  it('con un correo válido pide el enlace y muestra el mismo mensaje siempre', async () => {
    const fixture = TestBed.createComponent(MisEventosSolicitarPage);
    await fixture.whenStable();
    const registrations = TestBed.inject(RegistrationsService);

    const campoEmail = fixture.nativeElement.querySelector(
      'input[type="email"]',
    ) as HTMLInputElement;
    campoEmail.value = 'valido@example.com';
    campoEmail.dispatchEvent(new Event('input'));

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(registrations.requestMisEventosAccess).toHaveBeenCalledWith('valido@example.com', '');
    expect(fixture.nativeElement.textContent).toContain('Revisa tu correo');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
