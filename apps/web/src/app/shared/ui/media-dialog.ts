import { ChangeDetectionStrategy, Component, input, output, viewChild } from '@angular/core';

import { Dialog } from './dialog';
import { MediaFields } from './media-fields';

/**
 * `MediaFields` envuelto en `Dialog`, para el caso "cambiar" de
 * `MediaPicker`: ya hay una imagen elegida, así que el dropzone/pestañas no
 * ocupan el espacio del campo, se muestran en un modal aparte.
 *
 * Dos salidas excluyentes según la pestaña activa dentro de `MediaFields`:
 * - `ficheroElegido`: un `File` — quien llama lo sube con su propio endpoint
 *   (la subida es de cada pantalla: logo de identidad, cover de evento…).
 * - `urlElegida`: la URL escrita o elegida de la biblioteca.
 */
@Component({
  selector: 'app-media-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Dialog, MediaFields],
  template: `
    <app-dialog #dialogo (cerrado)="cerrado.emit()">
      <h3 class="titulo">{{ titulo() }}</h3>
      <app-media-fields
        #campos
        [aceptados]="aceptados()"
        [biblioteca]="biblioteca()"
        [tituloBiblioteca]="titulo()"
        [permitirUrl]="permitirUrl()"
        (ficheroElegido)="alElegirFichero($event)"
        (urlElegida)="alElegirUrl($event)"
      />
    </app-dialog>
  `,
  styles: `
    .titulo {
      margin: 0 0 var(--sp-3);
    }
  `,
})
export class MediaDialog {
  readonly titulo = input.required<string>();
  /** Tipos aceptados por el selector de fichero (igual que `accept`). */
  readonly aceptados = input.required<string>();
  /** Imágenes existentes para la pestaña Biblioteca (opcional). */
  readonly biblioteca = input<readonly { url: string; etiqueta: string }[]>([]);
  /** Si el consumidor puede persistir una URL elegida (ver `MediaFields`). */
  readonly permitirUrl = input(true);

  /** El `File` elegido en la pestaña Subir. */
  readonly ficheroElegido = output<File>();
  /** La URL escrita o elegida de la biblioteca. */
  readonly urlElegida = output<string>();
  readonly cerrado = output<void>();

  private readonly dialogo = viewChild.required(Dialog);
  private readonly campos = viewChild.required(MediaFields);

  abrir(): void {
    this.campos().reiniciar();
    this.dialogo().abrir();
  }

  protected alElegirFichero(fichero: File): void {
    this.ficheroElegido.emit(fichero);
    this.dialogo().cerrar();
  }

  protected alElegirUrl(url: string): void {
    this.urlElegida.emit(url);
    this.dialogo().cerrar();
  }
}
