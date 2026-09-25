import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { EmailSettingsOut } from '../../../core/api/generated/models/email-settings-out';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EmailSettingsPage } from './email-settings-page';

const AJUSTES_URL = '/api/v1/admin/email-settings';
const PRUEBA_URL = '/api/v1/admin/email-settings/test';

const CATALOGO = {
  presets: [
    { provider: 'resend', host: 'smtp.resend.com', port: 465, username: 'resend' },
    { provider: 'acumbamail', host: 'smtp.acumbamail.com', port: 587, username: null },
    { provider: 'ses', host: null, port: 465, username: null },
    { provider: 'custom', host: null, port: 587, username: null },
  ],
  ses_regions: ['eu-west-1', 'us-east-1'],
  allow_insecure: false,
} as const;

const DEL_ENTORNO: EmailSettingsOut = {
  ...CATALOGO,
  presets: [...CATALOGO.presets],
  ses_regions: [...CATALOGO.ses_regions],
  source: 'environment',
  provider: null,
  host: 'smtp.acumbamail.com',
  port: 587,
  tls_mode: 'starttls',
  username: null,
  region: null,
  from_address: 'no-responder@eventarium.org',
  has_password: true,
  password_hint: null,
  updated_at: null,
};

const GUARDADO: EmailSettingsOut = {
  ...DEL_ENTORNO,
  source: 'database',
  provider: 'resend',
  host: 'smtp.resend.com',
  port: 465,
  tls_mode: 'implicit',
  username: 'resend',
  from_address: 'hola@eventarium.org',
  password_hint: 'AB12',
  updated_at: '2026-09-25T19:00:00Z',
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EmailSettingsPage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
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
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  async function crearYCargar(
    estado: EmailSettingsOut = DEL_ENTORNO,
  ): Promise<ComponentFixture<EmailSettingsPage>> {
    const fixture = TestBed.createComponent(EmailSettingsPage);
    await avanzar(fixture);
    http.expectOne(AJUSTES_URL).flush(estado);
    await avanzar(fixture);
    await avanzar(fixture);
    return fixture;
  }

  it('sin configuración guardada propone Resend y no tiene violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();
    const pagina = fixture.componentInstance;

    expect(pagina.provider()).toBe('resend');
    expect(pagina.port()).toBe('465');
    expect(fixture.nativeElement.textContent).toContain('smtp.resend.com');
    expect(fixture.nativeElement.textContent).toContain('variables SMTP_*');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('nunca rellena la contraseña guardada: solo enseña su pista', async () => {
    const fixture = await crearYCargar(GUARDADO);

    const campo = fixture.nativeElement.querySelector('#correo-password') as HTMLInputElement;
    expect(campo.value).toBe('');
    expect(fixture.nativeElement.textContent).toContain('AB12');
  });

  it('con el mismo proveedor guarda sin reenviar la contraseña', async () => {
    const fixture = await crearYCargar(GUARDADO);

    const envio = fixture.componentInstance.guardar(new Event('submit'));
    const peticion = http.expectOne((req) => req.method === 'PUT' && req.url === AJUSTES_URL);
    expect(peticion.request.body).toMatchObject({
      provider: 'resend',
      port: 465,
      password: null,
      username: null,
      from_address: 'hola@eventarium.org',
    });
    peticion.flush(GUARDADO);
    await envio;
    await avanzar(fixture);
    expect(fixture.componentInstance.aviso()).toContain('Se ha guardado');
  });

  it('al cambiar de proveedor exige una contraseña nueva y no llama al backend', async () => {
    const fixture = await crearYCargar(GUARDADO);
    const pagina = fixture.componentInstance;

    pagina['elegirProveedor']('acumbamail');
    expect(pagina.port()).toBe('587');
    await pagina.guardar(new Event('submit'));

    expect(pagina.error()).toContain('contraseña o API key');
    http.expectNone(AJUSTES_URL);
  });

  it('la prueba envía el formulario y muestra por qué ha fallado', async () => {
    const fixture = await crearYCargar();
    const pagina = fixture.componentInstance;
    pagina.password.set('re_nueva_clave_1234');

    const envio = pagina.probar();
    const peticion = http.expectOne(PRUEBA_URL);
    expect(peticion.request.body).toMatchObject({
      provider: 'resend',
      password: 're_nueva_clave_1234',
    });
    peticion.flush({ ok: false, sent_to: 'yo@eventarium.org', motivo: 'autenticacion' });
    await envio;
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('ha rechazado el usuario o la API key');
  });

  it('solo confirma sin reservas si se guarda lo mismo que pasó la prueba', async () => {
    const fixture = await crearYCargar(GUARDADO);
    const pagina = fixture.componentInstance;

    const prueba = pagina.probar();
    http.expectOne(PRUEBA_URL).flush({ ok: true, sent_to: 'yo@eventarium.org', motivo: null });
    await prueba;
    const envio = pagina.guardar(new Event('submit'));
    http.expectOne((req) => req.method === 'PUT').flush(GUARDADO);
    await envio;
    expect(pagina.aviso()).toContain('en menos de un minuto');

    pagina.fromAddress.set('otro@eventarium.org');
    const otro = pagina.guardar(new Event('submit'));
    http.expectOne((req) => req.method === 'PUT').flush(GUARDADO);
    await otro;
    expect(pagina.aviso()).toContain('sin un correo de prueba aceptado');
  });

  it('valida el remitente antes de llamar al backend', async () => {
    const fixture = await crearYCargar(GUARDADO);
    const pagina = fixture.componentInstance;
    pagina.fromAddress.set('no-es-un-correo');

    await pagina.guardar(new Event('submit'));
    expect(pagina.error()).toContain('formato de correo');
    http.expectNone(AJUSTES_URL);
  });

  it('volver al entorno borra la fila y recarga el estado', async () => {
    const fixture = await crearYCargar(GUARDADO);

    const accion = fixture.componentInstance.volverAlEntorno();
    http.expectOne((req) => req.method === 'DELETE' && req.url === AJUSTES_URL).flush(null);
    await avanzar(fixture);
    http.expectOne((req) => req.method === 'GET' && req.url === AJUSTES_URL).flush(DEL_ENTORNO);
    await accion;
    await avanzar(fixture);

    expect(fixture.componentInstance.ajustes()?.source).toBe('environment');
  });
});
