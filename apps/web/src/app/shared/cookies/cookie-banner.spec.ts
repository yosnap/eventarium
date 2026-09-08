import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { CookieBanner } from './cookie-banner';
import { CookieConsentService } from '../../core/cookies/cookie-consent.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('CookieBanner', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    delete (window as unknown as { __dummyAnalyticsHits?: number }).__dummyAnalyticsHits;
    document.getElementById('dummy-analytics-script')?.remove();

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
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('aparece en la primera visita y bloquea el script de ejemplo no esencial', async () => {
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('[role="region"]')).not.toBeNull();
    expect(document.getElementById('dummy-analytics-script')).toBeNull();
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('"aceptar todo" y "rechazar todo" tienen el mismo peso visual (misma variante de botón)', async () => {
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);

    const botones = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ) as HTMLButtonElement[];
    const clases = botones.map((boton) => boton.className);
    // Las tres acciones principales usan la misma clase de variante: ninguna
    // lleva la clase `primario`, que sí destacaría una sobre las demás.
    expect(clases.some((c) => c.includes('primario'))).toBe(false);
    expect(new Set(clases.slice(0, 3)).size).toBe(1);
  });

  it('rechazar todo no activa el script de ejemplo y registra el consentimiento', async () => {
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);

    const botones = (fixture.nativeElement as HTMLElement).querySelectorAll('button');
    const rechazar = Array.from(botones).find((b) => b.textContent?.includes('Rechazar todo'));
    rechazar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/public/cookie-consent');
    expect(peticion.request.body).toEqual({ categories: ['necessary'] });
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    await avanzar(fixture);

    expect(document.getElementById('dummy-analytics-script')).toBeNull();
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="region"]')).toBeNull();
    expect(JSON.parse(localStorage.getItem('cookie-consent') ?? '{}').categories).toEqual([
      'necessary',
    ]);
  });

  it('aceptar todo activa el script de ejemplo no esencial', async () => {
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);

    const botones = (fixture.nativeElement as HTMLElement).querySelectorAll('button');
    const aceptar = Array.from(botones).find((b) => b.textContent?.includes('Aceptar todo'));
    aceptar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/public/cookie-consent');
    expect(new Set(peticion.request.body.categories)).toEqual(
      new Set(['necessary', 'analytics', 'marketing']),
    );
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    await avanzar(fixture);

    expect(document.getElementById('dummy-analytics-script')).not.toBeNull();
  });

  it('personalizar solo activa las categorías marcadas', async () => {
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;

    const personalizar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Personalizar'),
    );
    personalizar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    const checkboxes = Array.from(
      raiz.querySelectorAll('input[type="checkbox"]:not([disabled])'),
    ) as HTMLInputElement[];
    expect(checkboxes.length).toBe(2);
    checkboxes[0].checked = true;
    checkboxes[0].dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const guardar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Guardar preferencias'),
    );
    guardar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/public/cookie-consent');
    expect(new Set(peticion.request.body.categories)).toEqual(new Set(['necessary', 'analytics']));
    peticion.flush(null, { status: 204, statusText: 'No Content' });
  });

  it('no vuelve a mostrarse si ya hay una decisión guardada', async () => {
    localStorage.setItem('cookie-consent', JSON.stringify({ categories: ['necessary'] }));
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);

    expect((fixture.nativeElement as HTMLElement).querySelector('[role="region"]')).toBeNull();
  });

  it('guarda versión y fecha en la decisión persistida', async () => {
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);

    const botones = (fixture.nativeElement as HTMLElement).querySelectorAll('button');
    const aceptar = Array.from(botones).find((b) => b.textContent?.includes('Aceptar todo'));
    aceptar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);
    http
      .expectOne('/api/v1/public/cookie-consent')
      .flush(null, { status: 204, statusText: 'No Content' });
    await avanzar(fixture);

    const guardado = JSON.parse(localStorage.getItem('cookie-consent') ?? '{}');
    expect(guardado.version).toBe(1);
    expect(typeof guardado.created_at).toBe('string');
    expect(Number.isNaN(Date.parse(guardado.created_at))).toBe(false);
  });

  it('"Gestionar cookies" reabre el banner con las categorías previamente elegidas ya marcadas', async () => {
    localStorage.setItem(
      'cookie-consent',
      JSON.stringify({ categories: ['necessary', 'analytics'], version: 1, created_at: 'x' }),
    );
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;

    // Ya hay una decisión guardada: el banner no se muestra hasta reabrir la gestión.
    expect(raiz.querySelector('[role="region"]')).toBeNull();

    const consentimiento = TestBed.inject(CookieConsentService);
    consentimiento.abrirGestionDeCookies();
    await avanzar(fixture);

    expect(raiz.querySelector('[role="region"]')).not.toBeNull();
    const checkboxes = Array.from(
      raiz.querySelectorAll('input[type="checkbox"]:not([disabled])'),
    ) as HTMLInputElement[];
    // Analíticas (ya elegida antes) viene precargada; marketing no.
    expect(checkboxes[0].checked).toBe(true);
    expect(checkboxes[1].checked).toBe(false);
    await esperarSinViolacionesDeAccesibilidad(raiz);

    // Cambia una categoría y guarda: la nueva decisión sobrescribe la anterior.
    checkboxes[1].checked = true;
    checkboxes[1].dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const guardar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Guardar preferencias'),
    );
    guardar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/public/cookie-consent');
    expect(new Set(peticion.request.body.categories)).toEqual(
      new Set(['necessary', 'analytics', 'marketing']),
    );
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    await avanzar(fixture);

    expect(raiz.querySelector('[role="region"]')).toBeNull();
    const persistido = JSON.parse(localStorage.getItem('cookie-consent') ?? '{}');
    expect(new Set(persistido.categories)).toEqual(
      new Set(['necessary', 'analytics', 'marketing']),
    );
  });

  it('"Volver" tras reabrir "Gestionar cookies" cierra sin cambiar la decisión guardada', async () => {
    localStorage.setItem(
      'cookie-consent',
      JSON.stringify({ categories: ['necessary'], version: 1, created_at: 'x' }),
    );
    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;

    const consentimiento = TestBed.inject(CookieConsentService);
    consentimiento.abrirGestionDeCookies();
    await avanzar(fixture);
    expect(raiz.querySelector('[role="region"]')).not.toBeNull();

    const volver = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Volver'),
    );
    volver?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    expect(raiz.querySelector('[role="region"]')).toBeNull();
    expect(JSON.parse(localStorage.getItem('cookie-consent') ?? '{}').categories).toEqual([
      'necessary',
    ]);
  });

  it('rechazar todo no toca nada relacionado con Turnstile (aislamiento arquitectónico)', async () => {
    // Cloudflare Turnstile es un caso aparte a propósito (ver
    // `turnstile-widget.ts` y `templates.py`): `CookieConsentService` no debe
    // importarlo, referenciarlo ni condicionar su carga bajo ningún concepto,
    // para que rechazar cookies nunca pueda bloquear el formulario público de
    // inscripción. Se comprueba aquí en el mismo módulo que decide qué
    // scripts activar (`activarScriptsDeLasCategorias`): el único script que
    // se activa o no según la categoría es el de ejemplo (`dummy-analytics`).
    const modulo = await import('../../core/cookies/cookie-consent.service');
    const fuente = modulo.CookieConsentService.toString();
    expect(fuente.toLowerCase()).not.toContain('turnstile');

    const fixture = TestBed.createComponent(CookieBanner);
    await avanzar(fixture);
    const rechazar = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((b) => b.textContent?.includes('Rechazar todo'));
    rechazar?.dispatchEvent(new Event('click'));
    await avanzar(fixture);
    http.expectOne('/api/v1/public/cookie-consent').flush(null, {
      status: 204,
      statusText: 'No Content',
    });

    // Turnstile no depende de ningún estado que `CookieConsentService` toque
    // (ni `localStorage`, ni el DOM que gestiona `DummyAnalyticsService`).
    expect(document.getElementById('dummy-analytics-script')).toBeNull();
  });
});
