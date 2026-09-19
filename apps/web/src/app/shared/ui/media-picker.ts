import { ChangeDetectionStrategy, Component, input, model, output, viewChild } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from './button';
import { MediaDialog } from './media-dialog';
import { MediaElegida, MediaFields, MediaKind } from './media-fields';

export type { MediaElegida, MediaKind };

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
 * "Quitar" es puramente local (limpia `url`/`mediaId`): nunca llama a
 * `DELETE .../media/{id}` — enviar una imagen a la papelera es una acción
 * explícita nueva, dentro del modal de biblioteca (`MediaFields`), no algo
 * que "Quitar" haga de forma implícita (hallazgo de red-team 11).
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
          [kind]="kind()"
          [etiqueta]="etiqueta()"
          [permitirUrl]="permitirUrl()"
          (mediaElegido)="alElegirMedia($event)"
        />
      }

      <app-media-dialog
        #dialogo
        [titulo]="etiqueta()"
        [aceptados]="aceptados()"
        [kind]="kind()"
        [permitirUrl]="permitirUrl()"
        (mediaElegido)="alElegirMedia($event)"
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
  readonly kind = input.required<MediaKind>();
  /** Si el consumidor puede elegir/subir por URL (ver `MediaFields`). */
  readonly permitirUrl = input(true);

  /** La URL de la imagen a previsualizar, en doble enlace — el consumidor la
   * inicializa con lo que ya tenga guardado (p. ej. `branding.logo_url`). */
  readonly url = model<string | null>(null);
  /** El `id` del medio recién elegido, en doble enlace — `null` mientras no
   * se haya elegido nada nuevo (no significa "sin imagen": `url()` puede
   * seguir mostrando la ya guardada). El consumidor lo lee al guardar para
   * llamar a su propio endpoint de asignación con `{media_id}`. */
  readonly mediaId = model<string | null>(null);

  /** Igual información que los dos `model` de arriba, como evento — para
   * quien prefiera reaccionar a la elección (p. ej. subir de inmediato)
   * en vez de leer los signals tras el hecho. */
  readonly mediaElegido = output<MediaElegida>();

  private readonly dialogo = viewChild.required(MediaDialog);

  protected abrir(): void {
    this.dialogo().abrir();
  }

  protected alElegirMedia(media: MediaElegida): void {
    this.url.set(media.url);
    this.mediaId.set(media.id);
    this.mediaElegido.emit(media);
  }

  protected quitar(): void {
    this.url.set(null);
    this.mediaId.set(null);
  }
}
