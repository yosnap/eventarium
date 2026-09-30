import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { EventCategoriesPage } from './event-categories-page';

const CATEGORIAS = [
  { id: 'c1', slug: 'taller', name: 'Taller', display_order: 1, is_active: true },
  { id: 'c2', slug: 'vieja', name: 'Vieja', display_order: 2, is_active: false },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventCategoriesPage', () => {
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

  afterEach(() => http.verify());

  async function abrir(categorias: readonly object[] = CATEGORIAS) {
    const fixture = TestBed.createComponent(EventCategoriesPage);
    fixture.detectChanges();
    http.expectOne('/api/v1/admin/event-categories').flush(categorias);
    await avanzar(fixture);
    return fixture;
  }

  function botonPorTexto(raiz: HTMLElement, texto: string): HTMLButtonElement {
    const boton = [...raiz.querySelectorAll('button')].find((b) => b.textContent?.includes(texto));
    if (!boton) throw new Error(`No hay botón «${texto}»`);
    return boton;
  }

  it('lista el catálogo con su identificador y estado, sin violaciones de accesibilidad', async () => {
    const fixture = await abrir();
    const raiz: HTMLElement = fixture.nativeElement;

    expect(raiz.textContent).toContain('taller');
    expect(raiz.textContent).toContain('vieja');
    const casillas = [...raiz.querySelectorAll('input[type="checkbox"]')] as HTMLInputElement[];
    expect(casillas.map((c) => c.checked)).toEqual([true, false]);
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('sin categorías enseña el estado vacío', async () => {
    const fixture = await abrir([]);
    expect(fixture.nativeElement.textContent).toContain('Todavía no hay categorías');
  });

  it('crea una categoría y la añade a la lista ordenada', async () => {
    const fixture = await abrir();
    const raiz: HTMLElement = fixture.nativeElement;
    const campos = [...raiz.querySelectorAll('form input')] as HTMLInputElement[];
    campos[0].value = 'charla';
    campos[0].dispatchEvent(new Event('input'));
    campos[1].value = 'Charla';
    campos[1].dispatchEvent(new Event('input'));
    campos[2].value = '0';
    campos[2].dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (raiz.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
    await avanzar(fixture);
    const peticion = http.expectOne('/api/v1/admin/event-categories');
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toEqual({ slug: 'charla', name: 'Charla', display_order: 0 });
    peticion.flush({ id: 'c3', slug: 'charla', name: 'Charla', display_order: 0, is_active: true });
    await avanzar(fixture);

    const slugs = [...raiz.querySelectorAll('.fila__slug')].map((e) => e.textContent?.trim());
    expect(slugs).toEqual(['charla', 'taller', 'vieja']);
  });

  it('un identificador inválido se avisa sin llamar a la API', async () => {
    const fixture = await abrir();
    const raiz: HTMLElement = fixture.nativeElement;
    const campos = [...raiz.querySelectorAll('form input')] as HTMLInputElement[];
    campos[0].value = 'Con Mayúsculas';
    campos[0].dispatchEvent(new Event('input'));
    campos[1].value = 'Algo';
    campos[1].dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (raiz.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http.expectNone((p) => p.method === 'POST');
    expect(raiz.textContent).toContain('Usa minúsculas, números y guiones');
  });

  it('un identificador repetido muestra el motivo de la API', async () => {
    const fixture = await abrir();
    const raiz: HTMLElement = fixture.nativeElement;
    const campos = [...raiz.querySelectorAll('form input')] as HTMLInputElement[];
    campos[0].value = 'taller';
    campos[0].dispatchEvent(new Event('input'));
    campos[1].value = 'Otro';
    campos[1].dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (raiz.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
    await avanzar(fixture);
    http
      .expectOne('/api/v1/admin/event-categories')
      .flush(
        { detail: 'Ya existe una categoría con el identificador «taller».' },
        { status: 409, statusText: 'Conflict' },
      );
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Ya existe una categoría');
  });

  it('al guardar un orden nuevo la fila cambia de sitio en la lista', async () => {
    const fixture = await abrir();
    const raiz: HTMLElement = fixture.nativeElement;
    const orden = raiz.querySelectorAll(
      '.fila input:not([type="checkbox"])',
    )[1] as HTMLInputElement;
    orden.value = '9';
    orden.dispatchEvent(new Event('input'));
    await avanzar(fixture);
    botonPorTexto(raiz, 'Guardar').click();
    http
      .expectOne('/api/v1/admin/event-categories/c1')
      .flush({ ...CATEGORIAS[0], display_order: 9 });
    await avanzar(fixture);

    const slugs = [...raiz.querySelectorAll('.fila__slug')].map((e) => e.textContent?.trim());
    expect(slugs).toEqual(['vieja', 'taller']);
  });

  it('guarda los cambios de una fila (nombre, orden y activa) con PATCH', async () => {
    const fixture = await abrir();
    const raiz: HTMLElement = fixture.nativeElement;
    const guardar = botonPorTexto(raiz, 'Guardar');
    expect(guardar.disabled).toBe(true);

    const casilla = raiz.querySelector('.fila input[type="checkbox"]') as HTMLInputElement;
    casilla.click();
    await avanzar(fixture);
    expect(botonPorTexto(raiz, 'Guardar').disabled).toBe(false);
    botonPorTexto(raiz, 'Guardar').click();
    const peticion = http.expectOne('/api/v1/admin/event-categories/c1');
    expect(peticion.request.method).toBe('PATCH');
    expect(peticion.request.body).toEqual({ name: 'Taller', display_order: 1, is_active: false });
    peticion.flush({ ...CATEGORIAS[0], is_active: false });
    await avanzar(fixture);

    expect(botonPorTexto(raiz, 'Guardar').disabled).toBe(true);
  });
});
