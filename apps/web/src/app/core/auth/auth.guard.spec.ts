import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ActivatedRouteSnapshot, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiService } from '../api/api.service';
import { AuthService } from './auth.service';
import { authGuard } from './auth.guard';

/** Ejecuta el guard dentro del contexto de inyección del TestBed. */
function ejecutarGuard(url = '/admin') {
  const estado = { url } as RouterStateSnapshot;
  const ruta = {} as ActivatedRouteSnapshot;
  return TestBed.runInInjectionContext(() => authGuard(ruta, estado));
}

describe('authGuard', () => {
  let auth: { isAuthenticated: ReturnType<typeof vi.fn>; refresh: ReturnType<typeof vi.fn> };
  let api: { isServer: boolean };

  beforeEach(() => {
    auth = { isAuthenticated: vi.fn().mockReturnValue(false), refresh: vi.fn() };
    api = { isServer: false };

    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: AuthService, useValue: auth },
        { provide: ApiService, useValue: api },
      ],
    });
  });

  it('deja pasar si ya hay sesión en memoria', async () => {
    auth.isAuthenticated.mockReturnValue(true);

    await expect(ejecutarGuard()).resolves.toBe(true);
    expect(auth.refresh).not.toHaveBeenCalled();
  });

  it('intenta renovar con la cookie antes de rechazar', async () => {
    auth.refresh.mockResolvedValue(true);

    await expect(ejecutarGuard()).resolves.toBe(true);
    expect(auth.refresh).toHaveBeenCalledTimes(1);
  });

  it('redirige al login conservando el destino', async () => {
    auth.refresh.mockResolvedValue(false);

    const resultado = await ejecutarGuard('/admin/branding');

    expect(resultado).toBeInstanceOf(UrlTree);
    expect((resultado as UrlTree).toString()).toContain('/admin/login');
    expect((resultado as UrlTree).toString()).toContain('redirigir');
  });

  it('nunca autoriza durante el renderizado en servidor', async () => {
    api.isServer = true;
    auth.isAuthenticated.mockReturnValue(true);

    await expect(ejecutarGuard()).resolves.toBe(false);
  });
});
