import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { AsistenteClaveTraduccion } from './asistente-clave-traduccion';

const CATALOGO = [
  {
    clave: 'openrouter',
    etiqueta: 'OpenRouter',
    api_base_editable: false,
    api_base_fijo: null,
    modelos_abiertos: true,
    coste_auditable: true,
    modelos: [{ clave: 'openai/gpt-4o-mini', etiqueta: 'GPT-4o mini', vision: true }],
  },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('AsistenteClaveTraduccion', () => {
  let http: HttpTestingController;
  const roles = signal<readonly string[]>(['owner']);

  beforeEach(() => {
    roles.set(['owner']);
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
        { provide: AuthService, useValue: { roles } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  function botonPorTexto(raiz: HTMLElement, texto: string): HTMLButtonElement {
    const boton = [...raiz.querySelectorAll('button')].find((b) => b.textContent?.includes(texto));
    if (!boton) throw new Error(`No hay botón «${texto}»`);
    return boton;
  }

  it('pregunta primero y «a mano» no configura nada', async () => {
    const fixture = TestBed.createComponent(AsistenteClaveTraduccion);
    const descartado = vi.fn();
    fixture.componentInstance.descartado.subscribe(descartado);
    await avanzar(fixture);

    const raiz: HTMLElement = fixture.nativeElement;
    expect(raiz.textContent).toContain('traduzcan automáticamente');
    await esperarSinViolacionesDeAccesibilidad(raiz);
    botonPorTexto(raiz, 'No, traduciré a mano').click();
    expect(descartado).toHaveBeenCalledOnce();
  });

  it('pide la clave, la verifica con una traducción real y solo entonces da por configurada', async () => {
    const fixture = TestBed.createComponent(AsistenteClaveTraduccion);
    const configurada = vi.fn();
    fixture.componentInstance.configurada.subscribe(configurada);
    await avanzar(fixture);
    botonPorTexto(fixture.nativeElement, 'Sí, configurar mi clave').click();
    await avanzar(fixture);
    http.expectOne('/api/v1/ai/catalog').flush(CATALOGO);
    await avanzar(fixture);
    expect(fixture.nativeElement.textContent).toContain('leer justificantes');

    const pagina = fixture.componentInstance;
    pagina.provider.set('openrouter');
    pagina.defaultModel.set('openai/gpt-4o-mini');
    pagina.apiKey.set('sk-or-prueba');
    await avanzar(fixture);
    for (const peticion of http.match((req) => req.url.endsWith('/models'))) {
      peticion.flush({
        proveedor: 'openrouter',
        en_vivo: true,
        motivo: null,
        modelos: CATALOGO[0].modelos,
      });
    }
    await avanzar(fixture);
    const guardar = pagina['guardar'](new Event('submit'));
    await avanzar(fixture);
    const fallida = http.expectOne({ method: 'PUT', url: '/api/v1/organizations/me/ai-settings' });
    expect(fallida.request.body).toEqual({
      provider: 'openrouter',
      default_model: 'openai/gpt-4o-mini',
      api_key: 'sk-or-prueba',
      verify_translation: true,
    });
    fallida.flush(
      { detail: 'La clave no ha podido traducir.', code: 'traduccion_de_prueba_fallida' },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await guardar;
    await avanzar(fixture);
    expect(configurada).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('no ha podido traducir');

    const otra = pagina['guardar'](new Event('submit'));
    await avanzar(fixture);
    http.expectOne({ method: 'PUT', url: '/api/v1/organizations/me/ai-settings' }).flush({});
    await otra;
    expect(configurada).toHaveBeenCalledOnce();
  });

  it('a quien no es propietario le dice que se lo pida al propietario', async () => {
    roles.set(['organizer']);
    const fixture = TestBed.createComponent(AsistenteClaveTraduccion);
    await avanzar(fixture);
    expect(fixture.nativeElement.textContent).toContain('propietario');
    expect(fixture.nativeElement.textContent).not.toContain('Sí, configurar mi clave');
  });
});
