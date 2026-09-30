import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { EventCancelCard } from './event-cancel-card';

const RESUMEN = {
  inscripciones_afectadas: 3,
  pagos_a_reembolsar: 1,
  importe_a_reembolsar_cents: 2500,
  moneda: 'eur',
  requiere_permiso_de_pagos: true,
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventCancelCard', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
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

  async function crear(yaCancelado = false): Promise<ComponentFixture<EventCancelCard>> {
    const fixture = TestBed.createComponent(EventCancelCard);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.componentRef.setInput('yaCancelado', yaCancelado);
    await avanzar(fixture);
    return fixture;
  }

  function botonPorTexto(raiz: HTMLElement, texto: string): HTMLButtonElement {
    const boton = [...raiz.querySelectorAll('button')].find((b) => b.textContent?.includes(texto));
    if (!boton) throw new Error(`No hay botón «${texto}»`);
    return boton;
  }

  it('enseña el resumen antes de cancelar y envía sus mismas cifras', async () => {
    const fixture = await crear();
    const raiz: HTMLElement = fixture.nativeElement;
    let confirmada = false;
    fixture.componentInstance.cancelacionConfirmada.subscribe(() => (confirmada = true));

    botonPorTexto(raiz, 'Cancelar evento').click();
    http.expectOne('/api/v1/events/e1/cancel/preview').flush(RESUMEN);
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Se cancelarán 3 inscripciones');
    expect(raiz.textContent).toContain('Se devolverán 1 pagos');

    botonPorTexto(raiz, 'Sí, cancelar el evento').click();
    const envio = http.expectOne('/api/v1/events/e1/cancel');
    expect(envio.request.body).toEqual({
      motivo: null,
      inscripciones_afectadas: 3,
      importe_a_reembolsar_cents: 2500,
    });
    envio.flush({ por_cancelar: 3, por_avisar: 3, reembolsos_fallidos: 0 });
    await avanzar(fixture);
    http
      .expectOne('/api/v1/events/e1/cancel/progress')
      .flush({ por_cancelar: 0, por_avisar: 0, reembolsos_fallidos: 0 });
    await avanzar(fixture);

    expect(confirmada).toBe(true);
    expect(raiz.textContent).toContain('Evento cancelado.');
  });

  it('si las cifras cambiaron, vuelve a pedir el resumen y explica por qué', async () => {
    const fixture = await crear();
    const raiz: HTMLElement = fixture.nativeElement;
    botonPorTexto(raiz, 'Cancelar evento').click();
    http.expectOne('/api/v1/events/e1/cancel/preview').flush(RESUMEN);
    await avanzar(fixture);

    botonPorTexto(raiz, 'Sí, cancelar el evento').click();
    http
      .expectOne('/api/v1/events/e1/cancel')
      .flush(
        { detail: 'Las inscripciones han cambiado.' },
        { status: 409, statusText: 'Conflict' },
      );
    await avanzar(fixture);
    http
      .expectOne('/api/v1/events/e1/cancel/preview')
      .flush({ ...RESUMEN, inscripciones_afectadas: 4 });
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Se cancelarán 4 inscripciones');
  });

  it('con el evento ya cancelado muestra el progreso y los reembolsos fallidos', async () => {
    const fixture = await crear(true);
    http
      .expectOne('/api/v1/events/e1/cancel/progress')
      .flush({ por_cancelar: 0, por_avisar: 0, reembolsos_fallidos: 2 });
    await avanzar(fixture);
    const raiz: HTMLElement = fixture.nativeElement;

    expect(raiz.textContent).toContain('2 reembolsos han fallado');
    const botones = [...raiz.querySelectorAll('button')].map((b) => b.textContent ?? '');
    expect(botones.some((texto) => texto.includes('Cancelar evento'))).toBe(false);
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  describe('eliminar', () => {
    it('un evento activo no ofrece eliminar: primero hay que cancelarlo', async () => {
      const fixture = await crear(false);
      expect(fixture.nativeElement.textContent).not.toContain('Eliminar evento');
    });

    it('con la cancelación en marcha el botón está desactivado y lo explica', async () => {
      const fixture = await crear(true);
      http
        .expectOne('/api/v1/events/e1/cancel/progress')
        .flush({ por_cancelar: 2, por_avisar: 3, reembolsos_fallidos: 0 });
      await avanzar(fixture);
      const raiz: HTMLElement = fixture.nativeElement;

      expect(botonPorTexto(raiz, 'Eliminar evento').disabled).toBe(true);
      expect(raiz.textContent).toContain('Podrás eliminarlo cuando termine la cancelación');
      // Para que el intervalo de seguimiento no deje peticiones abiertas.
      fixture.destroy();
    });

    it('con reembolsos fallidos tampoco se puede eliminar', async () => {
      const fixture = await crear(true);
      http
        .expectOne('/api/v1/events/e1/cancel/progress')
        .flush({ por_cancelar: 0, por_avisar: 0, reembolsos_fallidos: 1 });
      await avanzar(fixture);

      expect(botonPorTexto(fixture.nativeElement, 'Eliminar evento').disabled).toBe(true);
    });

    it('terminada la cancelación, confirma en un diálogo y elimina', async () => {
      const fixture = await crear(true);
      http
        .expectOne('/api/v1/events/e1/cancel/progress')
        .flush({ por_cancelar: 0, por_avisar: 0, reembolsos_fallidos: 0 });
      await avanzar(fixture);
      const raiz: HTMLElement = fixture.nativeElement;
      let eliminado = false;
      fixture.componentInstance.eliminado.subscribe(() => (eliminado = true));

      const abrir = botonPorTexto(raiz, 'Eliminar evento');
      expect(abrir.disabled).toBe(false);
      abrir.click();
      await avanzar(fixture);
      expect(raiz.textContent).toContain('¿Eliminar este evento?');

      botonPorTexto(raiz, 'Sí, eliminar el evento').click();
      const peticion = http.expectOne('/api/v1/events/e1');
      expect(peticion.request.method).toBe('DELETE');
      peticion.flush(null, { status: 204, statusText: 'No Content' });
      await avanzar(fixture);

      expect(eliminado).toBe(true);
    });

    it('si la API lo rechaza (409) enseña el motivo y no da el evento por eliminado', async () => {
      const fixture = await crear(true);
      http
        .expectOne('/api/v1/events/e1/cancel/progress')
        .flush({ por_cancelar: 0, por_avisar: 0, reembolsos_fallidos: 0 });
      await avanzar(fixture);
      const raiz: HTMLElement = fixture.nativeElement;
      let eliminado = false;
      fixture.componentInstance.eliminado.subscribe(() => (eliminado = true));

      botonPorTexto(raiz, 'Eliminar evento').click();
      await avanzar(fixture);
      botonPorTexto(raiz, 'Sí, eliminar el evento').click();
      http
        .expectOne('/api/v1/events/e1')
        .flush(
          { detail: 'Hay reembolsos sin completar.' },
          { status: 409, statusText: 'Conflict' },
        );
      await avanzar(fixture);

      expect(eliminado).toBe(false);
      expect(raiz.textContent).toContain('Hay reembolsos sin completar.');
    });
  });
});
