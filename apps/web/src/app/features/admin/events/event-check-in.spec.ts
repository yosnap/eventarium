import 'fake-indexeddb/auto';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { OfflineScanQueueService } from '../../../core/tickets/offline-scan-queue.service';
import { EventCheckIn } from './event-check-in';

/**
 * `whenStable()` no espera una promesa de RxJS (`firstValueFrom`) suelta ni
 * una vuelta real de IndexedDB (`fake-indexeddb` despacha sus eventos como
 * tareas del bucle de eventos, no microtasks) — ninguna de las dos se
 * registra en el `PendingTasks` de Angular. Un `setTimeout` real cubre
 * ambos huecos sin depender de cuántos microtasks hagan falta.
 */
async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
  // `sincronizar()` encadena varias vueltas reales de IndexedDB (leer
  // pendientes, borrar cada uno, releer el recuento) — varias rondas de
  // `setTimeout` cubren esa cadena sin depender de contar cuántas hacen falta.
  for (let vuelta = 0; vuelta < 4; vuelta += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();
  }
}

async function crearComponente(eventId = 'e1'): Promise<ComponentFixture<EventCheckIn>> {
  const fixture = TestBed.createComponent(EventCheckIn);
  fixture.componentRef.setInput('eventId', eventId);
  await avanzar(fixture);
  return fixture;
}

/** Deja al componente sin cámara real (no existe en jsdom) sin que rompa el
 * arranque: el resto del flujo se prueba llamando a `encolarEscaneo`
 * directamente, como si un dispositivo real ya hubiera decodificado un QR. */
function silenciarCargaInicial(http: HttpTestingController): void {
  http
    .expectOne((peticion) => peticion.url === '/api/v1/events/e1/registrations/stats')
    .flush({
      initiated: 10,
      verified: 10,
      pending_approval: 0,
      confirmed: 8,
      rejected: 0,
      cancelled: 0,
      waitlisted: 0,
      verified_conversion_rate: 1,
      confirmed_conversion_rate: 0.8,
    });
}

describe('EventCheckIn', () => {
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
    // jsdom no implementa `getUserMedia`: se simula ausente para que la
    // página muestre el aviso y siga funcionando por búsqueda manual/cola.
    Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true });
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  });

  afterEach(async () => {
    http.verify();
    vi.restoreAllMocks();
    // La cola de IndexedDB es un almacén global de `fake-indexeddb`, no algo
    // que `TestBed` reinicie entre pruebas: se vacía a mano para que un
    // escaneo de un test no contamine el contador de «pendientes» del
    // siguiente.
    const cola = TestBed.inject(OfflineScanQueueService);
    for (const pendiente of await cola.pending()) {
      await cola.remove(pendiente.clientScanId);
    }
  });

  it('no tiene violaciones de accesibilidad en el estado inicial', async () => {
    const fixture = await crearComponente();
    silenciarCargaInicial(http);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('8');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('encola un escaneo mientras está sin conexión y lo sincroniza al recuperarla', async () => {
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    const fixture = await crearComponente();
    const componente = fixture.componentInstance as unknown as {
      encolarEscaneo(token: string): Promise<void>;
    };
    silenciarCargaInicial(http);
    await avanzar(fixture);

    await componente.encolarEscaneo('token-sin-conexion');
    await avanzar(fixture);

    // Sin conexión: no debe intentar sincronizar todavía.
    http.expectNone((peticion) => peticion.url === '/api/v1/events/e1/tickets/scan/batch');
    expect(fixture.nativeElement.textContent).toContain('1');

    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    window.dispatchEvent(new Event('online'));
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/events/e1/tickets/scan/batch',
    );
    expect(peticion.request.body.scans).toHaveLength(1);
    expect(peticion.request.body.scans[0].client_scan_id).toBeTruthy();
    peticion.flush([
      {
        client_scan_id: peticion.request.body.scans[0].client_scan_id,
        result: 'valid',
        ticket_id: 't1',
        registration_id: 'r1',
        full_name: 'Persona de Prueba',
        email: 'persona@example.com',
        used_at: '2026-09-08T10:00:00Z',
        used_by_event_member_id: 'm1',
      },
    ]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Persona de Prueba');
  });

  it('un resultado duplicate muestra quién y cuándo hizo el primer check-in', async () => {
    const fixture = await crearComponente();
    const componente = fixture.componentInstance as unknown as {
      encolarEscaneo(token: string): Promise<void>;
    };
    silenciarCargaInicial(http);
    await avanzar(fixture);

    await componente.encolarEscaneo('token-duplicado');
    await avanzar(fixture);

    const peticion = http.expectOne(
      (peticion) => peticion.url === '/api/v1/events/e1/tickets/scan/batch',
    );
    peticion.flush([
      {
        client_scan_id: peticion.request.body.scans[0].client_scan_id,
        result: 'duplicate',
        ticket_id: 't1',
        registration_id: 'r1',
        full_name: 'Persona Duplicada',
        email: 'duplicada@example.com',
        used_at: '2026-09-08T09:30:00Z',
        used_by_event_member_id: 'm2',
      },
    ]);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Persona Duplicada');
    expect(texto).not.toContain('ya usado');
    expect(texto).toMatch(/Usada el/);
    expect(texto).toContain('m2');
  });

  it('busca inscripciones confirmadas y ofrece marcar el check-in manual', async () => {
    const fixture = await crearComponente();
    silenciarCargaInicial(http);
    await avanzar(fixture);

    const campo = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    campo.value = 'persona';
    campo.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    const formulario = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    formulario.dispatchEvent(new Event('submit', { cancelable: true }));
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/tickets/search')
      .flush([
        {
          ticket_id: 't1',
          registration_id: 'r1',
          full_name: 'Persona Buscada',
          email: 'buscada@example.com',
          used_at: null,
        },
      ]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Persona Buscada');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as HTMLButtonElement[];
    const marcar = botones.find((boton) => boton.textContent?.includes('Marcar entrada'));
    marcar?.click();
    await avanzar(fixture);

    http
      .expectOne((peticion) => peticion.url === '/api/v1/events/e1/tickets/t1/check-in-manual')
      .flush({
        client_scan_id: 'manual-1',
        result: 'manual',
        ticket_id: 't1',
        registration_id: 'r1',
        full_name: 'Persona Buscada',
        email: 'buscada@example.com',
        used_at: '2026-09-08T11:00:00Z',
        used_by_event_member_id: 'm1',
      });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('check-in manual');
  });
});
