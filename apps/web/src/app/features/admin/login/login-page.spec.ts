import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '../../../core/auth/auth.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { themingDePrueba } from '../../../../testing/theming.fixture';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { LoginPage } from './login-page';

function rutaConRedirigir(destino: string | null) {
  return {
    snapshot: { queryParamMap: convertToParamMap(destino ? { redirigir: destino } : {}) },
  };
}

describe('LoginPage', () => {
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
        // `AuthFrame` inyecta el `ThemingService` real, que necesita `HttpClient`.
        { provide: ThemingService, useValue: themingDePrueba() },
      ],
    }).compileComponents();
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  async function entrarYVerDestino(
    destino: string | null,
    auth: Partial<AuthService> = {},
  ): Promise<string> {
    const login = vi.fn().mockResolvedValue(undefined);
    configurar(
      {
        login,
        listMyOrganizations: vi.fn().mockResolvedValue([]),
        currentUser: () => null,
        ...auth,
      } as unknown as Partial<AuthService>,
      rutaConRedirigir(destino),
    );
    const router = TestBed.inject(Router);
    const navegar = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    const email = fixture.nativeElement.querySelector('input[type="email"]') as HTMLInputElement;
    email.value = 'persona@example.com';
    email.dispatchEvent(new Event('input'));
    const password = fixture.nativeElement.querySelector(
      'input[type="password"]',
    ) as HTMLInputElement;
    password.value = 'secreta';
    password.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    return navegar.mock.calls[0]?.[0] as string;
  }

  it('con 1 organización y sin rol de plataforma, entra al escritorio de la organización', async () => {
    // `/admin` es la plataforma y exige `personalPlataformaGuard`; mandar ahí a
    // un organizador que acaba de entrar sería un fallo de autorización.
    expect(
      await entrarYVerDestino(null, {
        listMyOrganizations: vi.fn().mockResolvedValue([
          { organization_id: 'o1', slug: 'acme', name: 'Acme', role_name: 'Propietario' },
        ]),
      }),
    ).toBe('/dashboard');
  });

  it('respeta el destino pedido en `redirigir` cuando solo hay 1 espacio', async () => {
    expect(
      await entrarYVerDestino('/dashboard/events/e1', {
        listMyOrganizations: vi.fn().mockResolvedValue([
          { organization_id: 'o1', slug: 'acme', name: 'Acme', role_name: 'Propietario' },
        ]),
      }),
    ).toBe('/dashboard/events/e1');
  });

  it('admin de plataforma sin organizaciones entra directo a /admin', async () => {
    expect(
      await entrarYVerDestino(null, {
        currentUser: (() => ({ is_superadmin: true })) as unknown as AuthService['currentUser'],
      }),
    ).toBe('/admin');
  });

  it('con 2+ espacios (organizaciones + plataforma), navega al selector', async () => {
    expect(
      await entrarYVerDestino(null, {
        listMyOrganizations: vi.fn().mockResolvedValue([
          { organization_id: 'o1', slug: 'acme', name: 'Acme', role_name: 'Propietario' },
        ]),
        currentUser: (() => ({ is_superadmin: true })) as unknown as AuthService['currentUser'],
      }),
    ).toBe('/espacio-de-trabajo');
  });

  it('con 2+ organizaciones (sin rol de plataforma), navega al selector', async () => {
    expect(
      await entrarYVerDestino(null, {
        listMyOrganizations: vi.fn().mockResolvedValue([
          { organization_id: 'o1', slug: 'acme', name: 'Acme', role_name: 'Propietario' },
          { organization_id: 'o2', slug: 'otra', name: 'Otra', role_name: 'Editor' },
        ]),
      }),
    ).toBe('/espacio-de-trabajo');
  });

  it('un fallo al contar espacios tras un login válido no aborta el login: degrada al destino por defecto', async () => {
    expect(
      await entrarYVerDestino(null, {
        listMyOrganizations: vi.fn().mockRejectedValue(new Error('red caída')),
      }),
    ).toBe('/dashboard');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    configurar({} as unknown as Partial<AuthService>, rutaConRedirigir(null));
    const fixture = TestBed.createComponent(LoginPage);
    await fixture.whenStable();

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
