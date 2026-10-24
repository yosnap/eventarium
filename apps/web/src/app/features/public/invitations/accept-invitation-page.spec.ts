import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import { AcceptInvitationPage } from './accept-invitation-page';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { ThemingService } from '../../../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { themingDePrueba } from '../../../../testing/theming.fixture';

function rutaConToken(token: string | null) {
  return { snapshot: { queryParamMap: convertToParamMap(token ? { token } : {}) } };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('AcceptInvitationPage', () => {
  let http: HttpTestingController;

  function configurar(ruta: unknown) {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: ruta },
        { provide: ThemingService, useValue: themingDePrueba() },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  }

  afterEach(() => {
    http.verify();
    document.documentElement.removeAttribute('data-theme');
  });

  it('sin token en la URL muestra el error sin llamar a la API', async () => {
    configurar(rutaConToken(null));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Falta el enlace de la invitación');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con un token válido pide nombre, apellidos y contraseña', async () => {
    configurar(rutaConToken('token-valido'));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    http
      .expectOne('/api/v1/public/invitations/token-valido')
      .flush({ organization_name: 'Acme', role_name: 'Organizador', account_has_password: false });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Acme');
    expect(fixture.nativeElement.textContent).toContain('Organizador');
    expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('si la cuenta ya tiene contraseña ofrece entrar en vez del formulario', async () => {
    configurar(rutaConToken('token-con-cuenta'));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    http
      .expectOne('/api/v1/public/invitations/token-con-cuenta')
      .flush({ organization_name: 'Acme', role_name: 'Organizador', account_has_password: true });
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Ya tienes una cuenta');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('un token caducado muestra el mensaje que da la API', async () => {
    configurar(rutaConToken('token-caducado'));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    http.expectOne('/api/v1/public/invitations/token-caducado').flush(
      {
        title: 'Recurso no encontrado',
        detail: 'Esta invitación ha caducado. Pide que te envíen otra.',
      },
      { status: 404, statusText: 'Not Found' },
    );
    await avanzar(fixture);

    const zonaAnuncio = fixture.nativeElement.querySelector('[aria-live="assertive"]');
    expect(zonaAnuncio?.textContent).toContain('ha caducado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('aceptar con éxito muestra la pantalla de bienvenida', async () => {
    configurar(rutaConToken('token-valido'));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    http
      .expectOne('/api/v1/public/invitations/token-valido')
      .flush({ organization_name: 'Acme', role_name: 'Organizador', account_has_password: false });
    await avanzar(fixture);

    const nombre = fixture.nativeElement.querySelector('#invitacion-nombre') as HTMLInputElement;
    const apellidos = fixture.nativeElement.querySelector(
      '#invitacion-apellidos',
    ) as HTMLInputElement;
    const password = fixture.nativeElement.querySelector(
      '#invitacion-password',
    ) as HTMLInputElement;
    nombre.value = 'Ada';
    nombre.dispatchEvent(new Event('input'));
    apellidos.value = 'Lovelace';
    apellidos.dispatchEvent(new Event('input'));
    password.value = 'Acepta-Esta-Invitacion-1!';
    password.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    fixture.nativeElement.querySelector('form')!.dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http.expectOne('/api/v1/public/invitations/token-valido/accept').flush({
      organization_slug: 'acme',
    });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Ya formas parte del equipo');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  // Fase 3 (plan `261019-1343`), red-team #14: el token va `encodeURIComponent`-eado
  // en la URL de consulta — bug preexistente (path traversal del lado cliente),
  // corregido de paso porque esta fase ya toca la línea al añadir `locale`.
  it('la consulta manda el token URL-encoded, no en crudo', async () => {
    configurar(rutaConToken('con/slash&raro'));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    const peticion = http.expectOne(
      (req) => req.method === 'GET' && req.url.includes('/public/invitations/'),
    );
    expect(peticion.request.url).toBe(
      `/api/v1/public/invitations/${encodeURIComponent('con/slash&raro')}`,
    );
    peticion.flush({
      organization_name: 'Acme',
      role_name: 'Organizador',
      account_has_password: false,
    });
    await avanzar(fixture);
  });

  // Fase 3, red-team #14 (misma corrección) + requisito de `locale` en el body
  // del `accept`: el helper `localeDeCuenta()` manda siempre un valor del
  // catálogo compartido con el backend (hoy, con un solo idioma cargado,
  // siempre `'es-ES'`).
  it('aceptar manda locale en el body y el token URL-encoded en la URL', async () => {
    configurar(rutaConToken('con/slash&raro'));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    http
      .expectOne((req) => req.method === 'GET' && req.url.includes('/public/invitations/'))
      .flush({ organization_name: 'Acme', role_name: 'Organizador', account_has_password: false });
    await avanzar(fixture);

    const nombre = fixture.nativeElement.querySelector('#invitacion-nombre') as HTMLInputElement;
    const apellidos = fixture.nativeElement.querySelector(
      '#invitacion-apellidos',
    ) as HTMLInputElement;
    const password = fixture.nativeElement.querySelector(
      '#invitacion-password',
    ) as HTMLInputElement;
    nombre.value = 'Ada';
    nombre.dispatchEvent(new Event('input'));
    apellidos.value = 'Lovelace';
    apellidos.dispatchEvent(new Event('input'));
    password.value = 'Acepta-Esta-Invitacion-1!';
    password.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    fixture.nativeElement.querySelector('form')!.dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    const peticion = http.expectOne((req) => req.method === 'POST');
    expect(peticion.request.url).toBe(
      `/api/v1/public/invitations/${encodeURIComponent('con/slash&raro')}/accept`,
    );
    expect(peticion.request.body).toEqual({
      first_name: 'Ada',
      last_name: 'Lovelace',
      password: 'Acepta-Esta-Invitacion-1!',
      locale: 'es-ES',
    });
    peticion.flush({ organization_slug: 'acme' });
    await avanzar(fixture);
  });

  it('el formulario no tiene violaciones de accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    configurar(rutaConToken('token-valido'));
    const fixture = TestBed.createComponent(AcceptInvitationPage);
    await avanzar(fixture);

    http
      .expectOne('/api/v1/public/invitations/token-valido')
      .flush({ organization_name: 'Acme', role_name: 'Organizador', account_has_password: false });
    await avanzar(fixture);

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
