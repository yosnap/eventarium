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


const METRICS_URL = '/api/v1/admin/metrics';

/** Resuelve la carga del escritorio, que la pantalla pide al construirse. */
function flushMetricas(http: HttpTestingController): void {
  const peticiones = http.match((p) => p.url === METRICS_URL);
  for (const peticion of peticiones) {
    peticion.flush({
      salud: { database: 'ok', storage: 'ok', redis: 'ok' },
      cifras: {
        organizaciones_activas: 1,
        organizaciones_totales: 1,
        eventos_totales: 0,
        eventos_publicados: 0,
        usuarios: 1,
        miembros: 1,
      },
      organizaciones: [],
    });
  }
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
    flushMetricas(http);
    http.expectOne((p) => p.url === AUDIT_LOG_URL).flush(pagina());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('organization.created');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('borra un inscrito con reautenticación y recarga la auditoría', async () => {
    const fixture = TestBed.createComponent(SuperadminPage);
    await avanzar(fixture);
    flushMetricas(http);
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
    flushMetricas(http);
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

describe('SuperadminPage — escritorio de la plataforma', () => {
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

  /** Monta con el escritorio ya resuelto y la auditoría pendiente de resolver. */
  async function montarConMetricas(
    organizaciones: readonly Record<string, unknown>[] = [],
    salud: Record<string, string> = { database: 'ok', storage: 'ok', redis: 'ok' },
  ): Promise<ComponentFixture<SuperadminPage>> {
    const fixture = TestBed.createComponent(SuperadminPage);
    await avanzar(fixture);
    for (const peticion of http.match((p) => p.url.startsWith(AUDIT_LOG_URL))) {
      peticion.flush({ items: [], total: 0, limit: 50, offset: 0 });
    }
    http.expectOne((p) => p.url === METRICS_URL).flush({
      salud,
      cifras: {
        organizaciones_activas: 1,
        organizaciones_totales: 2,
        eventos_totales: 5,
        eventos_publicados: 3,
        usuarios: 9,
        miembros: 12,
      },
      organizaciones,
    });
    await avanzar(fixture);
    return fixture;
  }

  function organizacion(overrides: Record<string, unknown> = {}): Record<string, unknown> {
    return {
      id: 'o1',
      name: 'IAWIC',
      slug: 'iawic',
      is_active: true,
      eventos: 3,
      eventos_publicados: 2,
      inscripciones: 150,
      miembros: 4,
      evento_mas_reciente: '2026-09-30T10:00:00Z',
      ultimo_evento_creado: '2026-09-01T10:00:00Z',
      ultima_inscripcion: '2026-09-15T10:00:00Z',
      ultimo_acceso: '2026-09-16T10:00:00Z',
      stripe_conectada: true,
      tiene_stripe_pendiente_con_eventos_de_pago: false,
      publicados_sin_inscripciones: false,
      ...overrides,
    };
  }

  it('muestra la salud de las tres dependencias con su producto real', async () => {
    const fixture = await montarConMetricas();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('PostgreSQL');
    expect(raiz.textContent).toContain('SeaweedFS');
    expect(raiz.textContent).toContain('Redis');
    expect(raiz.textContent).toContain('Correcto');
  });

  it('una dependencia caída se lee como error en texto, no solo en color', async () => {
    const fixture = await montarConMetricas([], {
      database: 'ok',
      storage: 'error',
      redis: 'ok',
    });
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('Con error');
  });

  it('pinta las cuatro marcas de actividad por separado', async () => {
    // Cada una responde a una pregunta distinta; fundirlas en una sola celda
    // perdería justo la diferencia que el admin necesita ver.
    const fixture = await montarConMetricas([organizacion()]);
    const raiz = fixture.nativeElement as HTMLElement;

    const cabeceras = Array.from(raiz.querySelectorAll('thead th')).map((th) =>
      th.textContent?.trim(),
    );
    expect(cabeceras).toContain('Evento tocado');
    expect(cabeceras).toContain('Evento creado');
    expect(cabeceras).toContain('Inscripción');
    expect(cabeceras).toContain('Último acceso');
  });

  it('una marca que no consta se dice como tal, no se deja en blanco', async () => {
    const fixture = await montarConMetricas([
      organizacion({ ultimo_acceso: null, ultima_inscripcion: null }),
    ]);
    const raiz = fixture.nativeElement as HTMLElement;

    const fila = raiz.querySelector('tbody tr') as HTMLElement;
    expect(fila.textContent).toContain('—');
  });

  it('una organización que publica de pago sin poder cobrar sale marcada', async () => {
    // Es la bandera que convierte cuatro datos sueltos en una alerta.
    const fixture = await montarConMetricas([
      organizacion({
        stripe_conectada: false,
        tiene_stripe_pendiente_con_eventos_de_pago: true,
      }),
    ]);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('sin poder cobrar');
  });

  it('una organización desactivada se distingue de una con actividad', async () => {
    const fixture = await montarConMetricas([
      organizacion({ id: 'o2', name: 'Parada', slug: 'parada', is_active: false }),
    ]);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('Desactivada');
  });

  it('no pinta ningún importe de las organizaciones', async () => {
    // La frontera del producto, comprobada también en la pantalla: si algún día
    // alguien añade una columna de dinero, esto lo dice antes de que se vea.
    const fixture = await montarConMetricas([organizacion()]);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).not.toContain('Ingresos');
    expect(raiz.textContent).not.toContain('Facturación');
    expect(raiz.textContent).not.toContain('€');
  });

  it('si el escritorio falla, se avisa y las herramientas siguen', async () => {
    const fixture = TestBed.createComponent(SuperadminPage);
    await avanzar(fixture);
    for (const peticion of http.match((p) => p.url.startsWith(AUDIT_LOG_URL))) {
      peticion.flush({ items: [], total: 0, limit: 50, offset: 0 });
    }
    http
      .expectOne((p) => p.url === METRICS_URL)
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('No se pudieron cargar los datos de la instalación');
    // La auditoría y las herramientas RGPD siguen ahí.
    expect(raiz.textContent).toContain('auditoría');
  });
});
