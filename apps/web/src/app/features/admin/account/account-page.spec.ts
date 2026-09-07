import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AccountPage } from './account-page';
import { AuthService, UsuarioAutenticado } from '../../../core/auth/auth.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const USUARIO: UsuarioAutenticado = {
  id: 'u1',
  email: 'propietaria@example.com',
  first_name: 'Ana',
  last_name: 'Propietaria',
  is_superadmin: false,
};

function authFalso(overrides: Partial<AuthService> = {}): Partial<AuthService> {
  return {
    currentUser: (() => USUARIO) as AuthService['currentUser'],
    loadCurrentUser: vi.fn().mockResolvedValue(USUARIO),
    listSocialLinks: vi.fn().mockResolvedValue([]),
    upsertSocialLink: vi.fn().mockResolvedValue({ kind: 'twitter', url: 'https://x.com/a' }),
    deleteSocialLink: vi.fn().mockResolvedValue(undefined),
    updateMe: vi.fn().mockResolvedValue(undefined),
    changeEmail: vi.fn().mockResolvedValue(undefined),
    changePassword: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe('AccountPage', () => {
  function configurar(auth: Partial<AuthService>) {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection(), { provide: AuthService, useValue: auth }],
    }).compileComponents();
  }

  beforeEach(() => {
    configurar(authFalso());
  });

  it('no tiene violaciones de accesibilidad y precarga el perfil', async () => {
    const fixture = TestBed.createComponent(AccountPage);
    await fixture.whenStable();

    const campoNombre = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(campoNombre.value).toBe('Ana');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('guardar el perfil llama a updateMe con nombre y apellidos', async () => {
    const fixture = TestBed.createComponent(AccountPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    const formularioPerfil = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    formularioPerfil.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(auth.updateMe).toHaveBeenCalledWith({ firstName: 'Ana', lastName: 'Propietaria' });
    expect(fixture.nativeElement.textContent).toContain('Perfil actualizado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('solicitar el cambio de correo exige contraseña actual', async () => {
    const fixture = TestBed.createComponent(AccountPage);
    await fixture.whenStable();
    const auth = TestBed.inject(AuthService);

    const formularios = fixture.nativeElement.querySelectorAll('form');
    const formularioCorreo = formularios[1] as HTMLFormElement;
    const campoCorreo = formularioCorreo.querySelector('input[type="email"]') as HTMLInputElement;
    campoCorreo.value = 'nuevo@example.com';
    campoCorreo.dispatchEvent(new Event('input'));

    formularioCorreo.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(auth.changeEmail).not.toHaveBeenCalled();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('un error al cambiar la contraseña se muestra sin romper el resto de la página', async () => {
    configurar(
      authFalso({
        changePassword: vi.fn().mockRejectedValue(new ApiError(401, 'no válida', null)),
      }),
    );
    const fixture = TestBed.createComponent(AccountPage);
    await fixture.whenStable();

    const formularios = fixture.nativeElement.querySelectorAll('form');
    const formularioContrasena = formularios[2] as HTMLFormElement;
    const [actual, nueva] = Array.from(
      formularioContrasena.querySelectorAll('input[type="password"]'),
    ) as HTMLInputElement[];
    actual.value = 'mala';
    actual.dispatchEvent(new Event('input'));
    nueva.value = 'Una-Contraseña-Fuerte-1!';
    nueva.dispatchEvent(new Event('input'));

    formularioContrasena.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('no válida');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
