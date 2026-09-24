import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { themingDePrueba } from '../../../../testing/theming.fixture';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { ThemingService } from '../../../core/theming/theming.service';
import { ConsentimientoPage } from './consentimiento-page';

const SOLICITUD = {
  client_id: 'abc123',
  client_name: 'Claude',
  no_verificado: true,
  redirect_uri: 'https://claude.ai/api/mcp/auth_callback',
  organization_name: 'IA Week',
  ambitos_pedidos: ['eventos:leer', 'eventos:editar'],
  ambitos_permitidos: ['eventos:leer', 'inscripciones:cifras', 'eventos:cancelar'],
  ambitos_por_defecto: ['eventos:leer'],
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('ConsentimientoPage', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: ThemingService, useValue: themingDePrueba() },
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap({ solicitud: 's1' }) } },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function montar() {
    const fixture = TestBed.createComponent(ConsentimientoPage);
    fixture.detectChanges();
    http.expectOne('/api/v1/oauth/solicitudes/s1').flush(SOLICITUD);
    await avanzar(fixture);
    http.match((r) => r.url === '/api/v1/events').forEach((p) => p.flush({ items: [] }));
    await avanzar(fixture);
    return { fixture, raiz: fixture.nativeElement as HTMLElement };
  }

  function boton(raiz: HTMLElement, texto: string): HTMLButtonElement {
    return [...raiz.querySelectorAll('button')].find((b) => b.textContent?.trim() === texto)!;
  }

  it('enseña quién pide la conexión y adónde volverá, y no marca cancelar', async () => {
    const { raiz } = await montar();

    expect(raiz.textContent).toContain('Cliente no verificado');
    expect(raiz.textContent).toContain('https://claude.ai/api/mcp/auth_callback');
    expect(raiz.textContent).toContain('IA Week');
    expect(raiz.textContent).toContain('El asistente pide:');
    const casillas = [...raiz.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')];
    const cancelar = casillas.find((c) =>
      c.closest('label')?.textContent?.includes('Cancelar eventos'),
    );
    expect(cancelar?.checked).toBe(false);
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('un error al aprobar deja el formulario para reintentar', async () => {
    const { fixture, raiz } = await montar();

    boton(raiz, 'Permitir').click();
    http
      .expectOne('/api/v1/oauth/solicitudes/s1/aprobar')
      .flush({ detail: 'Sin permiso' }, { status: 403, statusText: 'Forbidden' });
    await avanzar(fixture);

    expect(raiz.querySelector('app-alert')).not.toBeNull();
    expect(boton(raiz, 'Permitir')).toBeTruthy();
  });

  it('al permitir envía los permisos marcados y vuelve al asistente', async () => {
    const { fixture, raiz } = await montar();
    const asignacionDeUrl = vi.fn();
    Object.defineProperty(window, 'location', {
      value: {
        ...window.location,
        set href(url: string) {
          asignacionDeUrl(url);
        },
      },
      writable: true,
    });

    boton(raiz, 'Permitir').click();
    const envio = http.expectOne('/api/v1/oauth/solicitudes/s1/aprobar');
    expect(envio.request.body).toEqual({ scopes: ['eventos:leer'], event_ids: null });
    envio.flush({ redirect_to: 'https://claude.ai/api/mcp/auth_callback?code=x' });
    await avanzar(fixture);

    expect(asignacionDeUrl).toHaveBeenCalledWith('https://claude.ai/api/mcp/auth_callback?code=x');
  });
});
