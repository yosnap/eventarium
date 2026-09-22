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
import { AiSettingsPage } from './ai-settings-page';

const AJUSTES_URL = '/api/v1/admin/ai-settings';
const USO_URL = '/api/v1/admin/ai-usage';
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
  {
    clave: 'custom',
    etiqueta: 'Endpoint personalizado (OpenAI-compatible)',
    api_base_editable: true,
    api_base_fijo: null,
    modelos_abiertos: true,
    coste_auditable: false,
    modelos: [],
  },
];

const AJUSTES = {
  provider: 'openai',
  default_model: 'gpt-4o',
  api_base: null,
  api_base_editable: false,
  has_key: true,
  api_key_hint: 'zk29',
  monthly_ceiling_usd: '50.000000',
  updated_at: '2026-09-19T10:00:00Z',
};

const USO = {
  periodo: '2026-09',
  llamadas: 3,
  llamadas_fallidas: 1,
  gasto_usd: '0.004500',
  gasto_auditable: false,
  input_tokens: 120,
  output_tokens: 45,
  monthly_ceiling_usd: '50.000000',
  ultimos: [
    {
      id: '11111111-1111-1111-1111-111111111111',
      organization_id: '22222222-2222-2222-2222-222222222222',
      use_case: 'accounting_ocr',
      provider: 'openai',
      model: 'gpt-4o',
      status: 'liquidado',
      input_tokens: 40,
      output_tokens: 15,
      cost_usd: '0.001500',
      cost_auditable: false,
      error_code: null,
      latency_ms: 820,
      created_at: '2026-09-19T10:05:00Z',
    },
  ],
  ultimos_errores: [
    { error_code: 'limite_superado', veces: 1, ultima_vez: '2026-09-19T10:06:00Z' },
  ],
};

/** `true` para las peticiones de modelos en vivo del componente de campos. */
function esListadoDeModelos(url: string): boolean {
  return url.startsWith('/api/v1/ai/catalog/') && url.endsWith('/models');
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('AiSettingsPage', () => {
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
   * Lo que devuelvan no importa en esta pantalla —tiene sus propios tests en
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
    ajustes: typeof AJUSTES = AJUSTES,
  ): Promise<ComponentFixture<AiSettingsPage>> {
    const fixture = TestBed.createComponent(AiSettingsPage);
    await avanzar(fixture);
    http.expectOne(CATALOGO_URL).flush(CATALOGO);
    http.expectOne(AJUSTES_URL).flush(ajustes);
    http.expectOne(USO_URL).flush(USO);
    await avanzar(fixture);
    await avanzar(fixture);
    await atenderModelos(fixture);
    return fixture;
  }

  it('carga la configuración y el uso agregado sin violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    expect(fixture.componentInstance.provider()).toBe('openai');
    expect(fixture.componentInstance.defaultModel()).toBe('gpt-4o');
    expect(fixture.componentInstance.techo()).toBe('50.000000');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('nunca rellena la clave, ni siquiera enmascarada: solo su pista', async () => {
    const fixture = await crearYCargar();

    const clave = fixture.nativeElement.querySelector('#ia-plataforma-clave') as HTMLInputElement;
    expect(clave.value).toBe('');
    expect(fixture.componentInstance.apiKey()).toBe('');
    expect(fixture.nativeElement.textContent).toContain('zk29');
  });

  it('el desplegable de proveedores sale del catálogo del backend', async () => {
    const fixture = await crearYCargar();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('NaN (nan.builders)');
    expect(texto).toContain('OpenAI');
    // El proveedor guardado tiene dirección fija: no hay campo editable.
    expect(fixture.nativeElement.querySelector('#ia-plataforma-api-base')).toBeNull();
  });

  it('marca los modelos con visión y avisa cuando el elegido no la tiene', async () => {
    const fixture = await crearYCargar();

    expect(fixture.nativeElement.textContent).toContain('GPT-4o · visión');

    fixture.componentInstance.provider.set('nan_builders');
    fixture.componentInstance.defaultModel.set('deepseek-v4-flash');
    await avanzar(fixture);
    await atenderModelos(fixture);

    expect(fixture.nativeElement.textContent).toContain('Este modelo no acepta imágenes');
  });

  it('avisa de gasto no auditable en los proveedores sin precio declarado', async () => {
    // El aviso del formulario habla del proveedor elegido; el del resumen de
    // gasto (que aquí ya sale, porque el periodo trae importes estimados) es
    // otro texto distinto.
    const avisoDelProveedor = 'no publica el precio por token';
    const fixture = await crearYCargar();
    expect(fixture.nativeElement.textContent).not.toContain(avisoDelProveedor);

    fixture.componentInstance.provider.set('nan_builders');
    await avanzar(fixture);
    await atenderModelos(fixture);

    expect(fixture.nativeElement.textContent).toContain(avisoDelProveedor);
  });

  it('cambiar de proveedor sin escribir la clave no llega a enviarse', async () => {
    const fixture = await crearYCargar();
    fixture.componentInstance.provider.set('nan_builders');
    fixture.componentInstance.defaultModel.set('deepseek-v4-flash');
    await avanzar(fixture);
    await atenderModelos(fixture);

    await fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);

    http.expectNone({ method: 'PUT', url: AJUSTES_URL });
    expect(fixture.componentInstance.error()).toContain('exige escribir también la clave');
  });

  it('guarda proveedor, modelo, clave y techo, y vacía el campo de clave', async () => {
    const fixture = await crearYCargar();
    fixture.componentInstance.provider.set('nan_builders');
    fixture.componentInstance.defaultModel.set('deepseek-v4-flash');
    fixture.componentInstance.apiKey.set('sk-secreta-de-prueba');
    fixture.componentInstance.techo.set('30');
    await avanzar(fixture);
    await atenderModelos(fixture);

    const guardando = fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);

    const peticion = http.expectOne({ method: 'PUT', url: AJUSTES_URL });
    expect(peticion.request.body).toEqual({
      provider: 'nan_builders',
      default_model: 'deepseek-v4-flash',
      api_key: 'sk-secreta-de-prueba',
      monthly_ceiling_usd: '30',
    });
    // Dirección fija del catálogo: no se envía `api_base` (el backend da 422).
    expect(peticion.request.body).not.toHaveProperty('api_base');
    peticion.flush({
      ...AJUSTES,
      provider: 'nan_builders',
      default_model: 'deepseek-v4-flash',
      api_base: 'https://api.nan.builders/v1',
      api_key_hint: 'ueba',
      monthly_ceiling_usd: '30.000000',
    });
    await avanzar(fixture);
    http.expectOne(USO_URL).flush(USO);
    await guardando;
    await avanzar(fixture);

    expect(fixture.componentInstance.apiKey()).toBe('');
    expect(fixture.componentInstance.guardado()).toBe(true);
  });

  it('solo el techo: envía únicamente ese campo', async () => {
    const fixture = await crearYCargar();
    fixture.componentInstance.techo.set('');
    await avanzar(fixture);

    const guardando = fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);

    const peticion = http.expectOne({ method: 'PUT', url: AJUSTES_URL });
    expect(peticion.request.body).toEqual({ monthly_ceiling_usd: null });
    peticion.flush({ ...AJUSTES, monthly_ceiling_usd: null });
    await avanzar(fixture);
    http.expectOne(USO_URL).flush(USO);
    await guardando;
  });
});
