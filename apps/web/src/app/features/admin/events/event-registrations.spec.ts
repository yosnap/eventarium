import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventRegistrations } from './event-registrations';

function pagina(items: unknown[] = ITEMS, total = items.length, offset = 0) {
  return { items, total, limit: 20, offset };
}

const ITEMS = [
  {
    id: 'r1',
    email: 'persona@example.com',
    full_name: 'Persona de Prueba',
    status: 'pending_approval',
    created_at: '2026-10-01T09:00:00Z',
    verified_at: '2026-10-01T09:05:00Z',
    confirmed_at: null,
    waitlist_promoted_at: null,
    waitlist_promotion_expires_at: null,
  },
];

const STATS = {
  initiated: 10,
  verified: 8,
  approved: 6,
  issued: 5,
  pending_approval: 1,
  confirmed: 5,
  rejected: 1,
  cancelled: 0,
  waitlisted: 1,
  verified_conversion_rate: 0.8,
  confirmed_conversion_rate: 0.5,
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** Flujo de peticiones que dispara el componente al iniciar: listado, estadísticas
 * y las preguntas del formulario de inscripción (subcomponente siempre presente). */
function flushCargaInicial(
  http: HttpTestingController,
  itemsPage: ReturnType<typeof pagina> = pagina(),
): void {
  http.expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations').flush(itemsPage);
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
    .flush(STATS);
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registration-questions')
    .flush([]);
}

describe('EventRegistrations', () => {
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

  it('lista las inscripciones con sus estadísticas y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('persona@example.com');
    expect(fixture.nativeElement.textContent).toContain('Persona de Prueba');
    expect(fixture.nativeElement.textContent).toContain('80.0%');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('la tabla usa app-data-table con caption y el estado va en un chip con texto', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    const contenedor = fixture.nativeElement.querySelector('app-data-table') as HTMLElement | null;
    expect(contenedor).not.toBeNull();
    const tabla = contenedor!.querySelector('table') as HTMLTableElement;
    expect(tabla.querySelector('caption')?.textContent?.trim()).toBeTruthy();
    expect(tabla.querySelectorAll('th[scope="col"]').length).toBe(4);

    const ranura = contenedor!.querySelector('.ranura-scroll') as HTMLElement;
    expect(ranura.getAttribute('tabindex')).toBe('0');
    expect(ranura.getAttribute('role')).toBe('region');

    // Cada estado lleva su texto: el tono solo lo refuerza.
    const chips = Array.from(contenedor!.querySelectorAll('app-chip .chip')) as HTMLElement[];
    expect(chips.length).toBeGreaterThan(0);
    for (const chip of chips) {
      expect(chip.textContent?.trim()).toBeTruthy();
    }
  });

  it('ofrece aprobar y rechazar una inscripción pendiente de aprobación, y refresca tras la acción', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    const botonAprobar = Array.from(fixture.nativeElement.querySelectorAll('button')).find(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Aprobar',
    ) as HTMLButtonElement | undefined;
    expect(botonAprobar).toBeTruthy();
    botonAprobar?.click();
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) =>
        peticion.url === '/api/v1/events/e1/registrations/r1/approve' && peticion.method === 'POST',
    );
    peticion.flush({ ...ITEMS[0], status: 'confirmed' });
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations')
      .flush(pagina([{ ...ITEMS[0], status: 'confirmed' }]));
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
      .flush(STATS);
    await avanzar(fixture);
  });

  it('filtra por estado con el segmentado y vuelve a pedir el listado', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    const grupo = fixture.nativeElement.querySelector('[role="group"]') as HTMLElement;
    const boton = Array.from(grupo.querySelectorAll('button')).find(
      (b) => (b as HTMLButtonElement).textContent?.trim() === 'Confirmadas',
    ) as HTMLButtonElement | undefined;
    expect(boton).toBeTruthy();
    boton?.click();
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/events/e1/registrations',
    );
    expect(peticion.request.params.get('status')).toBe('confirmed');
    peticion.flush(pagina([]));
    await avanzar(fixture);
  });

  it('la búsqueda filtra en cliente por nombre o email dentro de la página cargada', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(
      http,
      pagina([
        ITEMS[0],
        {
          ...ITEMS[0],
          id: 'r2',
          email: 'otra@example.com',
          full_name: 'Otra Persona',
        },
      ]),
    );
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Otra Persona');

    const busqueda = fixture.nativeElement.querySelector(
      'input[type="search"]',
    ) as HTMLInputElement;
    busqueda.value = 'persona de prueba';
    busqueda.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Persona de Prueba');
    expect(fixture.nativeElement.textContent).not.toContain('Otra Persona');
    // Sin recarga al servidor: es un filtro puramente cliente.
    http.expectNone((peticion) => peticion.url === '/api/v1/events/e1/registrations');
  });

  it('el rechazo abre un diálogo con el mensaje prellenado y envía el motivo', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    const nativo = fixture.nativeElement;
    const dialogo = nativo.querySelector('dialog') as HTMLDialogElement;
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      };
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      };
    }

    const botonRechazar = Array.from(nativo.querySelectorAll('button')).find(
      (b) => (b as HTMLButtonElement).textContent?.trim() === 'Rechazar',
    ) as HTMLButtonElement | undefined;
    expect(botonRechazar).toBeTruthy();
    botonRechazar?.click();
    await avanzar(fixture);

    expect(dialogo.hasAttribute('open')).toBe(true);
    const textarea = dialogo.querySelector('textarea') as HTMLTextAreaElement;
    expect(textarea.value).toContain('Gracias por tu interés');

    const botonConfirmar = Array.from(dialogo.querySelectorAll('button')).find(
      (b) => (b as HTMLButtonElement).textContent?.trim() === 'Rechazar y avisar',
    ) as HTMLButtonElement | undefined;
    botonConfirmar?.click();
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/events/e1/registrations/r1/reject',
    );
    expect(peticion.request.body.reason).toContain('Gracias por tu interés');
    peticion.flush({ ...ITEMS[0], status: 'rejected' });
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations')
      .flush(pagina([{ ...ITEMS[0], status: 'rejected' }]));
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
      .flush(STATS);
    await avanzar(fixture);

    expect(dialogo.hasAttribute('open')).toBe(false);
  });

  it('el rechazo con el mensaje vaciado envía reason: null, no una cadena vacía', async () => {
    const fixture = TestBed.createComponent(EventRegistrations);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);
    flushCargaInicial(http);
    await avanzar(fixture);

    const nativo = fixture.nativeElement;
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      };
      HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      };
    }

    const botonRechazar = Array.from(nativo.querySelectorAll('button')).find(
      (b) => (b as HTMLButtonElement).textContent?.trim() === 'Rechazar',
    ) as HTMLButtonElement | undefined;
    botonRechazar?.click();
    await avanzar(fixture);

    const dialogo = nativo.querySelector('dialog') as HTMLDialogElement;
    const textarea = dialogo.querySelector('textarea') as HTMLTextAreaElement;
    // Vacía el mensaje prellenado: un rechazo silencioso, sin motivo.
    textarea.value = '   ';
    textarea.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    const botonConfirmar = Array.from(dialogo.querySelectorAll('button')).find(
      (b) => (b as HTMLButtonElement).textContent?.trim() === 'Rechazar y avisar',
    ) as HTMLButtonElement | undefined;
    botonConfirmar?.click();
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/events/e1/registrations/r1/reject',
    );
    expect(peticion.request.body.reason).toBeNull();
    peticion.flush({ ...ITEMS[0], status: 'rejected' });
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations')
      .flush(pagina([{ ...ITEMS[0], status: 'rejected' }]));
    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
      .flush(STATS);
    await avanzar(fixture);
  });

  it('no tiene violaciones de accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    try {
      const fixture = TestBed.createComponent(EventRegistrations);
      fixture.componentRef.setInput('eventId', 'e1');
      await avanzar(fixture);
      flushCargaInicial(http);
      await avanzar(fixture);

      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });
});
