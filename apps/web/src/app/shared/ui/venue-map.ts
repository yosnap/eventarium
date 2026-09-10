import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  PLATFORM_ID,
  effect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import type { LayerGroup, Map as LeafletMap } from 'leaflet';

import { crearIcono } from './leaflet-icons';

/** Un punto a marcar en el mapa, con etiqueta opcional (nombre de la sede) y
 * color opcional (para que coincida con `estiloDeSede()` en el programa
 * multisede; por defecto el acento del tema). */
export interface MarcadorDeMapa {
  readonly lat: number;
  readonly lng: number;
  readonly label?: string | null;
  readonly color?: string;
}

const COLOR_POR_DEFECTO = 'var(--accent)';

const ZOOM_UN_MARCADOR = 16;
/** Margen alrededor del área que cubren varios marcadores, en píxeles. */
const MARGEN_AJUSTE = 32;

/**
 * Mapa de solo lectura (Leaflet), para mostrar una o varias ubicaciones ya
 * geocodificadas — la ficha de evento (1 marcador) y el programa multisede
 * (varios). A diferencia de `AddressMap` (`shared/ui/address-map.ts`), este
 * componente no edita nada: sin campo de texto, sin autocompletado Nominatim.
 * Mismo patrón SSR-safe (`isPlatformBrowser`, import dinámico de `leaflet`,
 * `invalidateSize()` tras insertar el contenedor) que ese componente ya prueba.
 *
 * Con 1 marcador, centra y hace zoom fijo sobre él. Con 2 o más, ajusta la
 * vista para que todos quepan (`fitBounds`), sin zoom prefijado.
 */
@Component({
  selector: 'app-venue-map',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="mapa" #mapa [attr.aria-label]="ariaLabel()"></div>`,
  styles: `
    .mapa {
      height: 14rem;
      border-radius: var(--radius-sm, var(--r-sm));
      border: 1px solid var(--border-strong, var(--color-border));
    }
  `,
})
export class VenueMap {
  readonly marcadores = input.required<readonly MarcadorDeMapa[]>();
  readonly ariaLabel = input.required<string>();

  private readonly plataforma = inject(PLATFORM_ID);
  private readonly esNavegador = isPlatformBrowser(this.plataforma);
  private readonly destroyRef = inject(DestroyRef);
  private readonly contenedor = viewChild<ElementRef<HTMLDivElement>>('mapa');

  private mapa: LeafletMap | null = null;
  private capaMarcadores: LayerGroup | null = null;

  constructor() {
    effect(() => {
      const elemento = this.contenedor();
      const puntos = this.marcadores();
      if (!this.esNavegador || !elemento || puntos.length === 0) {
        return;
      }
      void this.pintar(elemento.nativeElement, puntos);
    });

    this.destroyRef.onDestroy(() => {
      this.mapa?.remove();
    });
  }

  private async pintar(
    contenedor: HTMLDivElement,
    puntos: readonly MarcadorDeMapa[],
  ): Promise<void> {
    const L = await import('leaflet');
    if (!this.mapa) {
      this.mapa = L.map(contenedor);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(this.mapa);
      this.capaMarcadores = L.layerGroup().addTo(this.mapa);
    }

    // Se reconstruye entera en vez de mover marcadores existentes: `marcadores()`
    // solo cambia cuando el visitante filtra sedes en el programa multisede, un
    // caso poco frecuente donde la simplicidad importa más que el rendimiento.
    this.capaMarcadores?.clearLayers();
    for (const punto of puntos) {
      const marcador = L.marker([punto.lat, punto.lng], {
        icon: crearIcono(L, punto.color ?? COLOR_POR_DEFECTO),
      });
      if (punto.label) {
        marcador.bindPopup(punto.label);
      }
      this.capaMarcadores?.addLayer(marcador);
    }

    if (puntos.length === 1) {
      this.mapa.setView([puntos[0].lat, puntos[0].lng], ZOOM_UN_MARCADOR);
    } else {
      const limites = L.latLngBounds(puntos.map((punto) => [punto.lat, punto.lng]));
      this.mapa.fitBounds(limites, { padding: [MARGEN_AJUSTE, MARGEN_AJUSTE] });
    }

    // El contenedor puede haber estado oculto (recién insertado tras un `@if`)
    // al calcular su tamaño inicial: sin este recálculo Leaflet lo pinta a 0×0.
    const mapaActual = this.mapa;
    setTimeout(() => mapaActual.invalidateSize(), 0);
  }
}
