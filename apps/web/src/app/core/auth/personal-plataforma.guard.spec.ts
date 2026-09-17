import { PLATFORM_ID, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { personalPlataformaGuard } from './personal-plataforma.guard';
import { AuthService } from './auth.service';
import { ApiService } from '../api/api.service';

interface AuthServiceFalso {
  currentUser: () => { is_superadmin: boolean; platform_role?: string | null } | null;
  loadCurrentUser?: () => Promise<{ is_superadmin: boolean; platform_role?: string | null }>;
  refresh?: () => Promise<boolean>;
}

describe('personalPlataformaGuard', () => {
  let auth: AuthServiceFalso;
  let router: Router;

  function configurar(isServer: boolean): void {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: PLATFORM_ID, useValue: isServer ? 'server' : 'browser' },
        { provide: AuthService, useValue: auth },
      ],
    });
    router = TestBed.inject(Router);
  }

  async function ejecutar(): Promise<boolean | UrlTree> {
    return TestBed.runInInjectionContext(() =>
      personalPlataformaGuard({} as never, { url: '/admin' } as never),
    ) as Promise<boolean | UrlTree>;
  }

  beforeEach(() => {
    auth = { currentUser: () => null };
  });

  it('en SSR, deniega (authGuard ya lo hace en el padre; este no debe romperlo)', async () => {
    configurar(true);
    const api = TestBed.inject(ApiService);
    expect(api.isServer).toBe(true);
    expect(await ejecutar()).toBe(false);
  });

  it('permite el acceso a un superadmin ya cargado en memoria', async () => {
    auth.currentUser = vi.fn().mockReturnValue({ is_superadmin: true });
    configurar(false);
    expect(await ejecutar()).toBe(true);
  });

  it('permite el acceso a `soporte` (rol aditivo de plataforma, solo lectura)', async () => {
    // Fase 3 del plan de cookies: la pantalla de analítica externa se abre
    // también al personal de soporte; el guard de /admin lo admite igual que
    // `require_platform_staff` en el backend.
    auth.currentUser = vi.fn().mockReturnValue({ is_superadmin: false, platform_role: 'soporte' });
    configurar(false);
    expect(await ejecutar()).toBe(true);
  });

  it('deniega a un autenticado sin is_superadmin ni soporte y redirige a /dashboard', async () => {
    auth.currentUser = vi.fn().mockReturnValue({ is_superadmin: false });
    configurar(false);
    const resultado = await ejecutar();
    expect(resultado).not.toBe(true);
    expect((resultado as UrlTree).toString()).toBe(router.createUrlTree(['/dashboard']).toString());
  });

  it('sin usuario en memoria, renueva con la cookie y luego lo recarga antes de decidir', async () => {
    auth.currentUser = vi.fn().mockReturnValue(null);
    auth.refresh = vi.fn().mockResolvedValue(true);
    auth.loadCurrentUser = vi.fn().mockResolvedValue({ is_superadmin: true });
    configurar(false);
    expect(await ejecutar()).toBe(true);
    expect(auth.refresh).toHaveBeenCalled();
    expect(auth.loadCurrentUser).toHaveBeenCalled();
  });

  it('sin usuario en memoria y sin sesión que renovar, redirige a /acceder sin llamar a loadCurrentUser', async () => {
    auth.currentUser = vi.fn().mockReturnValue(null);
    auth.refresh = vi.fn().mockResolvedValue(false);
    auth.loadCurrentUser = vi.fn();
    configurar(false);
    const resultado = await ejecutar();
    expect((resultado as UrlTree).toString()).toBe(router.createUrlTree(['/acceder']).toString());
  });

  it('si recargar el usuario falla tras renovar la sesión, redirige a /acceder', async () => {
    auth.currentUser = vi.fn().mockReturnValue(null);
    auth.refresh = vi.fn().mockResolvedValue(true);
    auth.loadCurrentUser = vi.fn().mockRejectedValue(new Error('sin sesión'));
    configurar(false);
    const resultado = await ejecutar();
    expect((resultado as UrlTree).toString()).toBe(router.createUrlTree(['/acceder']).toString());
  });
});
