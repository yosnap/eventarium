import { ChangeDetectionStrategy, Component, ElementRef, input, output, signal, viewChild } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from './button';

/** Rectángulo normalizado (0-1 respecto al tamaño de la imagen) — mismo
 * contrato que `MediaCropRequest` en el backend. */
export interface RectanguloDeRecorte {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

/**
 * Editor de recorte: arrastra un rectángulo sobre la imagen con el puntero.
 *
 * Sin `<canvas>` a propósito — dibujar un rectángulo de selección es una
 * superposición posicionada en porcentajes sobre la propia `<img>`, no
 * justifica reescribir la imagen a mano en un lienzo. El recorte real (los
 * píxeles) lo hace el servidor con Pillow al confirmar (`PATCH
 * .../media/{id}/crop`), este componente solo produce el rectángulo.
 */
@Component({
  selector: 'app-media-crop-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button],
  template: `
    <ng-container *transloco="let t">
      <p class="instruccion">{{ t('ui.media.arrastraParaRecortar') }}</p>
      <div
        #lienzo
        class="lienzo"
        (pointerdown)="alEmpezar($event)"
        (pointermove)="alArrastrar($event)"
        (pointerup)="alSoltar()"
        (pointercancel)="alSoltar()"
      >
        <img [src]="url()" alt="" />
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
      <div class="acciones">
        <app-button variant="secundario" type="button" (pulsado)="cancelado.emit()">
          {{ t('comun.cancelar') }}
        </app-button>
        <app-button
          type="button"
          [disabled]="!rectangulo() || confirmando()"
          [loading]="confirmando()"
          (pulsado)="confirmar()"
        >
          {{ t('ui.media.confirmarRecorte') }}
        </app-button>
      </div>
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
    .lienzo {
      position: relative;
      max-height: 20rem;
      overflow: hidden;
      border-radius: var(--radius-md);
      touch-action: none;
      cursor: crosshair;
      user-select: none;
    }
    .lienzo img {
      display: block;
      width: 100%;
      max-height: 20rem;
      object-fit: contain;
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
  /** Imagen sobre la que recortar. */
  readonly url = input.required<string>();
  /** Refleja que la confirmación está en curso (deshabilita los controles). */
  readonly confirmando = input(false);

  /** Rectángulo normalizado elegido, listo para `PATCH .../crop`. */
  readonly confirmado = output<RectanguloDeRecorte>();
  readonly cancelado = output<void>();

  private readonly lienzo = viewChild.required<ElementRef<HTMLDivElement>>('lienzo');

  protected readonly rectangulo = signal<RectanguloDeRecorte | null>(null);
  private origen: { x: number; y: number } | null = null;

  private posicionRelativa(evento: PointerEvent): { x: number; y: number } {
    const caja = this.lienzo().nativeElement.getBoundingClientRect();
    const x = Math.min(Math.max((evento.clientX - caja.left) / caja.width, 0), 1);
    const y = Math.min(Math.max((evento.clientY - caja.top) / caja.height, 0), 1);
    return { x, y };
  }

  protected alEmpezar(evento: PointerEvent): void {
    this.origen = this.posicionRelativa(evento);
    this.rectangulo.set(null);
  }

  protected alArrastrar(evento: PointerEvent): void {
    if (!this.origen || evento.buttons === 0) {
      return;
    }
    const actual = this.posicionRelativa(evento);
    const x = Math.min(this.origen.x, actual.x);
    const y = Math.min(this.origen.y, actual.y);
    const width = Math.abs(actual.x - this.origen.x);
    const height = Math.abs(actual.y - this.origen.y);
    this.rectangulo.set({ x, y, width, height });
  }

  protected alSoltar(): void {
    this.origen = null;
    // Un arrastre demasiado pequeño (clic sin mover apenas) no es un recorte
    // útil — se descarta en vez de dejar un rectángulo de anchura casi nula.
    const r = this.rectangulo();
    if (r && (r.width < 0.02 || r.height < 0.02)) {
      this.rectangulo.set(null);
    }
  }

  protected confirmar(): void {
    const r = this.rectangulo();
    if (r) {
      this.confirmado.emit(r);
    }
  }
}
