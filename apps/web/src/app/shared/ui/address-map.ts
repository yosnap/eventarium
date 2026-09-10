import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  PLATFORM_ID,
  computed,
  effect,
  inject,
  input,
  model,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import type { Map as LeafletMap, Marker as LeafletMarker } from 'leaflet';

import { crearIcono } from './leaflet-icons';

/** Coordenadas geográficas, en el formato que ya expone el backend. */
export interface Coordenadas {
  readonly latitude: number;
  readonly longitude: number;
}

interface Sugerencia {
  readonly displayName: string;
  readonly lat: number;
  readonly lon: number;
}

interface ResultadoNominatim {
  readonly display_name: string;
  readonly lat: string;
  readonly lon: string;
}

/** Nominatim pide un cliente «buen ciudadano»: el navegador no permite fijar
 * `User-Agent` desde `fetch`, así que la cortesía se traduce en no bombardear la
 * API pública con una petición por tecla. */
const RETRASO_BUSQUEDA_MS = 500;
const LONGITUD_MINIMA_BUSQUEDA = 3;
const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';
const ZOOM_MARCADOR = 16;

/**
 * Campo de dirección con autocompletado (Nominatim) y mapa real (Leaflet).
 *
 * Se usa tanto para la dirección de una sede como para la dirección simple de un
 * evento de una sola sede: en los dos casos el backend geocodifica la dirección al
 * guardar (`latitude`/`longitude` de solo lectura), así que este componente nunca
 * envía coordenadas al backend — solo el texto de la dirección, más un mapa que
 * ayuda a confirmar visualmente el sitio elegido.
 *
 * El mapa solo aparece cuando hay coordenadas conocidas: de una sugerencia elegida,
 * o de las que ya vengan guardadas (`initialLatitude`/`initialLongitude`) al editar un
 * registro ya geocodificado por el backend. Si la persona escribe una dirección a
 * mano sin elegir ninguna sugerencia, el campo sigue funcionando como texto libre
 * normal, sin mapa.
 *
 * Patrón ARIA «combobox con listbox», mismo espíritu que `Select`
 * (`aria-activedescendant`, foco siempre en el campo de texto real).
 */
