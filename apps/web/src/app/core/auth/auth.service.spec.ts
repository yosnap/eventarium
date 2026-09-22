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
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
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

describe('AuthService: refresh()', () => {
  let servicio: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    servicio = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  async function iniciarSesion(): Promise<void> {
    const login = servicio.login('admin@ejemplo.test', 'secreta');
    http.expectOne('/api/v1/auth/login').flush({ access_token: 'token-viejo', user: USUARIO });
    await login;
  }

  it('un 401/403 del propio /auth/refresh limpia la sesión (cookie de refresco caducada o revocada)', async () => {
    await iniciarSesion();

    const renovar = servicio.refresh();
    http
      .expectOne('/api/v1/auth/refresh')
      .flush({ detail: 'Refresh token inválido.' }, { status: 401, statusText: 'Unauthorized' });
    const ok = await renovar;

    expect(ok).toBe(false);
    expect(servicio.isAuthenticated()).toBe(false);
    expect(servicio.accessToken()).toBeNull();
  });

  it('un fallo de red (no un rechazo del servidor) NO limpia la sesión — es transitorio, no "sesión muerta"', async () => {
    await iniciarSesion();

    const renovar = servicio.refresh();
    // `status: 0` es como Angular reporta que la petición ni siquiera llegó
    // (red caída, CORS, servidor caído a mitad de despliegue) — a
    // diferencia de un 401/403, el servidor no ha dicho nada sobre la
    // sesión.
    http.expectOne('/api/v1/auth/refresh').error(new ProgressEvent('error'), { status: 0 });
    const ok = await renovar;

    expect(ok).toBe(false);
    // El token viejo se queda tal cual — limpiarlo aquí expulsaría del
    // panel (y tiraría cualquier formulario a medias) por un problema de
    // red pasajero, no por una sesión realmente caducada.
    expect(servicio.isAuthenticated()).toBe(true);
    expect(servicio.accessToken()).toBe('token-viejo');
  });
});

describe('AuthService: organización sin dominio', () => {
  let servicio: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    servicio = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  it('switchOrganization manda la organización de destino y actualiza el token', async () => {
    const login = servicio.login('admin@ejemplo.test', 'secreta');
    http.expectOne('/api/v1/auth/login').flush({ access_token: 'token-org-1', user: USUARIO });
    await login;

    const cambio = servicio.switchOrganization('org-2');
    const peticion = http.expectOne('/api/v1/auth/switch-organization');
    expect(peticion.request.body).toEqual({ organization_id: 'org-2' });
    expect(peticion.request.withCredentials).toBe(true);
    peticion.flush({ access_token: 'token-org-2', expires_in: 900 });
    await cambio;

    expect(servicio.accessToken()).toBe('token-org-2');
  });

  it('createOrganization activa la sesión con el token de la propia respuesta', async () => {
    const login = servicio.login('admin@ejemplo.test', 'secreta');
    http.expectOne('/api/v1/auth/login').flush({ access_token: 'token-previo', user: USUARIO });
    await login;

    const creacion = servicio.createOrganization({
      name: 'Nueva',
      slug: 'nueva',
      firstName: 'A',
      lastName: 'B',
      turnstileToken: 'turnstile',
    });
    const peticion = http.expectOne('/api/v1/organizations');
    expect(peticion.request.withCredentials).toBe(true);
    peticion.flush({
      id: 'org-nueva',
      slug: 'nueva',
      host: 'nueva.example',
      access_token: 'token-org-nueva',
      expires_in: 900,
    });
    await creacion;

    expect(servicio.accessToken()).toBe('token-org-nueva');
  });
});
