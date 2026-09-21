import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { AiConfigFields } from './ai-config-fields';

const MODELOS_URL = (proveedor: string) => `/api/v1/ai/catalog/${proveedor}/models`;
const PRUEBA_URL = '/api/v1/ai/test-connection';

const CATALOGO = [
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
    etiqueta: 'Endpoint personalizado',
    api_base_editable: true,
    api_base_fijo: null,
    modelos_abiertos: false,
    coste_auditable: false,
    modelos: [],
  },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('AiConfigFields', () => {
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
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  async function crear(): Promise<ComponentFixture<AiConfigFields>> {
    const fixture = TestBed.createComponent(AiConfigFields);
    fixture.componentRef.setInput('catalogo', CATALOGO);
    fixture.componentRef.setInput('idPrefijo', 'ia-test');
    await avanzar(fixture);
    return fixture;
  }

  function textoDe(fixture: ComponentFixture<unknown>): string {
    return fixture.nativeElement.textContent as string;
  }

  it('sin proveedor elegido no consulta ningún listado', async () => {
    const fixture = await crear();

    http.expectNone(MODELOS_URL('openai'));
    expect(fixture.componentInstance.modelosEnVivo()).toBeNull();
  });

  it('al elegir proveedor pide sus modelos en vivo y los pinta', async () => {
    const fixture = await crear();
    fixture.componentInstance.provider.set('openai');
    await avanzar(fixture);

    expect(fixture.componentInstance.cargandoModelos()).toBe(true);
    expect(textoDe(fixture)).toContain('Consultando los modelos disponibles');

    http.expectOne(MODELOS_URL('openai')).flush({
      proveedor: 'openai',
      en_vivo: true,
      motivo: null,
      modelos: [
        { clave: 'gpt-4o', etiqueta: 'GPT-4o', vision: true },
        { clave: 'gpt-6-nuevo', etiqueta: 'GPT-6 nuevo', vision: false },
      ],
    });
    await avanzar(fixture);

    const opciones = [
      ...fixture.nativeElement.querySelectorAll('#ia-test-modelo-nativo option'),
    ].map((opcion: HTMLOptionElement) => opcion.value);
    // El modelo nuevo no está en el catálogo cerrado: solo puede salir del
    // listado en vivo.
    expect(opciones).toContain('gpt-6-nuevo');
    expect(textoDe(fixture)).toContain('GPT-4o · visión');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('avisa cuando el listado no es en vivo, sin vaciar el desplegable', async () => {
    const fixture = await crear();
    fixture.componentInstance.provider.set('openai');
    await avanzar(fixture);

    http.expectOne(MODELOS_URL('openai')).flush({
      proveedor: 'openai',
      en_vivo: false,
      motivo: 'clave_rechazada',
      modelos: [{ clave: 'gpt-4o', etiqueta: 'GPT-4o', vision: true }],
    });
    await avanzar(fixture);

    const texto = textoDe(fixture);
    expect(texto).toContain('No se ha podido consultar el catálogo en vivo');
    expect(texto).toContain('el proveedor ha rechazado la clave');
    expect(
      fixture.nativeElement.querySelectorAll('#ia-test-modelo-nativo option').length,
    ).toBeGreaterThan(1);
  });

  it('cambiar de proveedor descarta los modelos del anterior', async () => {
    const fixture = await crear();
    fixture.componentInstance.provider.set('openai');
    await avanzar(fixture);
    http.expectOne(MODELOS_URL('openai')).flush({
      proveedor: 'openai',
      en_vivo: true,
      motivo: null,
      modelos: [{ clave: 'gpt-4o', etiqueta: 'GPT-4o', vision: true }],
    });
    await avanzar(fixture);

    fixture.componentInstance.provider.set('custom');
    await avanzar(fixture);

    expect(fixture.componentInstance.modelosEnVivo()).toBeNull();
    http.expectOne(MODELOS_URL('custom')).flush({
      proveedor: 'custom',
      en_vivo: true,
      motivo: null,
      modelos: [],
    });
    await avanzar(fixture);
  });

  it('un fallo de la petición deja el catálogo cerrado, sin romper la pantalla', async () => {
    const fixture = await crear();
    fixture.componentInstance.provider.set('openai');
    await avanzar(fixture);

    http
      .expectOne(MODELOS_URL('openai'))
      .flush({ detail: 'Demasiadas peticiones.' }, { status: 429, statusText: 'Too Many' });
    await avanzar(fixture);

    expect(fixture.componentInstance.modelosEnVivo()).toBeNull();
    expect(fixture.componentInstance.cargandoModelos()).toBe(false);
    expect(textoDe(fixture)).toContain('GPT-4o');
  });

  // --- Probar conexión --------------------------------------------------------

  async function conProveedorCargado(): Promise<ComponentFixture<AiConfigFields>> {
    const fixture = await crear();
    fixture.componentInstance.provider.set('openai');
    await avanzar(fixture);
    http.expectOne(MODELOS_URL('openai')).flush({
      proveedor: 'openai',
      en_vivo: false,
      motivo: 'sin_clave',
      modelos: [{ clave: 'gpt-4o', etiqueta: 'GPT-4o', vision: true }],
    });
    await avanzar(fixture);
    return fixture;
  }

  it('el botón de probar está deshabilitado mientras falte proveedor o clave', async () => {
    const fixture = await conProveedorCargado();

    expect(fixture.componentInstance['sePuedeProbar']()).toBe(false);

    fixture.componentInstance.apiKey.set('sk-recien-escrita');
    await avanzar(fixture);

    expect(fixture.componentInstance['sePuedeProbar']()).toBe(true);
  });

  it('un endpoint personalizado no se puede probar sin su dirección', async () => {
    const fixture = await crear();
    fixture.componentInstance.provider.set('custom');
    fixture.componentInstance.apiKey.set('sk-recien-escrita');
    await avanzar(fixture);
    http
      .expectOne(MODELOS_URL('custom'))
      .flush({ proveedor: 'custom', en_vivo: false, motivo: 'sin_clave', modelos: [] });
    await avanzar(fixture);

    expect(fixture.componentInstance['sePuedeProbar']()).toBe(false);

    fixture.componentInstance.apiBase.set('https://modelos.example.com/v1');
    await avanzar(fixture);

    expect(fixture.componentInstance['sePuedeProbar']()).toBe(true);
  });

  it('una prueba correcta envía la clave escrita y pasa sus modelos al desplegable', async () => {
    const fixture = await conProveedorCargado();
    fixture.componentInstance.apiKey.set('sk-recien-escrita');
    await avanzar(fixture);

    const probando = fixture.componentInstance.probarConexion();
    await avanzar(fixture);

    const peticion = http.expectOne(PRUEBA_URL);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({
      provider: 'openai',
      api_key: 'sk-recien-escrita',
    });
    peticion.flush({
      ok: true,
      motivo: null,
      modelos: [{ clave: 'gpt-7-privado', etiqueta: 'GPT-7 privado', vision: true }],
    });
    await probando;
    await avanzar(fixture);

    const texto = textoDe(fixture);
    expect(texto).toContain('Conexión correcta');
    // El aviso de listado no en vivo desaparece: ya hay una consulta buena.
    expect(texto).not.toContain('No se ha podido consultar el catálogo en vivo');
    expect(texto).toContain('GPT-7 privado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('una clave rechazada se enseña con su motivo, sin tocar el desplegable', async () => {
    const fixture = await conProveedorCargado();
    fixture.componentInstance.apiKey.set('sk-mala');
    await avanzar(fixture);

    const probando = fixture.componentInstance.probarConexion();
    await avanzar(fixture);
    http.expectOne(PRUEBA_URL).flush({ ok: false, motivo: 'clave_rechazada', modelos: [] });
    await probando;
    await avanzar(fixture);

    const texto = textoDe(fixture);
    expect(texto).toContain('No se ha podido conectar');
    expect(texto).toContain('el proveedor ha rechazado la clave');
    expect(texto).toContain('GPT-4o');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('un motivo desconocido cae a un texto genérico en vez de la clave de traducción', async () => {
    const fixture = await conProveedorCargado();
    fixture.componentInstance.apiKey.set('sk-recien-escrita');
    await avanzar(fixture);

    const probando = fixture.componentInstance.probarConexion();
    await avanzar(fixture);
    http.expectOne(PRUEBA_URL).flush({ ok: false, motivo: 'motivo_que_no_existe', modelos: [] });
    await probando;
    await avanzar(fixture);

    const texto = textoDe(fixture);
    expect(texto).toContain('no se ha podido completar la comprobación');
    expect(texto).not.toContain('admin.ia.motivos');
  });

  it('cambiar de proveedor borra el resultado de la prueba anterior', async () => {
    const fixture = await conProveedorCargado();
    fixture.componentInstance.apiKey.set('sk-recien-escrita');
    await avanzar(fixture);
    const probando = fixture.componentInstance.probarConexion();
    await avanzar(fixture);
    http.expectOne(PRUEBA_URL).flush({ ok: true, motivo: null, modelos: [] });
    await probando;
    await avanzar(fixture);

    fixture.componentInstance.provider.set('custom');
    await avanzar(fixture);

    expect(fixture.componentInstance.resultado()).toBeNull();
    expect(textoDe(fixture)).not.toContain('Conexión correcta');
    http
      .expectOne(MODELOS_URL('custom'))
      .flush({ proveedor: 'custom', en_vivo: true, motivo: null, modelos: [] });
    await avanzar(fixture);
  });
});
