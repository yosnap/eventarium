import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { OrganizationAiSettings } from './ai-settings';

const AJUSTES_URL = '/api/v1/organizations/me/ai-settings';
const USO_URL = '/api/v1/organizations/me/ai-usage';
const CATALOGO_URL = '/api/v1/ai/catalog';

const CATALOGO = [
  {
    clave: 'nan_builders',
    etiqueta: 'NaN (nan.builders)',
    api_base_editable: false,
    api_base_fijo: 'https://api.nan.builders/v1',
    modelos_abiertos: false,
    coste_auditable: false,
    modelos: [{ clave: 'deepseek-v4-flash', etiqueta: 'DeepSeek v4 Flash', vision: false }],
  },
  {
    clave: 'openai',
    etiqueta: 'OpenAI',
    api_base_editable: false,
    api_base_fijo: null,
    modelos_abiertos: false,
    coste_auditable: true,
    modelos: [{ clave: 'gpt-4o', etiqueta: 'GPT-4o', vision: true }],
  },
];

const HEREDADA = {
  origen: 'heredada' as const,
  provider: 'openai',
  default_model: 'gpt-4o',
  api_base: null,
  api_base_editable: false,
  has_key: true,
  // Nunca la pista de la clave de plataforma (V-11).
  api_key_hint: null,
  monthly_limit_usd: null,
  monthly_ceiling_usd: '50.000000',
  limite_efectivo_usd: '50.000000',
  servicio_ia_activo: true,
  updated_at: null,
};

const PROPIA = {
  ...HEREDADA,
  origen: 'propia' as const,
  provider: 'nan_builders',
  default_model: 'deepseek-v4-flash',
  api_base: 'https://api.nan.builders/v1',
  api_key_hint: 'ueba',
  monthly_limit_usd: '10.000000',
  limite_efectivo_usd: '10.000000',
};

