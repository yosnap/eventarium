import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { McpConnectionsPage } from './mcp-connections-page';

const CONEXION = {
  id: 'c1',
  name: 'Claude de Ana',
  method: 'api_key',
  scopes: ['eventos:leer'],
  event_ids: null,
  key_prefix: 'evtm_abcdefg',
  created_at: '2026-09-24T10:00:00Z',
  expires_at: '2026-12-23T10:00:00Z',
  last_used_at: null,
  revoked_at: null,
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('McpConnectionsPage', () => {
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
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function montar(opciones: { permiso: boolean; dueno: boolean }) {
    const fixture = TestBed.createComponent(McpConnectionsPage);
    fixture.detectChanges();
    const mias = http.expectOne('/api/v1/users/me/mcp-connections');
    if (opciones.permiso) mias.flush([CONEXION]);
    else mias.flush({ detail: 'Sin permiso' }, { status: 403, statusText: 'Forbidden' });
    const org = http.expectOne('/api/v1/organizations/me/mcp-connections');
    if (opciones.dueno) org.flush([{ ...CONEXION, id: 'c2', user_email: 'otra@example.com' }]);
    else org.flush({ detail: 'Solo el dueño' }, { status: 403, statusText: 'Forbidden' });
    await avanzar(fixture);
    // El formulario de clave pide los eventos si hay permiso.
    http.match('/api/v1/events').forEach((peticion) => peticion.flush({ items: [] }));
    await avanzar(fixture);
    return { fixture, raiz: fixture.nativeElement as HTMLElement };
  }

  it('sin el permiso explica cómo pedirlo y no ofrece crear claves', async () => {
    const { raiz } = await montar({ permiso: false, dueno: false });

    expect(raiz.textContent).toContain('Tu rol no permite conectar asistentes');
    expect(raiz.textContent).not.toContain('Nueva clave de API');
  });

  it('con el permiso lista mis conexiones y las deja revocar', async () => {
    const { fixture, raiz } = await montar({ permiso: true, dueno: false });

    expect(raiz.textContent).toContain('Claude de Ana');
    expect(raiz.textContent).not.toContain('Conexiones de la organización');
    const revocar = [...raiz.querySelectorAll('button')].find(
      (boton) => boton.textContent?.replace(/\s+/g, ' ').trim() === 'Revocar Claude de Ana',
    );
    revocar!.click();
    http.expectOne('/api/v1/users/me/mcp-connections/c1').flush(null);
    await avanzar(fixture);
    http
      .expectOne('/api/v1/users/me/mcp-connections')
      .flush([{ ...CONEXION, revoked_at: '2026-09-24T11:00:00Z' }]);
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('el dueño ve también las conexiones de la organización', async () => {
    const { raiz } = await montar({ permiso: true, dueno: true });

    expect(raiz.textContent).toContain('Conexiones de la organización');
    expect(raiz.textContent).toContain('otra@example.com');
  });
});
