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
 * pasa a previsualización + "Cambiar", que sí abre el modal (`MediaDialog`)
 * — ahí sí hace falta, para no ocupar el espacio del campo con el dropzone
 * entero solo por sustituir una imagen que ya se ve bien.
 *
 * Sin "Quitar" a propósito: ninguno de los 4 endpoints de asignación
 * (logo de organización, identidad de plataforma, portada de evento, logo
 * de patrocinador) admite desasignar (no hay contrato `{media_id: null}`),
 * así que un botón "Quitar" que solo limpiara el campo local sería
 * engañoso — la imagen seguiría asignada de verdad en el servidor y
 * reaparecería al recargar o al guardar (hallazgo de code-review). Enviar
 * una imagen a la papelera SIGUE siendo una acción real, pero vive dentro
 * del modal de biblioteca (`MediaFields`), no aquí.
 */
@Component({
  selector: 'app-media-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, MediaDialog, MediaFields],
  template: `
    <ng-container *transloco="let t">
      <span class="etiqueta">{{ etiqueta() }}</span>
      @if (url(); as actual) {
        <div class="campo" [class.campo-ancho]="variante() === 'ancha'">
          <img
            class="previsualizacion"
            [class.previsualizacion-ancha]="variante() === 'ancha'"
            [src]="actual"
            [alt]="etiqueta()"
          />
          <div class="acciones">
            <app-button variant="secundario" type="button" (pulsado)="abrir()">
              {{ t('ui.media.cambiar') }}
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
    /* Portada de evento: mismo criterio visual que .portada en la propia
       ficha pública (event-page.ts) — ancho completo, recorte por
       object-fit: cover, tope de altura en vez del 4rem cuadrado
       genérico del resto de campos (logos, mucho más pequeños en la
       página real). aspect-ratio: 16/9 es una aproximación fija a la
       franja fluida de la ficha (ahí no hay una ratio única, es
       width:100%; max-height:20rem) — razonable para una vista previa
       en un formulario, no una réplica exacta pixel a pixel. */
    .campo-ancho {
      display: block;
    }
    .previsualizacion {
      width: 4rem;
      height: 4rem;
      object-fit: contain;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
    }
    .previsualizacion-ancha {
      width: 100%;
      height: auto;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border-radius: var(--radius-lg);
      margin-bottom: var(--space-sm);
    }
    .campo-ancho .acciones {
      display: block;
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
  /** `'compacta'` (por defecto): miniatura cuadrada de 4rem, para logos.
   * `'ancha'`: previsualización a todo el ancho del contenedor con la
   * proporción de una portada de evento (16:9) — ver comentario del CSS. */
  readonly variante = input<'compacta' | 'ancha'>('compacta');
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
  private anterior: { url: string | null; mediaId: string | null } | null = null;

  protected abrir(): void {
    this.dialogo().abrir();
  }

  protected alElegirMedia(media: MediaElegida): void {
    this.anterior = { url: this.url(), mediaId: this.mediaId() };
    this.url.set(media.url);
    this.mediaId.set(media.id);
    this.mediaElegido.emit(media);
  }

  /** Para quien asigna de inmediato (sin guardado diferido): si la
   * petición de asignación falla, la previsualización no debe seguir
   * mostrando la imagen nueva como si estuviera guardada — el consumidor
   * llama a esto desde su propio `catch` (hallazgo de code-review). */
  revertir(): void {
    if (this.anterior) {
      this.url.set(this.anterior.url);
      this.mediaId.set(this.anterior.mediaId);
      this.anterior = null;
    }
  }
}
