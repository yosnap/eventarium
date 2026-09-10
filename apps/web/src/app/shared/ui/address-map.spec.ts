import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { AddressMap } from './address-map';

// Se mockea leaflet: aquí solo se comprueba que el componente decide pintar (o
// no) el mapa, no el comportamiento interno de la librería de mapas.
vi.mock('leaflet', () => {
  const marcador = { setLatLng: vi.fn() };
  const mapaFalso = {
    setView: vi.fn().mockReturnThis(),
    invalidateSize: vi.fn(),
    remove: vi.fn(),
  };
  return {
    map: vi.fn(() => mapaFalso),
    tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
    marker: vi.fn(() => ({ addTo: vi.fn(() => marcador), setLatLng: vi.fn() })),
    divIcon: vi.fn(() => ({})),
  };
});

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** Espera real algo más larga que el debounce de 500ms del componente: se evitan
 * los temporizadores falsos de vitest porque interfieren con el planificador de
 * zoneless change detection de Angular (`whenStable()` deja de resolver). */
async function esperarDebounce(fixture: ComponentFixture<unknown>): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 600));
  await avanzar(fixture);
}

function respuestaNominatim(resultados: { display_name: string; lat: string; lon: string }[]) {
  return {
    ok: true,
    json: () => Promise.resolve(resultados),
  } as Response;
}

describe('AddressMap', () => {
  let fixture: ComponentFixture<AddressMap>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        AddressMap,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(AddressMap);
    fixture.componentRef.setInput('label', 'Dirección');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('no muestra el mapa mientras no hay coordenadas conocidas', async () => {
    fixture.detectChanges();
    await avanzar(fixture);
    expect(fixture.nativeElement.querySelector('.mapa')).toBeNull();
  });

  it('muestra el mapa de entrada cuando recibe coordenadas iniciales, sin llamar a Nominatim', async () => {
    const fetchEspia = vi.spyOn(globalThis, 'fetch');
    fixture.componentRef.setInput('initialLatitude', 39.47);
    fixture.componentRef.setInput('initialLongitude', -0.376);
    fixture.detectChanges();
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('.mapa')).not.toBeNull();
    expect(fetchEspia).not.toHaveBeenCalled();
  });

  it('busca sugerencias con debounce al escribir y las lista de forma accesible', async () => {
    const fetchEspia = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        respuestaNominatim([{ display_name: 'Calle Mayor 1, Valencia', lat: '39.47', lon: '-0.376' }]),
      );
    fixture.detectChanges();
    await avanzar(fixture);

    const campo = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    campo.value = 'Calle Mayor';
    campo.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    expect(fetchEspia).not.toHaveBeenCalled();
    await esperarDebounce(fixture);

    expect(fetchEspia).toHaveBeenCalledTimes(1);
    expect((fetchEspia.mock.calls[0][0] as string).startsWith('https://nominatim.openstreetmap.org/search')).toBe(
      true,
    );
    const opciones = fixture.nativeElement.querySelectorAll('[role="option"]');
    expect(opciones.length).toBe(1);
    expect(campo.getAttribute('aria-expanded')).toBe('true');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  }, 10000);

  it('al elegir una sugerencia, rellena el campo y muestra el mapa', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      respuestaNominatim([{ display_name: 'Calle Mayor 1, Valencia', lat: '39.47', lon: '-0.376' }]),
    );
    fixture.detectChanges();
    await avanzar(fixture);

    const campo = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    campo.value = 'Calle Mayor';
    campo.dispatchEvent(new Event('input'));
    await esperarDebounce(fixture);

    const opcion = fixture.nativeElement.querySelector('[role="option"]') as HTMLLIElement;
    opcion.dispatchEvent(new Event('mousedown', { bubbles: true }));
    await avanzar(fixture);

    expect(campo.value).toBe('Calle Mayor 1, Valencia');
    expect(fixture.nativeElement.querySelector('.mapa')).not.toBeNull();
  }, 10000);

  it('vuelve a texto libre sin mapa si se edita la dirección a mano tras elegir una sugerencia', async () => {
    fixture.componentRef.setInput('initialLatitude', 39.47);
    fixture.componentRef.setInput('initialLongitude', -0.376);
    fixture.detectChanges();
    await avanzar(fixture);
    expect(fixture.nativeElement.querySelector('.mapa')).not.toBeNull();

    const campo = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    campo.value = 'Otra dirección cualquiera';
    campo.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('.mapa')).toBeNull();
  });
});
