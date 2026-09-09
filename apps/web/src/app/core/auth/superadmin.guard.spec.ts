import { PLATFORM_ID, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { superadminGuard } from './superadmin.guard';
import { AuthService } from './auth.service';
import { ApiService } from '../api/api.service';

interface AuthServiceFalso {
  currentUser: () => { is_superadmin: boolean } | null;
  loadCurrentUser?: () => Promise<{ is_superadmin: boolean }>;
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
      superadminGuard({} as never, { url: '/admin/superadmin' } as never),
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

  it('deniega a un autenticado sin is_superadmin y redirige a /admin', async () => {
    auth.currentUser = vi.fn().mockReturnValue({ is_superadmin: false });
    configurar(false);
    const resultado = await ejecutar();
    expect(resultado).not.toBe(true);
    expect((resultado as UrlTree).toString()).toBe(router.createUrlTree(['/admin']).toString());
  });

  it('sin usuario en memoria, lo recarga antes de decidir', async () => {
    auth.currentUser = vi.fn().mockReturnValue(null);
    auth.loadCurrentUser = vi.fn().mockResolvedValue({ is_superadmin: true });
    configurar(false);
    expect(await ejecutar()).toBe(true);
    expect(auth.loadCurrentUser).toHaveBeenCalled();
  });

  it('si recargar el usuario falla, redirige a /admin/login', async () => {
    auth.currentUser = vi.fn().mockReturnValue(null);
    auth.loadCurrentUser = vi.fn().mockRejectedValue(new Error('sin sesión'));
    configurar(false);
    const resultado = await ejecutar();
    expect((resultado as UrlTree).toString()).toBe(
      router.createUrlTree(['/admin/login']).toString(),
    );
  });
});
