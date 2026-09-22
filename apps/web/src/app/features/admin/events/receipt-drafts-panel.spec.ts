import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import type { ReceiptDraft } from './accounting-types';
import { ReceiptDraftsPanel } from './receipt-drafts-panel';

const LISTADO = '/api/v1/accounting/events/e1/expense-drafts';

function draft(sobreescritura: Partial<ReceiptDraft> = {}): ReceiptDraft {
  return {
    id: 'd1',
    event_id: 'e1',
    status: 'pending_extraction',
    error_code: null,
    ocr_provider: 'ai_gateway',
    receipt_object_key: 'orgs/o1/accounting-receipts/abc.pdf',
    rasterized_object_key: null,
    extracted_fields: {
      provider_name: null,
      expense_date: null,
      base_cents: null,
      vat_cents: null,
      total_cents: null,
      currency: null,
    },
    field_confidence: {},
    attempts: 0,
    confirmed_expense_id: null,
    created_at: '2026-09-05T10:00:00Z',
    ...sobreescritura,
  };
}

function listo(id: string): ReceiptDraft {
  return draft({
    id,
    status: 'pending_review',
    ocr_provider: 'openai/gpt-4o-mini',
    extracted_fields: {
      provider_name: 'Catering SL',
      expense_date: '2026-09-05',
      base_cents: 10_000,
      vat_cents: 2_100,
      total_cents: 12_100,
      currency: 'EUR',
    },
    field_confidence: {
      provider_name: 'alta',
      expense_date: 'alta',
      base_cents: 'alta',
      vat_cents: 'alta',
      total_cents: 'alta',
      currency: 'alta',
    },
  });
}

