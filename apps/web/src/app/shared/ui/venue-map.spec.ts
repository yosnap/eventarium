import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { VenueMap } from './venue-map';

// Se mockea leaflet: aquí solo se comprueba que el componente decide pintar
// (o no) el mapa y cuántos marcadores construye, no el comportamiento interno
// de la librería de mapas — mismo criterio que `address-map.spec.ts`.
const capaFalsa = { clearLayers: vi.fn(), addLayer: vi.fn(), addTo: vi.fn() };
const mapaFalso = {
  setView: vi.fn().mockReturnThis(),
  fitBounds: vi.fn(),
  invalidateSize: vi.fn(),
  remove: vi.fn(),
};
vi.mock('leaflet', () => ({
  map: vi.fn(() => mapaFalso),
  tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
  layerGroup: vi.fn(() => ({ ...capaFalsa, addTo: vi.fn(() => capaFalsa) })),
  marker: vi.fn(() => ({ bindPopup: vi.fn() })),
  latLngBounds: vi.fn(() => ({})),
  divIcon: vi.fn(() => ({})),
}));

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** `pintar()` es asíncrona (`await import('leaflet')`) y el efecto que la lanza no
 * se espera por Angular: `whenStable()` no basta. Se da un tick extra, igual que
 * `esperarDebounce` en `address-map.spec.ts`. */
async function avanzarConMapaPintado(fixture: ComponentFixture<unknown>): Promise<void> {
  await avanzar(fixture);
  await new Promise((resolve) => setTimeout(resolve, 0));
  await avanzar(fixture);
}

describe('VenueMap', () => {
  let fixture: ComponentFixture<VenueMap>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [VenueMap],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(VenueMap);
    fixture.componentRef.setInput('ariaLabel', 'Mapa de ubicación');
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('no monta el mapa sin marcadores', async () => {
    fixture.componentRef.setInput('marcadores', []);
    fixture.detectChanges();
    await avanzar(fixture);
    const { map } = await import('leaflet');
    expect(map).not.toHaveBeenCalled();
  });

  it('centra y hace zoom fijo con un único marcador', async () => {
    fixture.componentRef.setInput('marcadores', [{ lat: 39.47, lng: -0.376 }]);
    fixture.detectChanges();
    await avanzarConMapaPintado(fixture);

    expect(mapaFalso.setView).toHaveBeenCalledWith([39.47, -0.376], 16);
    expect(mapaFalso.fitBounds).not.toHaveBeenCalled();
  });

  it('ajusta la vista a todos los marcadores cuando hay más de uno', async () => {
    fixture.componentRef.setInput('marcadores', [
      { lat: 39.47, lng: -0.376, label: 'Sede A' },
      { lat: 39.48, lng: -0.38, label: 'Sede B' },
    ]);
    fixture.detectChanges();
    await avanzarConMapaPintado(fixture);

    expect(mapaFalso.fitBounds).toHaveBeenCalled();
    expect(mapaFalso.setView).not.toHaveBeenCalled();
    const { marker } = await import('leaflet');
    expect(marker).toHaveBeenCalledTimes(2);
  });

  it('lleva el aria-label pedido, sin depender de i18n', () => {
    fixture.componentRef.setInput('marcadores', []);
    fixture.detectChanges();
    const mapa = fixture.nativeElement.querySelector('.mapa') as HTMLElement;
    expect(mapa.getAttribute('aria-label')).toBe('Mapa de ubicación');
  });
});
