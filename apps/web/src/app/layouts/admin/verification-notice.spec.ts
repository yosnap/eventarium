import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../core/api/error.interceptor';
import { AuthService } from '../../core/auth/auth.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { VerificationNotice } from './verification-notice';

const ESTADO_URL = '/api/v1/users/me/verification';
const REENVIO_URL = '/api/v1/users/me/resend-verification';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function montar(
  emailVerified: boolean,
  suplantando: object | null = null,
): Promise<{
  fixture: ComponentFixture<VerificationNotice>;
  raiz: HTMLElement;
  http: HttpTestingController;
}> {
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
      { provide: AuthService, useValue: { suplantando: signal(suplantando) } },
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(VerificationNotice);
  await avanzar(fixture);
  http.expectOne(ESTADO_URL).flush({ email: 'luis@ejemplo.com', email_verified: emailVerified });
  await avanzar(fixture);
  return { fixture, raiz: fixture.nativeElement as HTMLElement, http };
}

describe('VerificationNotice', () => {
  let http: HttpTestingController;

  afterEach(() => {
    http.verify();
  });

  it('con el correo verificado no pinta nada', async () => {
    const montado = await montar(true);
    http = montado.http;

    expect(montado.raiz.textContent?.trim()).toBe('');
  });

  it('sin verificar avisa de que la cuenta está limitada, sin violaciones de accesibilidad', async () => {
    const montado = await montar(false);
    http = montado.http;

    expect(montado.raiz.textContent).toContain('Tu cuenta aún no está verificada');
    expect(montado.raiz.textContent).toContain('luis@ejemplo.com');
    await esperarSinViolacionesDeAccesibilidad(montado.raiz);
  });

  it('reenviar pide un enlace nuevo, lo confirma y deshabilita el botón', async () => {
    const { fixture, raiz, http: h } = await montar(false);
    http = h;

    raiz.querySelector<HTMLButtonElement>('button')?.click();
    await avanzar(fixture);
    const peticion = http.expectOne(REENVIO_URL);
    expect(peticion.request.method).toBe('POST');
    peticion.flush(
      { email: 'luis@ejemplo.com', email_verified: false },
      { status: 202, statusText: 'Accepted' },
    );
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Te hemos enviado un enlace nuevo');
    expect(raiz.querySelector<HTMLButtonElement>('button')?.disabled).toBe(true);
  });

  it('si ya se verificó en otra pestaña (409), el aviso desaparece', async () => {
    const { fixture, raiz, http: h } = await montar(false);
    http = h;

    raiz.querySelector<HTMLButtonElement>('button')?.click();
    await avanzar(fixture);
    http
      .expectOne(REENVIO_URL)
      .flush({ detail: 'Tu correo ya está verificado.' }, { status: 409, statusText: 'Conflict' });
    await avanzar(fixture);

    expect(raiz.textContent?.trim()).toBe('');
  });

  it('durante una suplantación avisa pero no ofrece reenviar', async () => {
    const montado = await montar(false, { token: 't' });
    http = montado.http;

    expect(montado.raiz.textContent).toContain('Tu cuenta aún no está verificada');
    expect(montado.raiz.querySelector('button')).toBeNull();
  });
});
