import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import {
  ActivatedRouteSnapshot,
  RouterStateSnapshot,
  UrlTree,
  convertToParamMap,
  provideRouter,
} from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiService } from '../api/api.service';
import { AuthService } from './auth.service';
import { guestGuard } from './guest.guard';

/** Ejecuta el guard dentro del contexto de inyección del TestBed. */
function ejecutarGuard(redirigir?: string) {
  const ruta = {
    queryParamMap: convertToParamMap(redirigir ? { redirigir } : {}),
  } as ActivatedRouteSnapshot;
  const estado = {} as RouterStateSnapshot;
  return TestBed.runInInjectionContext(() => guestGuard(ruta, estado));
}

describe('guestGuard', () => {
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

  it('deja ver el formulario si no hay sesión', async () => {
    auth.refresh.mockResolvedValue(false);

    await expect(ejecutarGuard()).resolves.toBe(true);
  });

  it('con sesión ya en memoria, redirige a /dashboard sin intentar renovar', async () => {
    auth.isAuthenticated.mockReturnValue(true);

    const resultado = await ejecutarGuard();

    expect(auth.refresh).not.toHaveBeenCalled();
    expect(resultado).toBeInstanceOf(UrlTree);
    expect((resultado as UrlTree).toString()).toBe('/dashboard');
  });

  it('sin token en memoria, renueva con la cookie antes de decidir', async () => {
    auth.refresh.mockResolvedValue(true);

    const resultado = await ejecutarGuard();

    expect(auth.refresh).toHaveBeenCalledTimes(1);
    expect((resultado as UrlTree).toString()).toBe('/dashboard');
  });

  it('con sesión renovada, respeta un `redirigir` explícito en vez de /dashboard', async () => {
    auth.isAuthenticated.mockReturnValue(true);

    const resultado = await ejecutarGuard('/admin/estilo');

    expect((resultado as UrlTree).toString()).toBe('/admin/estilo');
  });

  it('nunca redirige durante el renderizado en servidor', async () => {
    api.isServer = true;
    auth.isAuthenticated.mockReturnValue(true);

    await expect(ejecutarGuard()).resolves.toBe(true);
    expect(auth.refresh).not.toHaveBeenCalled();
  });
});