@Component({
  selector: 'app-address-map',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <div class="campo">
        <label [id]="idEtiqueta()" [for]="idCampo()">{{ label() }}</label>
        <div class="combo">
          <input
            #campo
            type="text"
            role="combobox"
            autocomplete="off"
            aria-autocomplete="list"
            aria-haspopup="listbox"
            [id]="idCampo()"
            [value]="value()"
            [disabled]="disabled()"
            [attr.aria-expanded]="abierto()"
            [attr.aria-controls]="idLista()"
            [attr.aria-labelledby]="idEtiqueta()"
            [attr.aria-activedescendant]="idOpcionActiva()"
            [attr.aria-invalid]="error() ? 'true' : null"
            [attr.aria-describedby]="descripcionId()"
            [attr.aria-required]="required() ? 'true' : null"
            (input)="alEscribir($event)"
            (keydown)="alPulsarTecla($event)"
            (blur)="alPerderFoco()"
          />
          <ul
            class="combo__lista"
            role="listbox"
            [id]="idLista()"
            [attr.aria-labelledby]="idEtiqueta()"
            [hidden]="!abierto() || sugerencias().length === 0"
          >
            @for (sugerencia of sugerencias(); track sugerencia.displayName; let i = $index) {
              <li
                class="combo__o"
                role="option"
                [id]="idOpcion(i)"
                [class.is-active]="i === indiceActivo()"
                [attr.aria-selected]="i === indiceActivo()"
                (mousedown)="elegir(i)"
                (mousemove)="indiceActivo.set(i)"
              >
                {{ sugerencia.displayName }}
              </li>
            }
          </ul>
        </div>

        @if (error()) {
          <p [id]="idError()" class="error">{{ error() }}</p>
        } @else if (hint()) {
          <p [id]="idAyuda()" class="ayuda">{{ hint() }}</p>
        }
        @if (buscando()) {
          <p class="estado" role="status">{{ t('direccionMapa.buscando') }}</p>
        } @else if (errorBusqueda()) {
          <p class="estado estado--error" role="status">{{ t('direccionMapa.error') }}</p>
        }

        @if (coordsActuales(); as punto) {
          <div class="mapa" #mapa [attr.aria-label]="t('direccionMapa.mapaEtiqueta')"></div>
        } @else {
          <p class="estado">{{ t('direccionMapa.sinMapa') }}</p>
        }
      </div>
    </ng-container>
  `,
  styles: `
    .campo {
      display: grid;
      gap: var(--sp-2);
    }
    label {
      display: block;
      font-size: var(--fs-sm, 0.875rem);
      color: var(--muted, var(--color-text-muted, #6b7280));
    }
    .combo {
      position: relative;
    }
    input {
      width: 100%;
      box-sizing: border-box;
      padding: var(--sp-3);
      border: 1px solid var(--border-strong, var(--color-border));
      border-radius: var(--radius-sm);
      background-color: var(--surface-2, var(--color-surface));
      color: var(--fg, var(--color-text));
      font: inherit;
      min-height: 2.75rem;
    }
    input:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent);
    }
    .combo__lista {
      position: absolute;
      z-index: 60;
      top: calc(100% + var(--sp-1));
      left: 0;
      right: 0;
      max-height: 16rem;
      overflow: auto;
      padding: var(--sp-1);
      margin: 0;
      list-style: none;
      background: var(--surface);
      border: 1px solid var(--border-strong, var(--color-border));
      border-radius: var(--radius-sm);
      box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.15));
    }
    .combo__lista[hidden] {
      display: none;
    }
    .combo__o {
      padding: var(--sp-2) var(--sp-3);
      border-radius: 3px;
      cursor: pointer;
      color: var(--fg, var(--color-text));
      font-size: 0.9rem;
    }
    .combo__o.is-active,
    .combo__o:hover {
      background: var(--surface-hi, rgba(0, 0, 0, 0.06));
    }
    .error {
      margin: 0;
      color: var(--danger, var(--color-danger));
      font-size: 0.875rem;
    }
    .ayuda,
    .estado {
      margin: 0;
      color: var(--muted, var(--color-text-muted, #6b7280));
      font-size: 0.8125rem;
    }
    .estado--error {
      color: var(--danger, var(--color-danger));
    }
    .mapa {
      height: 14rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border-strong, var(--color-border));
    }
  `,
})
export class AddressMap {
  readonly label = input.required<string>();
  readonly required = input(false);
  readonly disabled = input(false);
  readonly error = input<string | null>(null);
  readonly hint = input<string | null>(null);
  readonly fieldId = input<string | null>(null);
  /** Coordenadas ya conocidas (p. ej. al editar un registro ya geocodificado por el
   * backend): permiten mostrar el mapa sin tener que volver a geocodificar. */
  readonly initialLatitude = input<number | null>(null);
  readonly initialLongitude = input<number | null>(null);
  readonly value = model('');
  /** Se emite al perder el foco, mismo patrón que `Input`/`Select`. */
  readonly blurred = output<void>();
  /** Se emite cuando se elige una sugerencia (coordenadas nuevas) o se pierden
   * (texto editado a mano): informativo para quien lo use, el propio componente no
   * necesita que se le devuelva nada por `[initialLatitude]`/`[initialLongitude]`. */
  readonly coordsPicked = output<Coordenadas | null>();

  private readonly plataforma = inject(PLATFORM_ID);
  private readonly esNavegador = isPlatformBrowser(this.plataforma);
  private readonly destroyRef = inject(DestroyRef);
  private readonly contenedorMapa = viewChild<ElementRef<HTMLDivElement>>('mapa');

  private static contador = 0;
  private readonly indice = AddressMap.contador++;
  protected readonly idCampo = computed(() => this.fieldId() ?? `direccion-${this.indice}`);
  protected readonly idLista = computed(() => `${this.idCampo()}-lista`);
  protected readonly idEtiqueta = computed(() => `${this.idCampo()}-etiqueta`);
  protected readonly idError = computed(() => `${this.idCampo()}-error`);
  protected readonly idAyuda = computed(() => `${this.idCampo()}-ayuda`);
  protected readonly descripcionId = computed(() => {
    if (this.error()) return this.idError();
    if (this.hint()) return this.idAyuda();
    return null;
  });

  protected readonly sugerencias = signal<Sugerencia[]>([]);
  protected readonly abierto = signal(false);
  protected readonly indiceActivo = signal(-1);
  protected readonly buscando = signal(false);
  protected readonly errorBusqueda = signal(false);
  protected readonly idOpcionActiva = computed(() =>
    this.abierto() && this.indiceActivo() >= 0 ? this.idOpcion(this.indiceActivo()) : null,
  );

  /** Coordenadas mostradas en el mapa: de una sugerencia elegida, o de las
   * iniciales mientras no se toquen. */
  protected readonly coordsActuales = signal<{ lat: number; lng: number } | null>(null);

  private mapa: LeafletMap | null = null;
  private marcador: LeafletMarker | null = null;
  private temporizadorBusqueda: ReturnType<typeof setTimeout> | null = null;
  private cierreDiferido: ReturnType<typeof setTimeout> | null = null;
  private abortador: AbortController | null = null;
  private secuenciaBusqueda = 0;

  constructor() {
    // Las coordenadas iniciales llegan por `input()`, no por `model()`: cuando el
    // padre cambia de registro en edición (o vuelve a `null` al cancelar), este
    // efecto resincroniza el mapa sin que escribir a mano lo pise (ver `alEscribir`,
    // que solo limpia `coordsActuales` de forma local, sin tocar estos inputs).
    effect(() => {
      const lat = this.initialLatitude();
      const lon = this.initialLongitude();
      // `typeof` en vez de `!== null`: algunas respuestas (y algunos mocks de test)
      // omiten el campo en vez de mandarlo explícitamente a `null`.
      this.coordsActuales.set(
        typeof lat === 'number' && typeof lon === 'number' ? { lat, lng: lon } : null,
      );
    });

    effect(() => {
      const contenedor = this.contenedorMapa();
      const punto = this.coordsActuales();
      if (!this.esNavegador || !contenedor || !punto) {
        return;
      }
      void this.pintarMapa(contenedor.nativeElement, punto);
    });

    this.destroyRef.onDestroy(() => {
      if (this.temporizadorBusqueda) clearTimeout(this.temporizadorBusqueda);
      if (this.cierreDiferido) clearTimeout(this.cierreDiferido);
      this.abortador?.abort();
      this.mapa?.remove();
    });
  }

  protected idOpcion(indice: number): string {
    return `${this.idLista()}-o-${indice}`;
  }

  private async pintarMapa(
    contenedor: HTMLDivElement,
    punto: { lat: number; lng: number },
  ): Promise<void> {
    const L = await import('leaflet');
    if (!this.mapa) {
      this.mapa = L.map(contenedor).setView([punto.lat, punto.lng], ZOOM_MARCADOR);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(this.mapa);
      this.marcador = L.marker([punto.lat, punto.lng], {
        icon: crearIcono(L, 'var(--accent)'),
      }).addTo(this.mapa);
    } else {
      this.mapa.setView([punto.lat, punto.lng], ZOOM_MARCADOR);
      this.marcador?.setLatLng([punto.lat, punto.lng]);
    }
    // El contenedor puede haber estado oculto (recién insertado tras el `@if`) al
    // calcular su tamaño inicial: sin este recálculo Leaflet lo pinta a 0×0.
    const mapaActual = this.mapa;
    setTimeout(() => mapaActual.invalidateSize(), 0);
  }

  protected alEscribir(evento: Event): void {
    const texto = (evento.target as HTMLInputElement).value;
    this.value.set(texto);
    this.coordsActuales.set(null);
    this.coordsPicked.emit(null);
    this.indiceActivo.set(-1);
    this.programarBusqueda(texto);
  }

  private programarBusqueda(texto: string): void {
    if (this.temporizadorBusqueda) clearTimeout(this.temporizadorBusqueda);
    if (!this.esNavegador || texto.trim().length < LONGITUD_MINIMA_BUSQUEDA) {
      this.sugerencias.set([]);
      this.abierto.set(false);
      return;
    }
    this.temporizadorBusqueda = setTimeout(() => void this.buscar(texto), RETRASO_BUSQUEDA_MS);
  }

  private async buscar(texto: string): Promise<void> {
    this.abortador?.abort();
    const abortador = new AbortController();
    this.abortador = abortador;
    const secuencia = ++this.secuenciaBusqueda;
    this.buscando.set(true);
    this.errorBusqueda.set(false);
    try {
      const url = `${NOMINATIM_URL}?format=json&addressdetails=0&limit=5&q=${encodeURIComponent(texto)}`;
      const respuesta = await fetch(url, {
        signal: abortador.signal,
        headers: { Accept: 'application/json' },
      });
      if (!respuesta.ok) {
        throw new Error(`nominatim-http-${respuesta.status}`);
      }
      const resultados = (await respuesta.json()) as ResultadoNominatim[];
      if (secuencia !== this.secuenciaBusqueda) {
        return;
      }
      const sugerencias = resultados.map(
        (r): Sugerencia => ({ displayName: r.display_name, lat: Number(r.lat), lon: Number(r.lon) }),
      );
      this.sugerencias.set(sugerencias);
      this.abierto.set(sugerencias.length > 0);
      this.indiceActivo.set(sugerencias.length > 0 ? 0 : -1);
    } catch (error) {
      if (secuencia !== this.secuenciaBusqueda) {
        return;
      }
      if ((error as { name?: string }).name === 'AbortError') {
        return;
      }
      this.errorBusqueda.set(true);
      this.sugerencias.set([]);
      this.abierto.set(false);
    } finally {
      if (secuencia === this.secuenciaBusqueda) {
        this.buscando.set(false);
      }
    }
  }

  protected elegir(indice: number): void {
    const sugerencia = this.sugerencias()[indice];
    if (!sugerencia) return;
    this.value.set(sugerencia.displayName);
    this.coordsActuales.set({ lat: sugerencia.lat, lng: sugerencia.lon });
    this.coordsPicked.emit({ latitude: sugerencia.lat, longitude: sugerencia.lon });
    this.cerrarLista();
  }

  private cerrarLista(): void {
    this.abierto.set(false);
    this.sugerencias.set([]);
    this.indiceActivo.set(-1);
  }

  protected alPulsarTecla(evento: KeyboardEvent): void {
    if (!this.abierto() || this.sugerencias().length === 0) {
      return;
    }
    switch (evento.key) {
      case 'ArrowDown':
        evento.preventDefault();
        this.indiceActivo.set((this.indiceActivo() + 1) % this.sugerencias().length);
        return;
      case 'ArrowUp':
        evento.preventDefault();
        this.indiceActivo.set(
          (this.indiceActivo() - 1 + this.sugerencias().length) % this.sugerencias().length,
        );
        return;
      case 'Enter':
        if (this.indiceActivo() >= 0) {
          evento.preventDefault();
          this.elegir(this.indiceActivo());
        }
        return;
      case 'Escape':
        evento.preventDefault();
        this.cerrarLista();
        return;
    }
  }

  protected alPerderFoco(): void {
    // El cierre se retrasa para que el `mousedown` sobre una sugerencia (que ya
    // dispara `elegir()`) llegue antes de que la lista desaparezca por el `blur`.
    this.cierreDiferido = setTimeout(() => this.cerrarLista(), 150);
    this.blurred.emit();
  }
}
