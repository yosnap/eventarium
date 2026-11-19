import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { traduccionEnVivo } from './traduccion-en-vivo';

const RUTA = '/public/organizations/acme/events/x';
const POST = `/api/v1${RUTA}/translations?locale=es-ES`;
const ESTADO = `/api/v1${RUTA}/translations/status?locale=es-ES`;

@Component({ selector: 'app-anfitrion', template: '' })
class Anfitrion {
  readonly pendiente = signal(true);
  readonly recargar = vi.fn(async () => this.pendiente.set(false));
  readonly traduciendo = traduccionEnVivo({
    ruta: () => RUTA,
    pendiente: () => this.pendiente(),
    campos: () => ['title'],
    recargar: this.recargar,
  });
}

describe('traduccionEnVivo', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => vi.useRealTimers());

  it('pide la traducción, espera a que termine y recarga los datos', async () => {
    const fixture = TestBed.createComponent(Anfitrion);
    fixture.detectChanges();
    expect(fixture.componentInstance.traduciendo.activa()).toBe(true);
    expect(fixture.componentInstance.traduciendo.bloque('title')).toBe(true);
    expect(fixture.componentInstance.traduciendo.bloque('description')).toBe(false);

    http.expectOne(POST).flush({ queued: true });
    await vi.advanceTimersByTimeAsync(2000);
    http.expectOne(ESTADO).flush({ in_progress: true });
    await vi.advanceTimersByTimeAsync(4000);
    http.expectOne(ESTADO).flush({ in_progress: false });
    await vi.advanceTimersByTimeAsync(0);

    expect(fixture.componentInstance.recargar).toHaveBeenCalledOnce();
    expect(fixture.componentInstance.traduciendo.activa()).toBe(false);
  });

  it('si no se encola, deja el original enseguida', async () => {
    const fixture = TestBed.createComponent(Anfitrion);
    fixture.detectChanges();

    http.expectOne(POST).flush({ queued: false });
    await vi.advanceTimersByTimeAsync(0);

    expect(fixture.componentInstance.traduciendo.activa()).toBe(false);
    expect(fixture.componentInstance.recargar).not.toHaveBeenCalled();
  });

  it('pasado el límite deja el original', async () => {
    const fixture = TestBed.createComponent(Anfitrion);
    fixture.detectChanges();
    http.expectOne(POST).flush({ queued: true });

    for (let i = 0; i < 12; i++) {
      await vi.advanceTimersByTimeAsync(8000);
      http.match(ESTADO).forEach((peticion) => peticion.flush({ in_progress: true }));
    }

    expect(fixture.componentInstance.traduciendo.activa()).toBe(false);
  });
});