const USO = {
  periodo: '2026-09',
  llamadas: 2,
  llamadas_fallidas: 0,
  gasto_usd: '0.003000',
  gasto_auditable: true,
  input_tokens: 80,
  output_tokens: 20,
  limite_efectivo_usd: '10.000000',
  servicio_ia_activo: true,
  ultimos: [
    {
      id: '33333333-3333-3333-3333-333333333333',
      use_case: 'accounting_ocr',
      provider: 'openai',
      model: 'gpt-4o',
      status: 'liquidado',
      input_tokens: 40,
      output_tokens: 10,
      cost_usd: '0.001500',
      cost_auditable: true,
      error_code: null,
      latency_ms: 700,
      created_at: '2026-09-19T10:05:00Z',
    },
  ],
  ultimos_errores: [],
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** `true` para las peticiones de modelos en vivo del componente de campos. */
function esListadoDeModelos(url: string): boolean {
  return url.startsWith('/api/v1/ai/catalog/') && url.endsWith('/models');
}

describe('OrganizationAiSettings', () => {
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

  /**
   * Atiende las peticiones de modelos en vivo que dispara elegir proveedor.
   * Lo que devuelven no importa en esta pantalla —tiene sus propios tests en
   * `ai-config-fields.spec.ts`—, pero sin atenderlas `http.verify()` fallaría.
   */
  async function atenderModelos(fixture: ComponentFixture<unknown>): Promise<void> {
    for (const peticion of http.match((req) => esListadoDeModelos(req.url))) {
      const proveedor = peticion.request.url.split('/').at(-2) ?? '';
      peticion.flush({
        proveedor,
        en_vivo: true,
        motivo: null,
        modelos: CATALOGO.find((entrada) => entrada.clave === proveedor)?.modelos ?? [],
      });
    }
    await avanzar(fixture);
  }

  async function crearYCargar(
    ajustes: typeof HEREDADA | typeof PROPIA = HEREDADA,
  ): Promise<ComponentFixture<OrganizationAiSettings>> {
    const fixture = TestBed.createComponent(OrganizationAiSettings);
    await avanzar(fixture);
    http.expectOne(CATALOGO_URL).flush(CATALOGO);
    http.expectOne(AJUSTES_URL).flush(ajustes);
    http.expectOne(USO_URL).flush(USO);
    await avanzar(fixture);
    await avanzar(fixture);
    await atenderModelos(fixture);
    return fixture;
  }

  it('la vista heredada dice de dónde sale la config y no tiene violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('hereda la configuración de la plataforma');
    expect(texto).toContain('OpenAI');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('en la vista heredada no aparece la pista de la clave de plataforma', async () => {
    // V-11: la clave de plataforma es compartida por toda la instalación.
    const fixture = await crearYCargar();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('La plataforma tiene una clave guardada');
    expect(texto).not.toContain('acabada en');
  });

  it('con configuración propia muestra su origen, su límite y su pista', async () => {
    const fixture = await crearYCargar(PROPIA);

    expect(fixture.componentInstance.modo()).toBe('propia');
    expect(fixture.componentInstance.limite()).toBe('10.000000');
    expect(fixture.nativeElement.textContent).toContain('usa su propia configuración');
    expect(fixture.nativeElement.textContent).toContain('ueba');
  });

  it('un 403 del backend deja la pantalla en solo lectura, sin formulario', async () => {
    const fixture = TestBed.createComponent(OrganizationAiSettings);
    await avanzar(fixture);
    http.expectOne(CATALOGO_URL).flush(CATALOGO);
    http
      .expectOne(AJUSTES_URL)
      .flush({ detail: 'Solo el propietario.' }, { status: 403, statusText: 'Forbidden' });
    http
      .expectOne(USO_URL)
      .flush({ detail: 'Solo el propietario.' }, { status: 403, statusText: 'Forbidden' });
    await avanzar(fixture);
    await avanzar(fixture);

    expect(fixture.componentInstance.soloLectura()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Solo el propietario puede editar esto');
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('avisa antes de enviar si el límite supera el techo de la plataforma', async () => {
    const fixture = await crearYCargar(PROPIA);
    fixture.componentInstance.limite.set('999');
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Por encima del techo de la plataforma');

    await fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);

    http.expectNone({ method: 'PUT', url: AJUSTES_URL });
  });

  it('guarda la configuración propia entera y vacía el campo de clave', async () => {
    const fixture = await crearYCargar();
    fixture.componentInstance.modo.set('propia');
    fixture.componentInstance.provider.set('nan_builders');
    fixture.componentInstance.defaultModel.set('deepseek-v4-flash');
    fixture.componentInstance.apiKey.set('sk-secreta-de-prueba');
    fixture.componentInstance.limite.set('5');
    await avanzar(fixture);
    await atenderModelos(fixture);

    const guardando = fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);

    const peticion = http.expectOne({ method: 'PUT', url: AJUSTES_URL });
    expect(peticion.request.body).toEqual({
      provider: 'nan_builders',
      default_model: 'deepseek-v4-flash',
      api_key: 'sk-secreta-de-prueba',
      monthly_limit_usd: '5',
    });
    peticion.flush({ ...PROPIA, monthly_limit_usd: '5.000000' });
    await avanzar(fixture);
    http.expectOne(USO_URL).flush(USO);
    await guardando;
    await avanzar(fixture);

    expect(fixture.componentInstance.apiKey()).toBe('');
    expect(fixture.componentInstance.guardado()).toBe(true);
  });

  it('volver a heredar borra la configuración propia y recarga el estado', async () => {
    const fixture = await crearYCargar(PROPIA);
    // El botón solo existe cuando ya hay configuración propia y se mira el
    // modo heredado.
    fixture.componentInstance.modo.set('heredada');
    await avanzar(fixture);

    const borrando = fixture.componentInstance.volverAHeredar();
    await avanzar(fixture);
    http
      .expectOne({ method: 'DELETE', url: AJUSTES_URL })
      .flush(null, { status: 204, statusText: 'No Content' });
    await avanzar(fixture);
    http.expectOne({ method: 'GET', url: AJUSTES_URL }).flush(HEREDADA);
    await avanzar(fixture);
    http.expectOne(USO_URL).flush(USO);
    await borrando;
    await avanzar(fixture);

    expect(fixture.componentInstance.modo()).toBe('heredada');
    expect(fixture.componentInstance.ajustes()?.origen).toBe('heredada');
  });

  it('avisa cuando el admin ha apagado el servicio de IA para la organización', async () => {
    const fixture = await crearYCargar({ ...HEREDADA, servicio_ia_activo: false });

    expect(fixture.nativeElement.textContent).toContain('La IA está desactivada');
  });
});
