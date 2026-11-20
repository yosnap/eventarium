import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { PlatformLegalPage } from './platform-legal-page';

const LEGALES_URL = '/api/v1/admin/legal-pages';

const SIN_EDITAR = {
  legal_notice: { content: 'Aviso legal de Eventarium', is_custom: false },
  privacy_policy: { content: 'Privacidad de Eventarium', is_custom: false },
  cookies_policy: { content: 'Cookies de Eventarium', is_custom: false },
  registration_terms: { content: 'Condiciones de inscripción de Eventarium', is_custom: false },
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('PlatformLegalPage', () => {
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
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  async function crearYCargar(
    cuerpo: typeof SIN_EDITAR = SIN_EDITAR,
  ): Promise<ComponentFixture<PlatformLegalPage>> {
    const fixture = TestBed.createComponent(PlatformLegalPage);
    await avanzar(fixture);
    http.expectOne(`${LEGALES_URL}?idioma=es-ES`).flush(cuerpo);
    await avanzar(fixture);
    return fixture;
  }

  it('carga las cuatro páginas de plataforma y no tiene violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    expect(fixture.componentInstance.avisoLegal()).toBe('Aviso legal de Eventarium');
    expect(fixture.componentInstance.privacidad()).toBe('Privacidad de Eventarium');
    expect(fixture.componentInstance.cookies()).toBe('Cookies de Eventarium');
    expect(fixture.componentInstance.condicionesDeInscripcion()).toBe(
      'Condiciones de inscripción de Eventarium',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('incluye las condiciones de inscripción: son también de la plataforma', async () => {
    const fixture = await crearYCargar();
    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('ondiciones de inscripci');
  });

  it('indica si cada página está personalizada o en plantilla', async () => {
    const fixture = await crearYCargar({
      ...SIN_EDITAR,
      legal_notice: { content: 'Texto propio', is_custom: true },
    });
    expect(fixture.componentInstance.avisoEsPersonalizado()).toBe(true);
    expect(fixture.componentInstance.privacidadEsPersonalizada()).toBe(false);
  });

  it('un campo vacío se envía como null para volver a la plantilla', async () => {
    const fixture = await crearYCargar();
    fixture.componentInstance.avisoLegal.set('   ');

    const guardado = fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);
    const peticion = http.expectOne((r) => r.url === LEGALES_URL && r.method === 'PATCH');
    expect(peticion.request.body).toMatchObject({
      legal_notice_content: null,
      privacy_policy_content: 'Privacidad de Eventarium',
    });
    peticion.flush(SIN_EDITAR);
    await guardado;

    expect(fixture.componentInstance.guardado()).toBe(true);
  });

  it('en inglés carga la traducción guardada, envía solo lo cambiado y revisa la de la IA', async () => {
    const fixture = await crearYCargar();
    const espanola = (content: string, translation: unknown = null) => ({
      content,
      is_custom: false,
      served_locale: 'es-ES',
      translation,
    });

    fixture.componentInstance['cambiarIdioma']('en-US');
    await avanzar(fixture);
    http.expectOne(`${LEGALES_URL}?idioma=en-US`).flush({
      legal_notice: {
        content: 'Legal notice',
        is_custom: false,
        served_locale: 'en-US',
        translation: { content: 'Legal notice', origin: 'ia', status: 'al_dia' },
      },
      // Escrita a mano para un español que ya cambió: no se sirve, pero se edita.
      privacy_policy: espanola('Privacidad de Eventarium', {
        content: 'Old privacy',
        origin: 'manual',
        status: 'desactualizada',
      }),
      cookies_policy: espanola('Cookies de Eventarium'),
      registration_terms: espanola('Condiciones de inscripción de Eventarium'),
    });
    await avanzar(fixture);

    expect(fixture.componentInstance.avisoLegal()).toBe('Legal notice');
    expect(fixture.componentInstance.privacidad()).toBe('Old privacy');
    expect(fixture.componentInstance.cookies()).toBe('');
    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('no se sirve hasta que la actualices');
    expect(texto).toContain('Marcar como revisada');

    fixture.componentInstance.privacidad.set('New privacy');
    const guardado = fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);
    const peticion = http.expectOne((r) => r.url === LEGALES_URL && r.method === 'PATCH');
    // La traducción de la IA sin tocar no se reenvía (se volvería «escrita a mano»).
    expect(peticion.request.body).toEqual({
      locale: 'en-US',
      privacy_policy_content: 'New privacy',
    });
    peticion.flush(SIN_EDITAR);
    await guardado;

    const revisada = fixture.componentInstance['revisar']('legal_notice');
    await avanzar(fixture);
    const revision = http.expectOne(`${LEGALES_URL}/review`);
    expect(revision.request.body).toEqual({ page: 'legal_notice', locale: 'en-US' });
    revision.flush(SIN_EDITAR);
    await revisada;
  });

  it('mientras se guarda no cambia de idioma, para no mezclar versiones', async () => {
    const fixture = await crearYCargar();

    const guardado = fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);
    fixture.componentInstance['cambiarIdioma']('en-US');
    await avanzar(fixture);

    expect(fixture.componentInstance.idioma()).toBe('es-ES');
    http.expectNone(`${LEGALES_URL}?idioma=en-US`);
    http.expectOne((r) => r.url === LEGALES_URL && r.method === 'PATCH').flush(SIN_EDITAR);
    await guardado;
  });
});
