import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { ExpenseForm } from './expense-form';

/**
 * El alta de un gasto, que vivía dentro del libro de contabilidad y ahora es su
 * propio componente. Lo que se comprueba aquí es justo lo que se movió: la
 * validación de los cinco campos y que el total se **componga**, no se pida.
 */

const BASE = '/api/v1/accounting/events/e1';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function montar(
  http: HttpTestingController,
  partidas = [{ id: 'p1', name: 'Catering' }],
): Promise<ComponentFixture<ExpenseForm>> {
  const fixture = TestBed.createComponent(ExpenseForm);
  fixture.componentRef.setInput('eventId', 'e1');
  fixture.componentRef.setInput('partidas', partidas);
  await avanzar(fixture);
  return fixture;
}

function escribir(fixture: ComponentFixture<ExpenseForm>, id: string, valor: string): void {
  const campo = fixture.nativeElement.querySelector(`#${id}`) as HTMLInputElement;
  campo.value = valor;
  campo.dispatchEvent(new Event('input'));
}

async function enviar(fixture: ComponentFixture<ExpenseForm>): Promise<void> {
  const formulario = fixture.nativeElement.querySelector('form') as HTMLFormElement;
  formulario.dispatchEvent(new Event('submit'));
  await avanzar(fixture);
}

describe('ExpenseForm', () => {
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

  it('sin proveedor no envía y lo dice', async () => {
    const fixture = await montar(http);
    await enviar(fixture);

    expect(fixture.nativeElement.textContent).toContain('proveedor');
    http.expectNone((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
  });

  it('sin fecha no envía y lo dice', async () => {
    const fixture = await montar(http);
    escribir(fixture, 'gasto-proveedor', 'Catering SL');
    await enviar(fixture);

    expect(fixture.nativeElement.textContent).toContain('fecha');
    http.expectNone((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
  });

  it('compone el total con base más IVA, sin pedirlo aparte', async () => {
    // Es la razón de que el campo no exista: pedirlo dejaría guardar un total
    // que no cuadra con sus sumandos.
    const fixture = await montar(http);
    escribir(fixture, 'gasto-proveedor', 'Catering SL');
    escribir(fixture, 'gasto-fecha', '2026-09-05');
    escribir(fixture, 'gasto-base', '100');
    escribir(fixture, 'gasto-iva', '21');
    await enviar(fixture);

    const peticion = http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
    expect(peticion.request.body.base_cents).toBe(10000);
    expect(peticion.request.body.vat_cents).toBe(2100);
    expect(peticion.request.body.total_cents).toBe(12100);
    peticion.flush({});
  });

  it('sin IVA el total es la base, no nulo', async () => {
    const fixture = await montar(http);
    escribir(fixture, 'gasto-proveedor', 'Transporte');
    escribir(fixture, 'gasto-fecha', '2026-09-05');
    escribir(fixture, 'gasto-base', '50');
    await enviar(fixture);

    const peticion = http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
    expect(peticion.request.body.vat_cents).toBeNull();
    expect(peticion.request.body.total_cents).toBe(5000);
    peticion.flush({});
  });

  it('acepta la coma como separador decimal', async () => {
    const fixture = await montar(http);
    escribir(fixture, 'gasto-proveedor', 'Catering SL');
    escribir(fixture, 'gasto-fecha', '2026-09-05');
    escribir(fixture, 'gasto-base', '12,50');
    await enviar(fixture);

    const peticion = http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
    expect(peticion.request.body.base_cents).toBe(1250);
    peticion.flush({});
  });

  it('la conversión a céntimos no ha cambiado al pasar a ser compartida', async () => {
    // Regresión de la extracción de `aCents` a `accounting-types`: el alta
    // manual y la revisión de un justificante tienen que redondear igual, y
    // este es el comportamiento que había antes de moverla.
    const fixture = await montar(http);
    escribir(fixture, 'gasto-proveedor', 'Catering SL');
    escribir(fixture, 'gasto-fecha', '2026-09-05');
    escribir(fixture, 'gasto-base', '0,015');
    await enviar(fixture);

    const peticion = http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
    expect(peticion.request.body.base_cents).toBe(2);
    peticion.flush({});
  });

  it('un importe que no es un número se rechaza sin llamar al API', async () => {
    const fixture = await montar(http);
    escribir(fixture, 'gasto-proveedor', 'Catering SL');
    escribir(fixture, 'gasto-fecha', '2026-09-05');
    escribir(fixture, 'gasto-base', 'mil euros');
    await enviar(fixture);

    expect(fixture.nativeElement.textContent).toContain('importe base válido');
    http.expectNone((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
  });

  it('la partida es opcional y va nula si no se elige', async () => {
    const fixture = await montar(http);
    escribir(fixture, 'gasto-proveedor', 'Varios');
    escribir(fixture, 'gasto-fecha', '2026-09-05');
    escribir(fixture, 'gasto-base', '10');
    await enviar(fixture);

    const peticion = http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'POST');
    expect(peticion.request.body.budget_line_id).toBeNull();
    peticion.flush({});
  });

  it('avisa al crear y limpia el formulario', async () => {
    const fixture = await montar(http);
    let aviso: string | null = null;
    fixture.componentInstance.creado.subscribe((mensaje) => (aviso = mensaje));

    escribir(fixture, 'gasto-proveedor', 'Catering SL');
    escribir(fixture, 'gasto-fecha', '2026-09-05');
    escribir(fixture, 'gasto-base', '100');
    await enviar(fixture);
    http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'POST').flush({});
    await avanzar(fixture);

    expect(aviso).not.toBeNull();
    // Los campos vuelven a vacío, que es lo que permite dar de alta el siguiente.
    const proveedor = fixture.nativeElement.querySelector('#gasto-proveedor') as HTMLInputElement;
    expect(proveedor.value).toBe('');
  });

  it('ofrece las partidas que recibe para imputar', async () => {
    const fixture = await montar(http, [
      { id: 'p1', name: 'Catering' },
      { id: 'p2', name: 'Sonido' },
    ]);

    const opciones = Array.from(
      fixture.nativeElement.querySelectorAll('#gasto-partida-nativo option'),
    ).map((o) => (o as HTMLOptionElement).textContent?.trim());
    expect(opciones).toContain('Catering');
    expect(opciones).toContain('Sonido');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = await montar(http);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
