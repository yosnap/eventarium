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
import { MediaFields } from './media-fields';

/**
 * Campo de selección de imagen.
 *
 * Sin imagen todavía, muestra el dropzone/pestañas (`MediaFields`) directo
 * en la página: abrir un modal para el primer paso sería fricción de más
 * cuando no hay nada que el modal tenga que tapar. Con imagen ya elegida,
 * pasa a previsualización + Cambiar/Quitar, y "Cambiar" sí abre el modal
 * (`MediaDialog`) — ahí sí hace falta, para no ocupar el espacio del campo
 * con el dropzone entero solo por sustituir una imagen que ya se ve bien.
 *
 * Referencia: el media picker de Coetools — valor plano por URL, preview
 * dentro del campo, y la gestión del fichero fuera del componente.
 */
@Component({
  selector: 'app-media-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, MediaDialog, MediaFields],
  template: `
    <ng-container *transloco="let t">
      <span class="etiqueta">{{ etiqueta() }}</span>
      @if (url(); as actual) {
        <div class="campo">
          <img class="previsualizacion" [src]="actual" [alt]="etiqueta()" />
          <div class="acciones">
            <app-button variant="secundario" type="button" (pulsado)="abrir()">
              {{ t('ui.media.cambiar') }}
            </app-button>
            <app-button variant="terciario" type="button" (pulsado)="quitar()">
              {{ t('ui.media.quitar') }}
            </app-button>
          </div>
        </div>
      } @else {
        <app-media-fields
          [aceptados]="aceptados()"
          [biblioteca]="biblioteca()"
          [tituloBiblioteca]="etiqueta()"
          (ficheroElegido)="ficheroElegido.emit($event)"
          (urlElegida)="url.set($event)"
        />
      }

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
