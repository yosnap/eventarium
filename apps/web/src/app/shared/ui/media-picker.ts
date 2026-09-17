import {
  ChangeDetectionStrategy,
  Component,
  input,
  model,
  output,
  viewChild,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from './button';
import { MediaDialog } from './media-dialog';

/**
 * Campo de selección de imagen: previsualización de la actual y acciones
 * Elegir/Quitar. Abre el `MediaDialog` (pestañas Subir/URL/Biblioteca) y
 * expone los dos resultados por separado — `ficheroElegido` (quien llama lo
 * sube con su propio endpoint) y el `model` de URL (para una URL escrita o
 * elegida de la biblioteca).
 *
 * Referencia: el media picker de Coetools — valor plano por URL, preview
 * dentro del campo, y la gestión del fichero fuera del componente.
 */
@Component({
  selector: 'app-media-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, MediaDialog],
  template: `
    <ng-container *transloco="let t">
      <span class="etiqueta">{{ etiqueta() }}</span>
      <div class="campo">
        @if (url(); as actual) {
          <img class="previsualizacion" [src]="actual" [alt]="etiqueta()" />
        } @else {
          <span class="vacio">{{ t('ui.media.sinImagen') }}</span>
        }
        <div class="acciones">
          <app-button variant="secundario" type="button" (pulsado)="abrir()">
            {{ url() ? t('ui.media.cambiar') : t('ui.media.elegir') }}
          </app-button>
          @if (url()) {
            <app-button variant="terciario" type="button" (pulsado)="quitar()">
              {{ t('ui.media.quitar') }}
            </app-button>
          }
        </div>
      </div>

      <app-media-dialog
        #dialogo
        [titulo]="etiqueta()"
        [aceptados]="aceptados()"
        [biblioteca]="biblioteca()"
        (ficheroElegido)="ficheroElegido.emit($event)"
        (urlElegida)="url.set($event)"
      />
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .etiqueta {
      display: block;
      font-size: var(--fs-sm);
      color: var(--muted);
      margin-bottom: var(--space-xs);
    }
    .campo {
      display: flex;
      align-items: center;
      gap: var(--sp-3);
    }
    .previsualizacion {
      width: 4rem;
      height: 4rem;
      object-fit: contain;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
    }
    .vacio {
      display: grid;
      place-items: center;
      width: 4rem;
      height: 4rem;
      border: 2px dashed var(--border-strong);
      border-radius: var(--radius-md);
      color: var(--faint);
      font-size: var(--fs-xs, 0.75rem);
      text-align: center;
    }
    .acciones {
      display: grid;
      gap: var(--space-xs);
    }
  `,
})
export class MediaPicker {
  /** Rótulo del campo (etiqueta accesible de la imagen y del diálogo). */
  readonly etiqueta = input.required<string>();
  /** Tipos aceptados por el selector de fichero. */
  readonly aceptados = input.required<string>();
  /** Imágenes existentes para la pestaña Biblioteca (opcional). */
  readonly biblioteca = input<readonly { url: string; etiqueta: string }[]>([]);

  /** La URL actual de la imagen, en doble enlace. */
  readonly url = model<string | null>(null);

  /** El `File` elegido en la pestaña Subir (lo sube quien usa el campo). */
  readonly ficheroElegido = output<File>();

  private readonly dialogo = viewChild.required(MediaDialog);

  protected abrir(): void {
    this.dialogo().abrir();
  }

  protected quitar(): void {
    this.url.set(null);
  }
}
