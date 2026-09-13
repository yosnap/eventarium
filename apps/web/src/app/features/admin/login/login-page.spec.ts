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

  async function entrarYVerDestino(destino: string | null): Promise<string> {
    const login = vi.fn().mockResolvedValue(undefined);
    configurar({ login } as unknown as Partial<AuthService>, rutaConRedirigir(destino));
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

  it('sin destino explícito entra al escritorio de la organización, no a la plataforma', async () => {
    // `/admin` es la plataforma y exige `superadminGuard`; mandar ahí a un
    // organizador que acaba de entrar sería un fallo de autorización.
    expect(await entrarYVerDestino(null)).toBe('/dashboard');
  });

  it('respeta el destino pedido en `redirigir`', async () => {
    expect(await entrarYVerDestino('/dashboard/events/e1')).toBe('/dashboard/events/e1');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    configurar({} as unknown as Partial<AuthService>, rutaConRedirigir(null));
    const fixture = TestBed.createComponent(LoginPage);
    await fixture.whenStable();

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
