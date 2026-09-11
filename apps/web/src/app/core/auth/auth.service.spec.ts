import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { AuthService } from './auth.service';

const IMPERSONATE = '/api/v1/admin/impersonate';
const STOP = '/api/v1/admin/impersonate/stop';

const USUARIO = {
  id: 'u-admin',
  email: 'admin@ejemplo.test',
  first_name: 'Admin',
  last_name: null,
  is_superadmin: true,
};

describe('AuthService: impersonación', () => {
  let servicio: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  async function iniciarSesion(): Promise<void> {
    const login = servicio.login('admin@ejemplo.test', 'secreta');
    http.expectOne('/api/v1/auth/login').flush({ access_token: 'token-admin', user: USUARIO });
    await login;
  }

  it('sin suplantación, el token efectivo es el del administrador', async () => {
    await iniciarSesion();
    expect(servicio.suplantando()).toBeNull();
    expect(servicio.tokenEfectivo()).toBe('token-admin');
  });

  it('al impersonar, el token efectivo pasa a ser el de la suplantación', async () => {
    await iniciarSesion();

    const entrada = servicio.impersonar({
      userId: 'u-1',
      organizationId: 'o-1',
      reason: 'Reproducir una incidencia',
      password: 'secreta',
      nombreVisible: 'Ana',
    });
    const peticion = http.expectOne(IMPERSONATE);
    expect(peticion.request.body).toMatchObject({
      user_id: 'u-1',
      organization_id: 'o-1',
      reason: 'Reproducir una incidencia',
    });
    peticion.flush({ access_token: 'token-suplantacion' });
    await entrada;

    expect(servicio.suplantando()?.nombre).toBe('Ana');
    expect(servicio.tokenEfectivo()).toBe('token-suplantacion');
    // El token del administrador se conserva intacto para poder volver a él.
    expect(servicio.accessToken()).toBe('token-admin');
  });

  it('al salir, se revoca en el servidor y se vuelve al token del administrador', async () => {
    await iniciarSesion();
    const entrada = servicio.impersonar({
      userId: 'u-1',
      organizationId: 'o-1',
      reason: 'Reproducir',
      password: 'secreta',
      nombreVisible: 'Ana',
    });
    http.expectOne(IMPERSONATE).flush({ access_token: 'token-suplantacion' });
    await entrada;

    const salida = servicio.salirDeImpersonacion();
    const peticion = http.expectOne(STOP);
    expect(peticion.request.method).toBe('POST');
    peticion.flush(null);
    await salida;

    expect(servicio.suplantando()).toBeNull();
    expect(servicio.tokenEfectivo()).toBe('token-admin');
  });

  it('cerrar sesión limpia también la suplantación', async () => {
    await iniciarSesion();
    const entrada = servicio.impersonar({
      userId: 'u-1',
      organizationId: 'o-1',
      reason: 'Reproducir',
      password: 'secreta',
      nombreVisible: 'Ana',
    });
    http.expectOne(IMPERSONATE).flush({ access_token: 'token-suplantacion' });
    await entrada;

    const cierre = servicio.logout();
    http.expectOne('/api/v1/auth/logout').flush(null);
    await cierre;

    expect(servicio.suplantando()).toBeNull();
    expect(servicio.accessToken()).toBeNull();
  });
});
