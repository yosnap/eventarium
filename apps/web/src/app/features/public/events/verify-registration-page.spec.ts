import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import { VerifyRegistrationPage } from './verify-registration-page';
import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

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
        { provide: RegistrationsService, useValue: registrations },
        { provide: ActivatedRoute, useValue: ruta },
      ],
    }).compileComponents();
  }

  it('sin token en la URL muestra el error y no tiene violaciones de accesibilidad', async () => {
    configurar({ verify: vi.fn() }, rutaConToken(null));

    const fixture = TestBed.createComponent(VerifyRegistrationPage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('no es válido o ha caducado');
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
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
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
