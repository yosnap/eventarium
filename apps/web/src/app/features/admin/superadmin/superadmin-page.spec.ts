import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { SuperadminPage } from './superadmin-page';

const AUDIT_LOG_URL = '/api/v1/admin/audit-log';

function pagina() {
  return {
    items: [
      {
        id: 'a1',
        actor_user_id: 'u1',
        organization_id: 'o1',
        action: 'organization.created',
        entity_type: 'organization',
        entity_id: 'o1',
        detail: { slug: 'acme' },
        created_at: '2026-09-08T10:00:00Z',
      },
    ],
    total: 1,
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('SuperadminPage', () => {
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
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lista la auditoría inicial, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(SuperadminPage);
    await avanzar(fixture);
    http.expectOne((p) => p.url === AUDIT_LOG_URL).flush(pagina());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('organization.created');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('borra un inscrito con reautenticación y recarga la auditoría', async () => {
    const fixture = TestBed.createComponent(SuperadminPage);
    await avanzar(fixture);
    http.expectOne((p) => p.url === AUDIT_LOG_URL).flush(pagina());
    await avanzar(fixture);

    vi.stubGlobal('confirm', () => true);

    function escribir(id: string, valor: string): void {
      const campo = fixture.nativeElement.querySelector(`#${id}`) as HTMLInputElement;
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    }
    escribir('borrar-event-id', '11111111-1111-1111-1111-111111111111');
    escribir('borrar-email', 'quien-sea@example.com');
    escribir('borrar-password', 'mi-contraseña');
    await avanzar(fixture);

    const formularios = fixture.nativeElement.querySelectorAll('form');
    formularios[2].dispatchEvent(new Event('submit', { cancelable: true }));
    await avanzar(fixture);

    const peticion = http.expectOne(
      (p) => p.method === 'DELETE' && p.url === '/api/v1/admin/registrations/by-email',
    );
    expect(peticion.request.body).toEqual({
      event_id: '11111111-1111-1111-1111-111111111111',
      email: 'quien-sea@example.com',
      password: 'mi-contraseña',
    });
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    await avanzar(fixture);

    http.expectOne((p) => p.url === AUDIT_LOG_URL).flush(pagina());
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Inscripción borrada.');
    vi.unstubAllGlobals();
  });

  it('exporta RGPD con POST y body, nunca con GET (la Fetch API prohíbe body en GET)', async () => {
    const fixture = TestBed.createComponent(SuperadminPage);
    await avanzar(fixture);
    http.expectOne((p) => p.url === AUDIT_LOG_URL).flush(pagina());
    await avanzar(fixture);

    // Solo se sustituyen los dos métodos estáticos usados por el componente
    // (jsdom no los implementa): sustituir el propio constructor `URL` con
    // `vi.stubGlobal` rompería cualquier otro `new URL(...)` del resto de la
    // suite, que comparte entorno entre ficheros de test.
    const crearObjectUrlOriginal = URL.createObjectURL;
    const revocarObjectUrlOriginal = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => 'blob:mock');
    URL.revokeObjectURL = vi.fn();

    const crearElementoOriginal = document.createElement.bind(document);
    const enlaceFalso = crearElementoOriginal('a');
    vi.spyOn(enlaceFalso, 'click').mockImplementation(() => undefined);
    // Solo intercepta la creación del `<a>` de descarga: Angular sigue
    // necesitando `createElement` real para el resto de nodos del DOM.
    vi.spyOn(document, 'createElement').mockImplementation((tagName: string, options?: unknown) =>
      tagName === 'a'
        ? enlaceFalso
        : crearElementoOriginal(tagName, options as ElementCreationOptions),
    );

    function escribir(id: string, valor: string): void {
      const campo = fixture.nativeElement.querySelector(`#${id}`) as HTMLInputElement;
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    }
    escribir('export-event-id', '22222222-2222-2222-2222-222222222222');
    escribir('export-password', 'mi-contraseña');
    await avanzar(fixture);

    const formularios = fixture.nativeElement.querySelectorAll('form');
    formularios[1].dispatchEvent(new Event('submit', { cancelable: true }));
    await avanzar(fixture);

    // El hallazgo crítico: con `provideHttpClient(withFetch())`, un `GET` con
    // body lanza un `TypeError` antes de llegar a la red. Este `expectOne`
    // comprueba que la petición real es un `POST` (nunca un `GET`), que es la
    // única forma correcta de mandar body de reautenticación.
    const peticion = http.expectOne(
      (p) => p.url === '/api/v1/admin/events/22222222-2222-2222-2222-222222222222/rgpd-export',
    );
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({ password: 'mi-contraseña' });
    expect(peticion.request.responseType).toBe('blob');

    peticion.flush(new Blob(['contenido']), {
      status: 200,
      statusText: 'OK',
      headers: { 'Content-Type': 'application/zip' },
    });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Exportación descargada.');
    vi.restoreAllMocks();
    URL.createObjectURL = crearObjectUrlOriginal;
    URL.revokeObjectURL = revocarObjectUrlOriginal;
  });
});