function fallido(id: string, codigo: string): ReceiptDraft {
  return draft({
    id,
    status: 'extraction_failed',
    error_code: codigo,
    ocr_provider: 'openai/gpt-4o-mini',
    attempts: 1,
  });
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function montar(borradores: ReceiptDraft[]): Promise<ComponentFixture<ReceiptDraftsPanel>> {
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(ReceiptDraftsPanel);
  fixture.componentRef.setInput('eventId', 'e1');
  fixture.componentRef.setInput('partidas', [{ id: 'p1', name: 'Catering' }]);
  fixture.detectChanges();
  await avanzar(fixture);
  http.expectOne(LISTADO).flush(borradores);
  await avanzar(fixture);
  return fixture;
}

function botonPorTexto(fixture: ComponentFixture<unknown>, texto: string): HTMLButtonElement {
  const botones = Array.from(
    fixture.nativeElement.querySelectorAll('button'),
  ) as HTMLButtonElement[];
  const encontrado = botones.find((boton) => boton.textContent?.includes(texto));
  expect(encontrado, `No hay ningún botón con «${texto}»`).toBeTruthy();
  return encontrado!;
}

describe('ReceiptDraftsPanel', () => {
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
        provideRouter([]),
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('agrupa los borradores por estado con su recuento y no lista los cerrados', async () => {
    const fixture = await montar([
      draft({ id: 'd1' }),
      listo('d2'),
      fallido('d3', 'proveedor_error'),
      draft({ id: 'd4', status: 'confirmed' }),
      draft({ id: 'd5', status: 'discarded' }),
    ]);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Leyendo (1)');
    expect(texto).toContain('Pendientes de revisión (1)');
    expect(texto).toContain('Extracción fallida (1)');
    // Un solo formulario de revisión: el confirmado y el descartado no salen.
    expect(fixture.nativeElement.querySelectorAll('app-receipt-review-form').length).toBe(1);
  });

  it('muestra con qué modelo efectivo se leyó cada borrador', async () => {
    const fixture = await montar([listo('d2'), draft({ id: 'd1' })]);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Leído con openai/gpt-4o-mini');
    // Mientras está pendiente, el modelo todavía no se sabe: no se inventa.
    expect(texto).toContain('Todavía sin leer');
  });

  it('pregunta con retroceso mientras haya una extracción en curso y para cuando termina', async () => {
    vi.useFakeTimers();
    const fixture = await montar([draft({ id: 'd1' })]);

    // Primera espera: 2 s.
    await vi.advanceTimersByTimeAsync(1999);
    http.expectNone(LISTADO);
    await vi.advanceTimersByTimeAsync(1);
    http.expectOne(LISTADO).flush([draft({ id: 'd1' })]);
    await avanzar(fixture);

    // Segunda espera: 4 s (retroceso), no otros 2 s.
    await vi.advanceTimersByTimeAsync(3999);
    http.expectNone(LISTADO);
    await vi.advanceTimersByTimeAsync(1);
    http.expectOne(LISTADO).flush([listo('d1')]);
    await avanzar(fixture);

    // Ya no queda ninguna extracción en curso: se deja de preguntar.
    await vi.advanceTimersByTimeAsync(60_000);
    http.expectNone(LISTADO);
  });

  it('no deja temporizadores huérfanos al destruir el componente', async () => {
    vi.useFakeTimers();
    const fixture = await montar([draft({ id: 'd1' })]);

    fixture.destroy();
    await vi.advanceTimersByTimeAsync(120_000);
    http.expectNone(LISTADO);
  });

  it('una pasada del polling no borra lo que se está corrigiendo en un borrador', async () => {
    vi.useFakeTimers();
    // Uno listo para revisar y otro todavía extrayendo: el polling sigue vivo
    // mientras la persona corrige el primero.
    const fixture = await montar([listo('d1'), draft({ id: 'd2' })]);

    const proveedor = fixture.nativeElement.querySelector(
      '#draft-d1-proveedor',
    ) as HTMLInputElement;
    proveedor.value = 'Corregido SL';
    proveedor.dispatchEvent(new Event('input'));

    await vi.advanceTimersByTimeAsync(2000);
    http.expectOne(LISTADO).flush([listo('d1'), draft({ id: 'd2' })]);
    await avanzar(fixture);

    const despues = fixture.nativeElement.querySelector('#draft-d1-proveedor') as HTMLInputElement;
    expect(despues.value).toBe('Corregido SL');
  });

  it('una pasada del polling no vuelve a descargar la previsualización', async () => {
    vi.useFakeTimers();
    const conImagen = draft({
      ...listo('d1'),
      rasterized_object_key: 'orgs/o1/accounting-receipts/abc.png',
    });
    const RECIBO = '/api/v1/accounting/receipts/orgs/o1/accounting-receipts/abc.png';
    const fixture = await montar([conImagen, draft({ id: 'd2' })]);
    http.expectOne(RECIBO).flush(new Blob(['x']));
    await avanzar(fixture);

    await vi.advanceTimersByTimeAsync(2000);
    http.expectOne(LISTADO).flush([{ ...conImagen }, draft({ id: 'd2' })]);
    await avanzar(fixture);

    http.expectNone(RECIBO);
  });

  it('no reanuda el polling si se destruye con una petición de listado en vuelo', async () => {
    vi.useFakeTimers();
    const fixture = TestBed.createComponent(ReceiptDraftsPanel);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.componentRef.setInput('partidas', []);
    fixture.detectChanges();
    await fixture.whenStable();

    // Se destruye con el listado todavía sin responder: al llegar la respuesta
    // no puede programar la siguiente consulta.
    const enVuelo = http.expectOne(LISTADO);
    fixture.destroy();
    enVuelo.flush([draft({ id: 'd1' })]);
    await vi.advanceTimersByTimeAsync(120_000);

    http.expectNone(LISTADO);
  });

  it('no muestra un error si se destruye con una petición de listado en vuelo que falla', async () => {
    const fixture = TestBed.createComponent(ReceiptDraftsPanel);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.componentRef.setInput('partidas', []);
    fixture.detectChanges();
    await fixture.whenStable();

    // Se destruye con el listado todavía sin responder: al llegar el fallo
    // no puede pintar un error en un componente que ya no existe.
    const enVuelo = http.expectOne(LISTADO);
    fixture.destroy();
    enVuelo.flush(
      { detail: 'No hemos podido cargar los justificantes.' },
      { status: 500, statusText: 'Error' },
    );

    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
  });

  it('lleva el foco al primer campo del borrador que acaba de quedar listo', async () => {
    vi.useFakeTimers();
    const fixture = await montar([draft({ id: 'd1' })]);

    await vi.advanceTimersByTimeAsync(2000);
    http.expectOne(LISTADO).flush([listo('d1')]);
    await avanzar(fixture);

    expect(document.activeElement).toBe(fixture.nativeElement.querySelector('#draft-d1-proveedor'));
  });

  it('«presupuesto de IA agotado» es el único error con botón de reintentar', async () => {
    const fixture = await montar([
      fallido('d1', 'limite_superado'),
      fallido('d2', 'proveedor_error'),
    ]);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Presupuesto de IA agotado, amplía el límite.');
    expect(texto).toContain('El proveedor de IA ha fallado');

    const reintentos = Array.from(fixture.nativeElement.querySelectorAll('button')).filter(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Reintentar',
    );
    expect(reintentos.length).toBe(1);
  });

  it('un error_code fuera de la taxonomía cae en el mensaje genérico, sin reintentar', async () => {
    const fixture = await montar([fallido('d1', 'algo_que_no_existe')]);

    expect(fixture.nativeElement.textContent).toContain('No hemos podido leer este justificante');
    const reintentos = Array.from(fixture.nativeElement.querySelectorAll('button')).filter(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Reintentar',
    );
    expect(reintentos.length).toBe(0);
  });

  it('reintentar reencola la extracción y vuelve a cargar el listado', async () => {
    const fixture = await montar([fallido('d1', 'limite_superado')]);

    botonPorTexto(fixture, 'Reintentar').click();
    await avanzar(fixture);

    http.expectOne('/api/v1/accounting/expense-drafts/d1/retry').flush({ id: 'd1' });
    await avanzar(fixture);
    http.expectOne(LISTADO).flush([draft({ id: 'd1' })]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Leyendo (1)');
  });

  it('con varios límites superados ofrece reintentarlos todos', async () => {
    const fixture = await montar([
      fallido('d1', 'limite_superado'),
      fallido('d2', 'limite_superado'),
    ]);

    botonPorTexto(fixture, 'Reintentar todos').click();
    await avanzar(fixture);

    // Un reintento por borrador y **una sola** recarga del listado al final.
    http.expectOne('/api/v1/accounting/expense-drafts/d1/retry').flush({ id: 'd1' });
    await avanzar(fixture);
    http.expectNone(LISTADO);
    http.expectOne('/api/v1/accounting/expense-drafts/d2/retry').flush({ id: 'd2' });
    await avanzar(fixture);
    http.expectOne(LISTADO).flush([]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Todavía no hay ningún justificante');
  });

  it('los errores de configuración enlazan al panel de IA de la organización', async () => {
    const fixture = await montar([fallido('d1', 'sin_configuracion')]);

    const enlace = fixture.nativeElement.querySelector('a[href="/dashboard/ia"]');
    expect(enlace).not.toBeNull();
  });

  it('confirmar un borrador avisa hacia arriba y lo saca de la bandeja', async () => {
    const fixture = await montar([listo('d1')]);
    let aviso: string | null = null;
    fixture.componentInstance.gastoCreado.subscribe((mensaje) => (aviso = mensaje));

    const formulario = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    formulario.dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http.expectOne('/api/v1/accounting/expense-drafts/d1/confirm').flush({ id: 'g1' });
    await avanzar(fixture);

    // No se vuelve a pedir el listado: el servidor acaba de decir que ese
    // borrador ya es un gasto.
    http.expectNone(LISTADO);
    expect(aviso).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Todavía no hay ningún justificante');
  });

  it('si el listado falla lo dice, deja de preguntar y ofrece actualizar', async () => {
    const fixture = TestBed.createComponent(ReceiptDraftsPanel);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.componentRef.setInput('partidas', []);
    fixture.detectChanges();
    await avanzar(fixture);
    http
      .expectOne(LISTADO)
      .flush(
        { detail: 'No hemos podido cargar los justificantes.' },
        { status: 500, statusText: 'Error' },
      );
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    // Con el listado fallando no queda ningún temporizador pendiente: seguir
    // con el retroceso solo acumularía errores.
    vi.useFakeTimers();
    await vi.advanceTimersByTimeAsync(60_000);
    http.expectNone(LISTADO);
    vi.useRealTimers();

    botonPorTexto(fixture, 'Actualizar').click();
    await avanzar(fixture);
    http.expectOne(LISTADO).flush([]);
    await avanzar(fixture);
  });

  it('anuncia en una región aria-live que hay una extracción en curso', async () => {
    const fixture = await montar([draft({ id: 'd1' })]);

    const regiones = Array.from(
      fixture.nativeElement.querySelectorAll('[aria-live="polite"]'),
    ) as HTMLElement[];
    expect(regiones.some((region) => region.textContent?.includes('Estamos leyendo'))).toBe(true);
  });

  it('no tiene violaciones de accesibilidad: bandeja vacía, esperando y con error', async () => {
    const vacia = await montar([]);
    await esperarSinViolacionesDeAccesibilidad(vacia.nativeElement);
    vacia.destroy();

    const esperando = await montar([draft({ id: 'd1' }), fallido('d2', 'limite_superado')]);
    await esperarSinViolacionesDeAccesibilidad(esperando.nativeElement);
    esperando.destroy();

    const conError = TestBed.createComponent(ReceiptDraftsPanel);
    conError.componentRef.setInput('eventId', 'e1');
    conError.componentRef.setInput('partidas', []);
    conError.detectChanges();
    await avanzar(conError);
    http.expectOne(LISTADO).flush({ detail: 'Error' }, { status: 500, statusText: 'Error' });
    await avanzar(conError);
    await esperarSinViolacionesDeAccesibilidad(conError.nativeElement);
  });
});
