import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { Button } from './button';

/** Rectángulo normalizado (0-1) respecto a la imagen ya horneada (con la
 * rotación/volteo actuales ya aplicados a los píxeles). Solo se usa
 * internamente para el arrastre; nunca sale de este componente. */
interface RectanguloDeRecorte {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

interface PresetDeProporcion {
  readonly etiqueta: string;
  readonly valor: number | undefined;
}

const PROPORCIONES: readonly PresetDeProporcion[] = [
  { etiqueta: 'ui.media.proporcionLibre', valor: undefined },
  { etiqueta: '1:1', valor: 1 },
  { etiqueta: '16:9', valor: 16 / 9 },
  { etiqueta: '4:3', valor: 4 / 3 },
  { etiqueta: '3:2', valor: 3 / 2 },
];

const UMBRAL_MINIMO = 0.02;

/**
 * Editor de recorte: proporciones fijas, rotar, voltear y zoom, con recorte
 * final en el propio navegador (paridad con la referencia de Motoraldia,
 * `media-image-editor.tsx` + `react-image-crop`, decisión explícita del
 * usuario en `plans/260921-1720-prd-editor-recorte-imagen/plan.md` — revierte
 * a propósito el "el servidor manda los píxeles finales" de la biblioteca de
 * medios: aquí el resultado ya recortado se sube como un `Media` nuevo).
 *
 * Rotar/voltear se "hornean" en un `<canvas>` interno cada vez que cambian
 * (siempre partiendo de la imagen original intacta, nunca encadenando sobre
 * un resultado ya recodificado): así el arrastre de selección solo tiene que
 * lidiar con una imagen ya alineada a los ejes, nunca con una rotada por CSS
 * en pantalla — mucho más simple y menos frágil que recalcular la selección
 * bajo una transformación en curso. El zoom, en cambio, es una ayuda visual
 * pura (`transform: scale` sobre la imagen ya horneada, con scroll): no toca
 * los píxeles, solo permite arrastrar con más precisión sobre una imagen
 * grande.
 */
@Component({
  selector: 'app-media-crop-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        @if (error(); as mensaje) {
          <p class="error">{{ mensaje }}</p>
        }

        <p class="instruccion">{{ t('ui.media.arrastraParaRecortar') }}</p>

        <div class="controles">
          <div class="grupo">
            <span class="etiqueta-grupo">{{ t('ui.media.proporcion') }}</span>
            <div class="botones">
              @for (preset of proporciones; track preset.etiqueta) {
                <button
                  type="button"
                  class="chip"
                  [class.activo]="aspecto() === preset.valor"
                  (click)="elegirProporcion(preset.valor)"
                >
                  {{ preset.valor === undefined ? t(preset.etiqueta) : preset.etiqueta }}
                </button>
              }
            </div>
          </div>

          <div class="grupo">
            <span class="etiqueta-grupo">{{ t('ui.media.rotar') }}</span>
            <div class="botones">
              <button type="button" class="chip" (click)="rotar(-90)">-90°</button>
              <button type="button" class="chip" (click)="rotar(90)">+90°</button>
              <button
                type="button"
                class="chip"
                [class.activo]="flipHorizontal()"
                [attr.aria-label]="t('ui.media.voltearHorizontal')"
                (click)="alternarVolteo('horizontal')"
              >
                ↔
              </button>
              <button
                type="button"
                class="chip"
                [class.activo]="flipVertical()"
                [attr.aria-label]="t('ui.media.voltearVertical')"
                (click)="alternarVolteo('vertical')"
              >
                ↕
              </button>
            </div>
          </div>

          <label class="grupo zoom">
            <span class="etiqueta-grupo">{{ t('ui.media.zoom') }}</span>
            <input
              type="range"
              min="1"
              max="3"
              step="0.1"
              [value]="zoom()"
              (input)="zoom.set($any($event.target).valueAsNumber)"
            />
            <span class="valor-zoom">{{ zoom().toFixed(1) }}×</span>
          </label>
        </div>

        <div
          #lienzo
          class="lienzo"
          (pointerdown)="alEmpezar($event)"
          (pointermove)="alArrastrar($event)"
          (pointerup)="alSoltar($event)"
          (pointercancel)="alSoltar($event)"
        >
          <div class="interno" [style.transform]="'scale(' + zoom() + ')'">
            <img #imgPrevia [src]="previaSrc()" alt="" />
            @if (rectangulo(); as r) {
              <div
                class="seleccion"
                [style.left.%]="r.x * 100"
                [style.top.%]="r.y * 100"
                [style.width.%]="r.width * 100"
                [style.height.%]="r.height * 100"
              ></div>
            }
          </div>
        </div>

        <div class="acciones">
          <app-button
            variant="secundario"
            type="button"
            [disabled]="generando() || confirmando()"
            (pulsado)="cancelado.emit()"
          >
            {{ t('comun.cancelar') }}
          </app-button>
          <app-button
            type="button"
            [disabled]="!rectangulo() || generando() || confirmando()"
            [loading]="generando() || confirmando()"
            (pulsado)="confirmar()"
          >
            {{ t('ui.media.confirmarRecorte') }}
          </app-button>
        </div>
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .instruccion {
      margin: 0 0 var(--space-sm);
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .error {
      color: var(--danger);
      font-size: var(--fs-sm);
      margin: 0 0 var(--space-sm);
    }
    .controles {
      display: grid;
      gap: var(--space-sm);
      margin-bottom: var(--space-sm);
    }
    .grupo {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }
    .etiqueta-grupo {
      width: 5rem;
      flex-shrink: 0;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .botones {
      display: flex;
      flex-wrap: wrap;
      gap: 0.375rem;
    }
    .chip {
      border: 1px solid var(--border-strong);
      background: transparent;
      color: var(--fg);
      border-radius: var(--radius-sm);
      padding: 0.25rem 0.625rem;
      font: inherit;
      font-size: var(--fs-sm);
      cursor: pointer;
    }
    .chip:hover {
      background-color: var(--surface-hi);
    }
    .chip.activo {
      border-color: var(--accent);
      background-color: var(--accent);
      color: var(--on-accent);
    }
    .zoom {
      gap: 0.5rem;
    }
    .zoom input[type='range'] {
      flex: 1;
      min-width: 8rem;
    }
    .valor-zoom {
      width: 2.5rem;
      text-align: right;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    /* overflow: hidden + tamaño fijo (no max-height que se adapta al
       contenido): el zoom escala .interno desde su centro sin mover el
       viewport — "el tamaño permanece y se centra" (hallazgo del usuario:
       antes, con overflow: auto y transform-origin: top left, ampliar
       el zoom hacía crecer el lienzo entero y desplazaba la vista hacia la
       esquina superior izquierda en vez de mantenerla centrada). */
    .lienzo {
      position: relative;
      width: 100%;
      height: 20rem;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      touch-action: none;
    }
    .interno {
      position: relative;
      display: inline-block;
      transform-origin: center center;
      cursor: crosshair;
      user-select: none;
    }
    .interno img {
      display: block;
      max-width: 100%;
      max-height: 20rem;
      pointer-events: none;
    }
    .seleccion {
      position: absolute;
      border: 2px solid var(--accent);
      background-color: color-mix(in srgb, var(--accent) 20%, transparent);
      pointer-events: none;
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
      margin-top: var(--space-sm);
      justify-content: flex-end;
    }
  `,
})
export class MediaCropEditor {
  /** Imagen sobre la que recortar (URL ya subida, misma procedencia que el
   * resto de `MediaPicker` — no hace falta CORS explícito). */
  readonly url = input.required<string>();
  /** Refleja que la subida del resultado (tras confirmar) está en curso. */
  readonly confirmando = input(false);

  /** El recorte final ya renderizado, listo para subir por el endpoint de
   * subida habitual (multipart) — nunca un rectángulo: el propio navegador
   * hornea rotación/volteo/zoom/recorte en el resultado. */
  readonly confirmado = output<Blob>();
  readonly cancelado = output<void>();

  protected readonly proporciones = PROPORCIONES;

  private readonly lienzo = viewChild.required<ElementRef<HTMLDivElement>>('lienzo');
  private readonly imgPrevia = viewChild<ElementRef<HTMLImageElement>>('imgPrevia');

  protected readonly cargando = signal(true);
  protected readonly generando = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly rotacion = signal<0 | 90 | 180 | 270>(0);
  protected readonly flipHorizontal = signal(false);
  protected readonly flipVertical = signal(false);
  protected readonly zoom = signal(1);
  protected readonly aspecto = signal<number | undefined>(undefined);
  protected readonly rectangulo = signal<RectanguloDeRecorte | null>(null);
  protected readonly previaSrc = signal('');

  private origen: { x: number; y: number } | null = null;
  private imagenOriginal: HTMLImageElement | null = null;
  private lienzoHorneado: HTMLCanvasElement | null = null;
  private urlPreviaActual: string | null = null;

  private readonly transloco = inject(TranslocoService);

  constructor() {
    effect(
      () => {
        void this.cargarImagenOriginal(this.url());
      },
      { allowSignalWrites: true },
    );
    effect(
      () => {
        // Cualquier cambio de rotación/volteo invalida la selección: las
        // coordenadas normalizadas ya no describen el mismo recorte sobre
        // píxeles que acaban de cambiar de orientación.
        this.rotacion();
        this.flipHorizontal();
        this.flipVertical();
        // `hornear()` es asíncrono (toBlob) y ya atrapa sus propios errores
        // — un `effect` no debe dejar escapar una promesa rechazada sin
        // capturar (hallazgo de code-review).
        this.hornear();
      },
      { allowSignalWrites: true },
    );
    inject(DestroyRef).onDestroy(() => {
      if (this.urlPreviaActual) {
        URL.revokeObjectURL(this.urlPreviaActual);
      }
    });
  }

  private async cargarImagenOriginal(src: string): Promise<void> {
    this.cargando.set(true);
    this.error.set(null);
    try {
      const imagen = await new Promise<HTMLImageElement>((resolve, reject) => {
        const elemento = new Image();
        // Las URLs de medios pueden servirse desde un origen configurado
        // aparte del de la SPA (`S3_PUBLIC_BASE_URL`); sin esto, un origen
        // sin cabeceras CORS permisivas tiñe el canvas y `toBlob`/`toDataURL`
        // lanzan `SecurityError` más adelante en vez de fallar aquí, con un
        // mensaje claro (hallazgo de code-review).
        elemento.crossOrigin = 'anonymous';
        elemento.onload = () => resolve(elemento);
        elemento.onerror = () => reject(new Error('No se ha podido cargar la imagen.'));
        elemento.src = src;
      });
      this.imagenOriginal = imagen;
      this.rotacion.set(0);
      this.flipHorizontal.set(false);
      this.flipVertical.set(false);
      this.zoom.set(1);
      await this.hornearAsync();
    } catch {
      this.error.set(this.transloco.translate('comun.error'));
    } finally {
      this.cargando.set(false);
    }
  }

  private hornear(): void {
    void this.hornearAsync();
  }

  /** Redibuja la imagen original (nunca un resultado ya horneado) con la
   * rotación/volteo actuales: evita encadenar recodificaciones WEBP sobre
   * WEBP en cada pulsación de rotar. */
  private async hornearAsync(): Promise<void> {
    const original = this.imagenOriginal;
    if (!original) {
      return;
    }
    try {
      const rot = this.rotacion();
      const horizontal = rot === 90 || rot === 270;
      const anchoFinal = horizontal ? original.naturalHeight : original.naturalWidth;
      const altoFinal = horizontal ? original.naturalWidth : original.naturalHeight;
      const canvas = document.createElement('canvas');
      canvas.width = anchoFinal;
      canvas.height = altoFinal;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        throw new Error('Sin contexto 2D de canvas.');
      }
      ctx.save();
      ctx.translate(anchoFinal / 2, altoFinal / 2);
      // `scale` (volteo) se llama ANTES que `rotate`: en las transformaciones
      // de canvas, la última llamada es la primera en aplicarse al punto
      // dibujado — así `rotate` actúa primero (gira la imagen entera) y
      // `scale` voltea DESPUÉS, sobre el resultado ya girado. Llamados al
      // revés, el volteo se aplicaría en los ejes originales de la imagen,
      // no en los que el usuario ve tras rotar 90°/270° (hallazgo de
      // code-review).
      ctx.scale(this.flipHorizontal() ? -1 : 1, this.flipVertical() ? -1 : 1);
      ctx.rotate((rot * Math.PI) / 180);
      ctx.drawImage(original, -original.naturalWidth / 2, -original.naturalHeight / 2);
      ctx.restore();
      this.lienzoHorneado = canvas;
      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, 'image/webp', 0.92),
      );
      if (!blob) {
        throw new Error('No se ha podido generar la previsualización.');
      }
      const url = URL.createObjectURL(blob);
      if (this.urlPreviaActual) {
        URL.revokeObjectURL(this.urlPreviaActual);
      }
      this.urlPreviaActual = url;
      this.previaSrc.set(url);
      this.rectangulo.set(null);
    } catch {
      this.error.set(this.transloco.translate('comun.error'));
    }
  }

  /** Con una proporción fija, dibuja de inmediato una selección centrada de
   * ese ratio (mismo comportamiento que la referencia del usuario: elegir
   * "16:9" muestra ya un recuadro, no hace falta arrastrar a mano para
   * verlo) — antes limpiaba la selección a `null`, dejando la persona sin
   * ninguna vista previa hasta arrastrar (hallazgo del usuario). Con
   * "Libre" no se toca la selección ya dibujada: solo deja de forzar una
   * ratio en los arrastres siguientes. */
  protected elegirProporcion(valor: number | undefined): void {
    this.aspecto.set(valor);
    if (valor === undefined) {
      return;
    }
    const ratioEnFraccion = this.ratioEnFraccionDeImagen(valor);
    if (ratioEnFraccion === null) {
      this.rectangulo.set(null);
      return;
    }
    const { ancho, alto } = this.ajustarARatio(1, 1, ratioEnFraccion);
    this.rectangulo.set({ x: (1 - ancho) / 2, y: (1 - alto) / 2, width: ancho, height: alto });
  }

  protected rotar(grados: 90 | -90): void {
    this.rotacion.update((actual) => ((actual + grados + 360) % 360) as 0 | 90 | 180 | 270);
  }

  protected alternarVolteo(eje: 'horizontal' | 'vertical'): void {
    if (eje === 'horizontal') {
      this.flipHorizontal.update((v) => !v);
    } else {
      this.flipVertical.update((v) => !v);
    }
  }

  private posicionRelativa(evento: PointerEvent): { x: number; y: number } {
    const imagen = this.imgPrevia();
    if (!imagen) {
      return { x: 0, y: 0 };
    }
    const caja = imagen.nativeElement.getBoundingClientRect();
    const x = Math.min(Math.max((evento.clientX - caja.left) / caja.width, 0), 1);
    const y = Math.min(Math.max((evento.clientY - caja.top) / caja.height, 0), 1);
    return { x, y };
  }

  protected alEmpezar(evento: PointerEvent): void {
    // Sin esto, un arrastre rápido que saca el puntero del lienzo (ahora con
    // scroll por el zoom) deja de recibir `pointermove`/`pointerup` y la
    // selección se queda congelada a medio arrastrar (hallazgo de
    // code-review) — capturar el puntero en el propio lienzo evita que se
    // "pierda" al salir de sus límites.
    (evento.currentTarget as HTMLElement).setPointerCapture(evento.pointerId);
    this.origen = this.posicionRelativa(evento);
    this.rectangulo.set(null);
  }

  protected alArrastrar(evento: PointerEvent): void {
    if (!this.origen || evento.buttons === 0) {
      return;
    }
    const actual = this.posicionRelativa(evento);
    this.rectangulo.set(this.calcularRectangulo(this.origen, actual));
  }

  /** Sin restricción de proporción, el rectángulo es el arrastre libre de
   * siempre. Con una proporción fija, ajusta la dimensión que sobre para no
   * salirse de lo arrastrado, y recorta contra el borde de la imagen sin
   * perder la ratio elegida. */
  private calcularRectangulo(
    origen: { x: number; y: number },
    actual: { x: number; y: number },
  ): RectanguloDeRecorte {
    const signoX = actual.x >= origen.x ? 1 : -1;
    const signoY = actual.y >= origen.y ? 1 : -1;
    let ancho = Math.abs(actual.x - origen.x);
    let alto = Math.abs(actual.y - origen.y);
    const ratio = this.aspecto();
    const ratioEnFraccion = ratio ? this.ratioEnFraccionDeImagen(ratio) : null;

    if (ratioEnFraccion) {
      ({ ancho, alto } = this.ajustarARatio(ancho, alto, ratioEnFraccion));
    }

    ancho = Math.min(ancho, signoX >= 0 ? 1 - origen.x : origen.x);
    alto = Math.min(alto, signoY >= 0 ? 1 - origen.y : origen.y);

    if (ratioEnFraccion) {
      ({ ancho, alto } = this.ajustarARatio(ancho, alto, ratioEnFraccion));
    }

    const x = signoX >= 0 ? origen.x : origen.x - ancho;
    const y = signoY >= 0 ? origen.y : origen.y - alto;
    return { x, y, width: ancho, height: alto };
  }

  /** Ajusta `ancho`/`alto` para que cumplan `ratioEnFraccion` exactamente,
   * recortando siempre la dimensión que sobre — nunca crece ninguna de las
   * dos más allá de lo ya calculado. Compartido entre el ajuste inicial (a
   * partir del arrastre libre) y el reajuste tras recortar contra el borde
   * de la imagen: antes eran dos copias casi idénticas (hallazgo de
   * code-review). */
  private ajustarARatio(
    ancho: number,
    alto: number,
    ratioEnFraccion: number,
  ): { ancho: number; alto: number } {
    const altoDesdeAncho = ancho / ratioEnFraccion;
    if (altoDesdeAncho <= alto) {
      return { ancho, alto: altoDesdeAncho };
    }
    return { ancho: alto * ratioEnFraccion, alto };
  }

  /** Convierte una proporción en píxeles reales (p. ej. 16/9) a la misma
   * proporción expresada en fracciones (0-1) del rectángulo mostrado, que
   * depende de cómo de ancha/alta se vea la imagen actual. `null` si el
   * lienzo todavía no tiene tamaño real (p. ej. un arrastre disparado antes
   * de que el `<img>` recién actualizado termine su primer layout) — evita
   * dividir por cero y propagar `NaN` hasta el recorte final (hallazgo de
   * code-review). */
  private ratioEnFraccionDeImagen(ratioEnPixeles: number): number | null {
    const imagen = this.imgPrevia();
    if (!imagen) {
      return null;
    }
    const caja = imagen.nativeElement.getBoundingClientRect();
    if (caja.width === 0 || caja.height === 0) {
      return null;
    }
    return (ratioEnPixeles * caja.height) / caja.width;
  }

  protected alSoltar(evento: PointerEvent): void {
    try {
      (evento.currentTarget as HTMLElement).releasePointerCapture(evento.pointerId);
    } catch {
      // Sin captura previa (p. ej. `pointercancel` sin arrastre iniciado) no
      // hay nada que liberar — no es un error real.
    }
    this.origen = null;
    const r = this.rectangulo();
    if (r && (r.width < UMBRAL_MINIMO || r.height < UMBRAL_MINIMO)) {
      this.rectangulo.set(null);
    }
  }

  protected async confirmar(): Promise<void> {
    const r = this.rectangulo();
    const horneado = this.lienzoHorneado;
    if (!r || !horneado) {
      return;
    }
    this.generando.set(true);
    this.error.set(null);
    try {
      const blob = await this.recortarAPngWebp(horneado, r);
      if (!blob) {
        this.error.set(this.transloco.translate('comun.error'));
        return;
      }
      this.confirmado.emit(blob);
    } finally {
      this.generando.set(false);
    }
  }

  private recortarAPngWebp(horneado: HTMLCanvasElement, r: RectanguloDeRecorte): Promise<Blob | null> {
    const anchoPx = Math.max(1, Math.round(r.width * horneado.width));
    const altoPx = Math.max(1, Math.round(r.height * horneado.height));
    const canvas = document.createElement('canvas');
    canvas.width = anchoPx;
    canvas.height = altoPx;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return Promise.resolve(null);
    }
    ctx.drawImage(
      horneado,
      Math.round(r.x * horneado.width),
      Math.round(r.y * horneado.height),
      anchoPx,
      altoPx,
      0,
      0,
      anchoPx,
      altoPx,
    );
    return new Promise((resolve) => canvas.toBlob(resolve, 'image/webp', 0.85));
  }
}
