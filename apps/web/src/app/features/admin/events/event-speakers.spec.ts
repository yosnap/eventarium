import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventSpeakers } from './event-speakers';

const BASE = '/api/v1/events/e1';

const HTMLDialogElement_original = HTMLDialogElement.prototype.showModal;
const HTMLDialogElement_close = HTMLDialogElement.prototype.close;

beforeEach(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      this.removeAttribute('open');
    };
  }
});

afterEach(() => {
  HTMLDialogElement.prototype.showModal = HTMLDialogElement_original;
  HTMLDialogElement.prototype.close = HTMLDialogElement_close;
});

function vista() {
  return {
    items: [
      {
        organization_member_id: 'om1',
        user_id: 'u1',
        email: 'ana@example.com',
        first_name: 'Ana',
        last_name: 'García',
        titular: 'Plataformas de datos',
        sesiones: [{ id: 's1', titulo: 'Poner un modelo en producción', starts_at: null }],
        completitud: {
          porcentaje: 100,
          rellenas: 6,
          total: 6,
          faltantes: [],
        },
        ediciones: 3,
        public_slug: 'ana-garcia',
      },
      {
        organization_member_id: 'om2',
        user_id: 'u2',
        email: 'roberto@example.com',
        first_name: 'Roberto',
        last_name: 'Beltrán',
        titular: null,
        sesiones: [],
        completitud: {
          porcentaje: 33,
          rellenas: 2,
          total: 6,
          faltantes: ['bio', 'curriculum', 'web', 'contacto'],
        },
        ediciones: 1,
        public_slug: null,
      },
    ],
    total_sesiones: 18,
  };
}

function historial() {
  return [{ evento_titulo: 'IAWIC 2025', rol: 'speaker', fecha: null }];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function flushCarga(http: HttpTestingController): void {
  http.expectOne((p) => p.url === `${BASE}/speakers` && p.method === 'GET').flush(vista());
}

describe('EventSpeakers', () => {
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

  it('renderiza KPIs, tabla y acciones sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventSpeakers);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    // KPIs con datos reales de la vista sembrada.
    expect(texto).toContain('En el programa');
    expect(texto).toContain('De 18 sesiones');
    expect(texto).toContain('Sin bio');
    // Cabecera: una persona sin bio.
    expect(texto).toContain('ficha le falta bio para publicarse');
    // Monograma derivado del nombre.
    const monogramas = fixture.nativeElement.querySelectorAll(
      '.monograma',
    ) as NodeListOf<HTMLElement>;
    expect(monogramas[0].textContent?.trim()).toBe('AG');
    // Sesión asignada del primer ponente.
    expect(texto).toContain('Poner un modelo en producción');
    // Chip «Sin asignar» del segundo.
    expect(texto).toContain('Sin asignar');

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el filtro segmentado de «Sin sesión» deja solo a quien no tiene sesión', async () => {
    const fixture = TestBed.createComponent(EventSpeakers);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzar(fixture);

    const boton = (
      Array.from(
        fixture.nativeElement.querySelectorAll('[role="group"] button'),
      ) as HTMLButtonElement[]
    ).find((b) => b.textContent?.trim() === 'Sin sesión');
    expect(boton).toBeDefined();
    boton!.click();
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Roberto');
    expect(texto).not.toContain('Ana');
  });

  it('la búsqueda por nombre filtra en cliente', async () => {
    const fixture = TestBed.createComponent(EventSpeakers);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzar(fixture);

    const entrada = fixture.nativeElement.querySelector('input[type="search"]') as HTMLInputElement;
    entrada.value = 'Ana';
    entrada.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Ana');
    expect(texto).not.toContain('Roberto');
  });

  it('pedir bio hace POST al endpoint del ponente', async () => {
    const fixture = TestBed.createComponent(EventSpeakers);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzar(fixture);

    const botones = (
      Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[]
    ).filter((b) => b.textContent?.includes('Pedir bio'));
    expect(botones.length).toBe(1);
    botones[0].click();

    const peticion = http.expectOne(
      (p) => p.url === `${BASE}/speakers/om2/pedir-bio` && p.method === 'POST',
    );
    peticion.flush(null, { status: 204, statusText: 'No Content' });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain(
      'Recordatorio enviado para que complete su ficha.',
    );
  });

  it('el historial abre un diálogo con las participaciones pasadas', async () => {
    const fixture = TestBed.createComponent(EventSpeakers);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzar(fixture);

    const boton = (
      Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[]
    ).find((b) => b.textContent?.includes('Historial'));
    expect(boton).toBeDefined();
    boton!.click();

    http
      .expectOne((p) => p.url === `${BASE}/speakers/u1/historial` && p.method === 'GET')
      .flush(historial());
    await avanzar(fixture);

    const dialogo = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    expect(dialogo.open).toBe(true);
    expect(dialogo.textContent).toContain('IAWIC 2025');
    expect(dialogo.textContent).toContain('Ponente');
  });
});
