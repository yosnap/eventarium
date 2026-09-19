import { ChangeDetectionStrategy, Component, input, output, viewChild } from '@angular/core';

import { Dialog } from './dialog';
import { MediaElegida, MediaFields, MediaKind } from './media-fields';

/**
 * `MediaFields` envuelto en `Dialog`, para el caso "cambiar" de
 * `MediaPicker`: ya hay una imagen elegida, así que el dropzone/pestañas no
 * ocupan el espacio del campo, se muestran en un modal aparte.
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
        [kind]="kind()"
        [etiqueta]="titulo()"
        [permitirUrl]="permitirUrl()"
        (mediaElegido)="alElegirMedia($event)"
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
  readonly kind = input.required<MediaKind>();
  /** Si el consumidor puede elegir/subir por URL (ver `MediaFields`). */
  readonly permitirUrl = input(true);

  /** El medio elegido, por cualquiera de las 3 vías (ver `MediaFields`). */
  readonly mediaElegido = output<MediaElegida>();
  readonly cerrado = output<void>();

  private readonly dialogo = viewChild.required(Dialog);
  private readonly campos = viewChild.required(MediaFields);

  abrir(): void {
    this.campos().reiniciar();
    this.dialogo().abrir();
  }

  protected alElegirMedia(media: MediaElegida): void {
    this.mediaElegido.emit(media);
    this.dialogo().cerrar();
  }
}
