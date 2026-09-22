import { PLATFORM_ID, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiService } from '../api/api.service';
import { AuthService } from './auth.service';
import { superadminGuard } from './superadmin.guard';

interface AuthServiceFalso {
  currentUser: () => { is_superadmin: boolean; platform_role?: string | null } | null;
  loadCurrentUser?: () => Promise<{ is_superadmin: boolean; platform_role?: string | null }>;
  refresh?: () => Promise<boolean>;
}

describe('superadminGuard', () => {
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
      superadminGuard({} as never, { url: '/admin/ia' } as never),
    ) as Promise<boolean | UrlTree>;
  }

  beforeEach(() => {
    auth = { currentUser: () => null };
  });

  it('en SSR deniega, igual que el guard del panel que lo envuelve', async () => {
    configurar(true);
    expect(TestBed.inject(ApiService).isServer).toBe(true);
    expect(await ejecutar()).toBe(false);
  });

  it('permite el acceso a un superadmin', async () => {
    auth.currentUser = vi.fn().mockReturnValue({ is_superadmin: true });
    configurar(false);
    expect(await ejecutar()).toBe(true);
  });

  it('a `soporte` lo devuelve a /admin: la pantalla guarda una credencial', async () => {
    auth.currentUser = vi.fn().mockReturnValue({ is_superadmin: false, platform_role: 'soporte' });
    configurar(false);
    const resultado = await ejecutar();
    expect(resultado).not.toBe(true);
    expect((resultado as UrlTree).toString()).toBe(router.createUrlTree(['/admin']).toString());
  });

  it('a quien no es personal de plataforma lo devuelve a su panel', async () => {
    auth.currentUser = vi.fn().mockReturnValue({ is_superadmin: false });
    configurar(false);
    const resultado = await ejecutar();
    expect((resultado as UrlTree).toString()).toBe(router.createUrlTree(['/dashboard']).toString());
  });

  it('sin usuario en memoria renueva con la cookie antes de decidir', async () => {
    auth.currentUser = vi.fn().mockReturnValue(null);
    auth.refresh = vi.fn().mockResolvedValue(true);
    auth.loadCurrentUser = vi.fn().mockResolvedValue({ is_superadmin: true });
    configurar(false);
    expect(await ejecutar()).toBe(true);
    expect(auth.refresh).toHaveBeenCalled();
  });

  it('sin sesión que renovar, redirige a /acceder', async () => {
    auth.currentUser = vi.fn().mockReturnValue(null);
    auth.refresh = vi.fn().mockResolvedValue(false);
    configurar(false);
    const resultado = await ejecutar();
    expect((resultado as UrlTree).toString()).toBe(router.createUrlTree(['/acceder']).toString());
  });
});
