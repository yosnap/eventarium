import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventsListPage } from './events-list-page';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** El directorio pide el catálogo de categorías y la primera página de eventos. */
function responderListado(
  http: HttpTestingController,
  eventos: readonly object[],
  categorias: readonly object[] = [],
  total: number = eventos.length,
): void {
  http.expectOne('/api/v1/public/event-categories').flush(categorias);
  http
    .expectOne((peticion) => peticion.url === '/api/v1/public/events')
    .flush(eventos, { headers: { 'X-Total-Count': String(total) } });
}

@Component({ template: '' })
class RutaVacia {}

describe('EventsListPage', () => {
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
        provideRouter([{ path: 'eventos', component: RutaVacia }]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    document.documentElement.removeAttribute('data-theme');
  });

  it('lista los eventos en tema claro sin violaciones de accesibilidad', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    responderListado(http, [
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'iawic-2026',
        title: 'IA Week in Cascais 2026',
        summary: 'El evento del año.',
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-03T18:00:00Z',
        location_mode: 'in_person',
        location_name: 'Sala principal',
        city: 'Lisboa',
        registration_mode: 'free',
        capacity: null,
        reserved_count: 0,
      },
    ]);
    await avanzar(fixture);

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('lista los eventos publicados sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    responderListado(http, [
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'iawic-2026',
        title: 'IA Week in Cascais 2026',
        summary: 'El evento del año.',
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-03T18:00:00Z',
        location_mode: 'in_person',
        location_name: 'Sala principal',
        city: 'Lisboa',
        registration_mode: 'free',
        capacity: null,
        reserved_count: 0,
      },
    ]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('IA Week in Cascais 2026');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra el mensaje de "sin eventos" cuando el listado está vacío', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    responderListado(http, []);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Todavía no hay eventos publicados');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el buscador filtra por título en el cliente, sin llamar a la API de nuevo', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    responderListado(http, [
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'iawic-2026',
        title: 'IA Week in Cascais 2026',
        summary: 'El evento del año.',
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-03T18:00:00Z',
        location_mode: 'in_person',
        location_name: 'Sala principal',
        city: 'Lisboa',
        registration_mode: 'free',
        capacity: null,
        reserved_count: 0,
      },
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'meetup-comunidad',
        title: 'Meetup de la comunidad',
        summary: null,
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-11-05T18:00:00Z',
        ends_at: '2026-11-05T20:00:00Z',
        location_mode: 'online',
        location_name: null,
        city: 'Valencia',
        registration_mode: 'approval',
        capacity: 50,
        reserved_count: 50,
      },
    ]);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('IA Week in Cascais 2026');
    expect(raiz.textContent).toContain('Meetup de la comunidad');
    // Sin `capacity` (null) el evento marca "sin límite"; con las plazas ya
    // consumidas del todo (capacity === reserved_count) marca "Completo".
    expect(raiz.textContent).toContain('Sin límite');
    expect(raiz.textContent).toContain('Completo');

    const buscador = raiz.querySelector('input[type="search"]') as HTMLInputElement;
    buscador.value = 'cascais';
    buscador.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    expect(raiz.textContent).toContain('IA Week in Cascais 2026');
    expect(raiz.textContent).not.toContain('Meetup de la comunidad');
  });

  it('el filtro por formato solo muestra los eventos de esa modalidad', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    responderListado(http, [
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'iawic-2026',
        title: 'IA Week in Cascais 2026',
        summary: null,
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-03T18:00:00Z',
        location_mode: 'in_person',
        location_name: 'Sala principal',
        city: 'Lisboa',
        registration_mode: 'free',
        capacity: null,
        reserved_count: 0,
      },
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'meetup-comunidad',
        title: 'Meetup de la comunidad',
        summary: null,
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-11-05T18:00:00Z',
        ends_at: '2026-11-05T20:00:00Z',
        location_mode: 'online',
        location_name: null,
        city: 'Valencia',
        registration_mode: 'approval',
        capacity: 50,
        reserved_count: 50,
      },
    ]);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const tagOnline = Array.from(raiz.querySelectorAll('.tag')).find(
      (b) => b.textContent?.trim() === 'Online',
    ) as HTMLButtonElement;
    tagOnline.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Meetup de la comunidad');
    expect(raiz.textContent).not.toContain('IA Week in Cascais 2026');
    expect(tagOnline.getAttribute('aria-pressed')).toBe('true');
  });

  it('el select de ciudad solo muestra los eventos de la ciudad elegida', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    responderListado(http, [
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'iawic-2026',
        title: 'IA Week in Cascais 2026',
        summary: null,
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-03T18:00:00Z',
        location_mode: 'in_person',
        location_name: 'Sala principal',
        city: 'Lisboa',
        registration_mode: 'free',
        capacity: null,
        reserved_count: 0,
      },
      {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug: 'meetup-comunidad',
        title: 'Meetup de la comunidad',
        summary: null,
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-11-05T18:00:00Z',
        ends_at: '2026-11-05T20:00:00Z',
        location_mode: 'online',
        location_name: null,
        city: 'Valencia',
        registration_mode: 'approval',
        capacity: 50,
        reserved_count: 50,
      },
    ]);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const botonCiudad = raiz.querySelector('#ciudad') as HTMLButtonElement;
    expect(botonCiudad).not.toBeNull();

    botonCiudad.click();
    await avanzar(fixture);
    const opcionValencia = Array.from(raiz.querySelectorAll('[role="option"]')).find(
      (opcion) => opcion.textContent?.trim() === 'Valencia',
    ) as HTMLLIElement;
    expect(opcionValencia).toBeDefined();
    opcionValencia.click();
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Meetup de la comunidad');
    expect(raiz.textContent).not.toContain('IA Week in Cascais 2026');
  });

  describe('categorías, etiquetas y paginación', () => {
    const TALLER = { slug: 'taller', name: 'Taller' };

    function evento(slug: string, extra: Record<string, unknown> = {}) {
      return {
        organization: { slug: 'acme', name: 'Acme', page_public: false },
        slug,
        title: `Evento ${slug}`,
        summary: null,
        cover_url: null,
        timezone: 'Europe/Madrid',
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-01T18:00:00Z',
        location_mode: 'in_person',
        location_name: null,
        city: null,
        registration_mode: 'free',
        capacity: null,
        reserved_count: 0,
        ...extra,
      };
    }

    it('enseña las categorías del catálogo y la categoría y etiquetas de cada tarjeta', async () => {
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      responderListado(
        http,
        [evento('a', { category: TALLER, tags: ['ia', 'datos'] })],
        [TALLER, { slug: 'charla', name: 'Charla' }],
      );
      await avanzar(fixture);
      const texto: string = fixture.nativeElement.textContent;

      expect(texto).toContain('Todas');
      expect(texto).toContain('Charla');
      const tarjeta = fixture.nativeElement.querySelector('a.ev') as HTMLElement;
      expect(tarjeta.textContent).toContain('Taller');
      expect(tarjeta.textContent).toContain('#ia');
      expect(tarjeta.textContent).toContain('#datos');
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    it('pulsar una categoría filtra por URL', async () => {
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      responderListado(http, [evento('a')], [TALLER]);
      await avanzar(fixture);
      const router = TestBed.inject(Router);
      const navegar = vi.spyOn(router, 'navigate').mockResolvedValue(true);

      const boton = [...fixture.nativeElement.querySelectorAll('button.tag')].find(
        (b) => (b as HTMLElement).textContent?.trim() === 'Taller',
      ) as HTMLButtonElement;
      boton.click();

      expect(navegar).toHaveBeenCalledWith(
        [],
        expect.objectContaining({ queryParams: { categoria: 'taller', etiqueta: null } }),
      );
    });

    it('los filtros de la URL viajan al API y las etiquetas activas se pueden quitar', async () => {
      await TestBed.inject(Router).navigateByUrl(
        '/eventos?categoria=taller&etiqueta=ia&etiqueta=datos',
      );
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      http.expectOne('/api/v1/public/event-categories').flush([TALLER]);
      const peticion = http.expectOne((p) => p.url === '/api/v1/public/events');
      expect(peticion.request.params.get('categoria')).toBe('taller');
      expect(peticion.request.params.getAll('etiqueta')).toEqual(['ia', 'datos']);
      expect(peticion.request.params.get('limit')).toBe('24');
      peticion.flush([evento('a')], { headers: { 'X-Total-Count': '1' } });
      await avanzar(fixture);

      const texto: string = fixture.nativeElement.textContent;
      expect(texto).toContain('#ia ✕');
      expect(texto).toContain('#datos ✕');
      const quitar = fixture.nativeElement.querySelector(
        'button[aria-label="Quitar la etiqueta ia"]',
      );
      expect(quitar).not.toBeNull();
    });

    it('sin resultados con filtros lo dice y ofrece quitarlos', async () => {
      await TestBed.inject(Router).navigateByUrl('/eventos?categoria=taller');
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      responderListado(http, [], [TALLER]);
      await avanzar(fixture);

      expect(fixture.nativeElement.textContent).toContain('No hay eventos con estos filtros');
      expect(fixture.nativeElement.textContent).toContain('Quitar los filtros');
    });

    it('«Ver más» pide la página siguiente con el offset de lo ya cargado', async () => {
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      responderListado(http, [evento('a'), evento('b')], [], 3);
      await avanzar(fixture);
      expect(fixture.nativeElement.textContent).toContain('Ver más (2 de 3)');

      const boton = [...fixture.nativeElement.querySelectorAll('button')].find((b) =>
        (b as HTMLElement).textContent?.includes('Ver más'),
      ) as HTMLButtonElement;
      boton.click();
      await avanzar(fixture);
      const siguiente = http.expectOne((p) => p.url === '/api/v1/public/events');
      expect(siguiente.request.params.get('offset')).toBe('2');
      siguiente.flush([evento('c')], { headers: { 'X-Total-Count': '3' } });
      await avanzar(fixture);
      await avanzar(fixture);

      expect(fixture.nativeElement.querySelectorAll('a.ev')).toHaveLength(3);
      expect(fixture.nativeElement.textContent).not.toContain('Ver más');
    });

    it('una respuesta de un filtro anterior no pisa la del filtro actual (cambio rápido)', async () => {
      const router = TestBed.inject(Router);
      await router.navigateByUrl('/eventos?categoria=taller');
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      const categorias = http.expectOne('/api/v1/public/event-categories');
      const primera = http.expectOne((p) => p.url === '/api/v1/public/events');
      expect(primera.request.params.get('categoria')).toBe('taller');

      // Antes de que llegue la primera respuesta, el usuario cambia de filtro.
      await router.navigateByUrl('/eventos?categoria=charla');
      fixture.detectChanges();
      const segunda = http
        .match((p) => p.url === '/api/v1/public/events')
        .find((p) => p.request.params.get('categoria') === 'charla');
      const categorias2 = http.match('/api/v1/public/event-categories');
      expect(segunda).toBeDefined();

      // La respuesta correcta se resuelve primero; la vieja, después. Se responde
      // todo de una vez (esperar entre medias bloquearía con la petición pendiente).
      segunda?.flush([evento('de-charla')], { headers: { 'X-Total-Count': '1' } });
      categorias2.forEach((c) => c.flush([]));
      primera.flush([evento('de-taller')], { headers: { 'X-Total-Count': '1' } });
      categorias.flush([]);
      await avanzar(fixture);
      await avanzar(fixture);

      const titulos = [...fixture.nativeElement.querySelectorAll('a.ev h3')].map((h) =>
        h.textContent?.trim(),
      );
      expect(titulos).toEqual(['Evento de-charla']);
    });

    it('un filtro con forma inválida en la URL se descarta en vez de romper el listado', async () => {
      await TestBed.inject(Router).navigateByUrl(
        '/eventos?categoria=Mala%20Categoria&etiqueta=%23mal',
      );
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      http.expectOne('/api/v1/public/event-categories').flush([]);
      const peticion = http.expectOne((p) => p.url === '/api/v1/public/events');
      expect(peticion.request.params.has('categoria')).toBe(false);
      expect(peticion.request.params.has('etiqueta')).toBe(false);
      peticion.flush([evento('a')], { headers: { 'X-Total-Count': '1' } });
      await avanzar(fixture);

      expect(fixture.nativeElement.querySelectorAll('a.ev')).toHaveLength(1);
    });

    it('un 422 del listado se trata como «sin resultados», no como un fallo', async () => {
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      http.expectOne('/api/v1/public/event-categories').flush([]);
      http
        .expectOne((p) => p.url === '/api/v1/public/events')
        .flush({ detail: 'x' }, { status: 422, statusText: 'Unprocessable' });
      await avanzar(fixture);

      const texto: string = fixture.nativeElement.textContent;
      expect(texto).not.toContain('No hemos podido');
      expect(fixture.nativeElement.querySelector('app-alert')).toBeNull();
    });

    it('si el total no se puede leer y la página viene llena, «Ver más» sigue disponible', async () => {
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      http.expectOne('/api/v1/public/event-categories').flush([]);
      const llena = Array.from({ length: 24 }, (_, i) => evento(`e${i}`));
      // Sin cabecera `X-Total-Count` (p. ej. otro origen sin CORS).
      http.expectOne((p) => p.url === '/api/v1/public/events').flush(llena);
      await avanzar(fixture);

      const boton = [...fixture.nativeElement.querySelectorAll('button')].find(
        (b) => (b as HTMLElement).textContent?.trim() === 'Ver más',
      );
      expect(boton).toBeDefined();
    });

    it('avisa de que el buscador actúa sobre lo cargado mientras haya más páginas', async () => {
      const fixture = TestBed.createComponent(EventsListPage);
      fixture.detectChanges();
      responderListado(http, [evento('a')], [], 5);
      await avanzar(fixture);

      expect(fixture.nativeElement.textContent).toContain('actúan sobre los eventos ya cargados');
    });
  });
});
