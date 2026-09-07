import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import { ConfirmEmailChangePage } from './confirm-email-change-page';
import { AuthService } from '../../../core/auth/auth.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

describe('ConfirmEmailChangePage', () => {
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
      ],
    }).compileComponents();
  }

  it('sin token en la URL muestra el error y no tiene violaciones de accesibilidad', async () => {
    configurar({}, rutaConToken(null));

    const fixture = TestBed.createComponent(ConfirmEmailChangePage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Pide un nuevo cambio de correo');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token válido lo confirma y muestra el éxito', async () => {
    const confirmChangeEmail = vi.fn().mockResolvedValue(undefined);
    configurar({ confirmChangeEmail }, rutaConToken('token-valido'));

    const fixture = TestBed.createComponent(ConfirmEmailChangePage);
    await fixture.whenStable();

    expect(confirmChangeEmail).toHaveBeenCalledWith('token-valido');
    expect(fixture.nativeElement.textContent).toContain('Correo actualizado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('un token caducado muestra el error', async () => {
    const confirmChangeEmail = vi.fn().mockRejectedValue(new Error('caducado'));
    configurar({ confirmChangeEmail }, rutaConToken('token-caducado'));

    const fixture = TestBed.createComponent(ConfirmEmailChangePage);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Pide un nuevo cambio de correo');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
