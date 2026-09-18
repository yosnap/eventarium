import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { EventDesign } from './event-design';

const TOKENS_PLANTILLA = {
  dark: {
    bg: '#0a0a0a',
    surface: '#181818',
    fg: '#f0f0f0',
    accent: '#22c55e',
    'on-accent': '#000000',
  },
  light: {
    bg: '#ffffff',
    surface: '#f5f5f5',
    fg: '#161616',
    accent: '#16a34a',
    'on-accent': '#ffffff',
  },
};

function plantillas() {
  return [
    {
      id: 'p1',
      key: 'bosque',
      name: 'Bosque',
      tokens: TOKENS_PLANTILLA,
      is_default: true,
      default_mode: 'dark',
    },
    {
      id: 'p2',
      key: 'editorial',
      name: 'Editorial',
      tokens: TOKENS_PLANTILLA,
      is_default: false,
      default_mode: 'light',
    },
  ];
}

function eventoBase(overrides: Partial<{ theme_template_id: string | null }> = {}) {
  return {
    id: 'e1',
    theme_template_id: overrides.theme_template_id ?? null,
    theme_overrides: null,
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  // `cargar()` encadena un `Promise.all` de tres `firstValueFrom`: más saltos
  // de microtarea que el único `await` de otras pantallas, así que un solo
  // `whenStable()` no basta para que el `finally` (cargando=false) se
  // ejecute antes de leer el DOM.
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  fixture.detectChanges();
}

function flushCarga(
  http: HttpTestingController,
  opciones: {
    plantillasDevueltas?: unknown;
    brandingThemeId?: string | null;
    evento?: unknown;
  } = {},
): void {
  http
    .expectOne((p) => p.url === '/api/v1/organizations/me/theme-templates')
    .flush(opciones.plantillasDevueltas ?? plantillas());
  http
    .expectOne((p) => p.url === '/api/v1/organizations/me/branding')
    .flush({ theme_template_id: opciones.brandingThemeId ?? null });
  http.expectOne((p) => p.url === '/api/v1/events/e1').flush(opciones.evento ?? eventoBase());
}

describe('EventDesign', () => {
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
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('muestra el grid de plantillas y marca la activa (heredada del catálogo por defecto)', async () => {
    const fixture = TestBed.createComponent(EventDesign);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCarga(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('Bosque');
    expect(raiz.textContent).toContain('Editorial');
    const activa = raiz.querySelector('.plantilla-activa');
    expect(activa?.textContent).toContain('Bosque');

    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('clic en una tarjeta no activa aplica la plantilla con PATCH inmediato', async () => {
    const fixture = TestBed.createComponent(EventDesign);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCarga(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const botones = Array.from(raiz.querySelectorAll('.plantilla-tarjeta'));
    const editorial = botones.find((b) =>
      b.textContent?.includes('Editorial'),
    ) as HTMLButtonElement;
    editorial.click();
    await avanzar(fixture);

    const peticion = http.expectOne((p) => p.url === '/api/v1/events/e1' && p.method === 'PATCH');
    expect(peticion.request.body).toEqual({ theme_template_id: 'p2' });
    peticion.flush({ ...eventoBase({ theme_template_id: 'p2' }) });
    await avanzar(fixture);

    expect(raiz.querySelector('.plantilla-activa')?.textContent).toContain('Editorial');
    expect(raiz.textContent).toContain('Aplicada');
  });

  it('cambiar de fuente vacía un debounce de color pendiente antes de aplicar la fuente', async () => {
    // `shouldAdvanceTime` deja que el reloj avance con el tiempo real entre
    // ticks: si no, `fixture.whenStable()` (que depende de temporizadores
    // internos del planificador zoneless) se queda colgado para siempre.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const fixture = TestBed.createComponent(EventDesign);
      fixture.componentRef.setInput('eventId', 'e1');
      await avanzar(fixture);
      flushCarga(http);
      await avanzar(fixture);

      const raiz = fixture.nativeElement as HTMLElement;
      const colorInput = raiz.querySelector('input[type="color"]') as HTMLInputElement;
      colorInput.value = '#3b82f6';
      colorInput.dispatchEvent(new Event('input'));
      await avanzar(fixture);

      // Antes de que venza el debounce (400ms), se cambia la fuente: debe
      // forzar el envío del color pendiente primero. `app-select` es un
      // combobox propio (botón + listbox), no un `<select>` nativo: hay que
      // abrirlo y pulsar una opción, igual que haría una persona.
      const botonFuenteTitulo = raiz.querySelector(
        '#event-design-fuente-titulo',
      ) as HTMLButtonElement;
      botonFuenteTitulo.click();
      await avanzar(fixture);
      const opcionFuenteTitulo = raiz.querySelector(
        '#event-design-fuente-titulo-lista .sel__o:nth-child(2)',
      ) as HTMLLIElement;
      const fuenteElegida = opcionFuenteTitulo.textContent?.trim() ?? '';
      opcionFuenteTitulo.click();
      await avanzar(fixture);

      const peticionColor = http.expectOne(
        (p) => p.url === '/api/v1/events/e1' && p.method === 'PATCH',
      );
      expect(peticionColor.request.body).toEqual({ theme_overrides: { accent: '#3b82f6' } });
      peticionColor.flush({
        ...eventoBase(),
        theme_overrides: { accent: '#3b82f6' },
      });
      await avanzar(fixture);

      const peticionFuente = http.expectOne(
        (p) => p.url === '/api/v1/events/e1' && p.method === 'PATCH',
      );
      expect(peticionFuente.request.body).toEqual({
        theme_overrides: { accent: '#3b82f6', 'font-display': fuenteElegida },
      });
      peticionFuente.flush({
        ...eventoBase(),
        theme_overrides: { accent: '#3b82f6', 'font-display': fuenteElegida },
      });
      await avanzar(fixture);
    } finally {
      vi.useRealTimers();
    }
  });

  it('un PATCH fallido muestra el error y no corrompe el estado local', async () => {
    const fixture = TestBed.createComponent(EventDesign);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCarga(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const editorial = Array.from(raiz.querySelectorAll('.plantilla-tarjeta')).find((b) =>
      b.textContent?.includes('Editorial'),
    ) as HTMLButtonElement;
    editorial.click();
    await avanzar(fixture);

    http
      .expectOne((p) => p.url === '/api/v1/events/e1' && p.method === 'PATCH')
      .flush({ detail: 'No tienes permiso.' }, { status: 403, statusText: 'Forbidden' });
    await avanzar(fixture);

    expect(raiz.querySelector('.plantilla-activa')?.textContent).toContain('Bosque');
  });

  it('encolar una plantilla no pierde una personalización ya en cola detrás de otro PATCH en vuelo', async () => {
    // Escenario de red-team (fase 3): PATCH1 (color) en vuelo, PATCH2
    // (fuente, ya combinada con el accent) esperando en la cola de un
    // elemento, y ANTES de que PATCH1 responda el usuario hace clic en
    // otra plantilla. La cola de un elemento no debe descartar PATCH2 —
    // el backend acepta `theme_template_id` y `theme_overrides` en el
    // mismo PATCH, así que la plantilla y la personalización pendientes
    // se funden en un único PATCH siguiente. Las tarjetas de plantilla se
    // deshabilitan en el DOM mientras hay una acción en vuelo
    // (`[disabled]="accionEnCurso() !== null"`), así que un `.click()` real
    // no llega a disparar el clic — se invoca `elegirPlantilla` en el
    // componente directamente para probar la máquina de estados de la cola
    // en sí (la protección de la lógica no debe depender solo de que el
    // botón esté deshabilitado en el DOM).
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const fixture = TestBed.createComponent(EventDesign);
      fixture.componentRef.setInput('eventId', 'e1');
      await avanzar(fixture);
      flushCarga(http);
      await avanzar(fixture);

      const raiz = fixture.nativeElement as HTMLElement;

      // PATCH1: color, queda en vuelo (no se flushea todavía).
      const colorInput = raiz.querySelector('input[type="color"]') as HTMLInputElement;
      colorInput.value = '#3b82f6';
      colorInput.dispatchEvent(new Event('input'));
      vi.advanceTimersByTime(400);
      await avanzar(fixture);
      const peticionColor = http.expectOne(
        (p) => p.url === '/api/v1/events/e1' && p.method === 'PATCH',
      );
      expect(peticionColor.request.body).toEqual({ theme_overrides: { accent: '#3b82f6' } });

      // Con PATCH1 todavía en vuelo, cambia la fuente: se encola como PATCH2.
      const botonFuenteTitulo = raiz.querySelector(
        '#event-design-fuente-titulo',
      ) as HTMLButtonElement;
      botonFuenteTitulo.click();
      await avanzar(fixture);
      const opcionFuenteTitulo = raiz.querySelector(
        '#event-design-fuente-titulo-lista .sel__o:nth-child(2)',
      ) as HTMLLIElement;
      const fuenteElegida = opcionFuenteTitulo.textContent?.trim() ?? '';
      opcionFuenteTitulo.click();
      await avanzar(fixture);

      // Con PATCH1 aún en vuelo y PATCH2 en cola, clic en otra plantilla
      // (invocando el método directamente: el botón está deshabilitado en
      // el DOM mientras `accionEnCurso()` no sea null, ver comentario
      // arriba).
      const editorialInterno = plantillas()[1];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (fixture.componentInstance as any).elegirPlantilla(editorialInterno);
      await avanzar(fixture);

      // Se resuelve PATCH1 (color).
      peticionColor.flush({ ...eventoBase(), theme_overrides: { accent: '#3b82f6' } });
      await avanzar(fixture);

      // El siguiente PATCH debe llevar la plantilla Y la personalización de
      // fuente/color pendientes — ninguno de los dos cambios puede perderse.
      const peticionSiguiente = http.expectOne(
        (p) => p.url === '/api/v1/events/e1' && p.method === 'PATCH',
      );
      expect(peticionSiguiente.request.body).toEqual({
        theme_template_id: 'p2',
        theme_overrides: { accent: '#3b82f6', 'font-display': fuenteElegida },
      });
      peticionSiguiente.flush({
        ...eventoBase({ theme_template_id: 'p2' }),
        theme_overrides: { accent: '#3b82f6', 'font-display': fuenteElegida },
      });
      await avanzar(fixture);
    } finally {
      vi.useRealTimers();
    }
  });

  it('un color acromático se rechaza en cliente sin llegar a la red', async () => {
    const fixture = TestBed.createComponent(EventDesign);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCarga(http);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const colorInput = raiz.querySelector('input[type="color"]') as HTMLInputElement;
    colorInput.value = '#808080';
    colorInput.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    expect(raiz.textContent).toContain('saturación');
    http.expectNone((p) => p.url === '/api/v1/events/e1' && p.method === 'PATCH');
  });
});
