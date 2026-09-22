import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import { ApiError } from '../../core/api/error.interceptor';
import { Button } from './button';
import { Dialog } from './dialog';
import { Input } from './input';
import { MediaCropEditor } from './media-crop-editor';
import { MediaFolder, MediaItem, MediaKind, baseDeMedia } from './media-types';

/**
 * Modal «Editar imagen» de la biblioteca de medios: metadatos (nombre, texto
 * alternativo, carpeta) y recorte, en un único sitio — reemplaza el swap
 * inline a `MediaCropEditor` que antes vivía dentro de `MediaFields`.
 *
 * Adaptado a lo que el proyecto tiene de verdad (sin título bilingüe ni
 * descripción, que no existen en el modelo `Media`; ver
 * `plans/260922-0125-prd-iconos-hover-biblioteca-medios/prd-modal-editar-imagen.md`).
 *
 * Las dos secciones tienen guardado independiente: los metadatos son un
 * `PATCH` en el mismo recurso; el recorte crea un `Media` **nuevo** (decisión
 * ya cerrada en `plans/260921-1720-prd-editor-recorte-imagen`, no se
 * reabre aquí). Fusionarlas en un único botón fingiría una semántica de
 * "sobrescribir" que no existe. Ninguna de las dos cierra el modal sola —
 * cerrar es una acción explícita de la persona, para poder encadenar ambas
 * sin perder el modal a mitad de camino.
 *
 * `confirmarRecorte` **no emite ningún evento de "elegir imagen para un
 * campo"** (a diferencia del `MediaCropEditor` embebido en el flujo de
 * selección de `MediaFields`): este modal se abre desde la *gestión* de la
 * biblioteca (icono de lápiz), no desde la elección de imagen de un campo.
 * Emitirlo reasignaría en silencio la imagen de cualquier campo que hubiera
 * abierto el selector por debajo (hallazgo de red-team) — aquí solo se
 * refresca la rejilla de la biblioteca.
 */
@Component({
  selector: 'app-media-edit-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, Dialog, Input, MediaCropEditor],
  template: `
    <ng-container *transloco="let t">
      <app-dialog #dialogo>
        @if (item(); as actual) {
          <h3 class="titulo">{{ t('ui.media.editarImagenTitulo') }}</h3>

          @if (error(); as mensaje) {
            <p class="error">{{ mensaje }}</p>
          }

          <section class="metadatos">
            <app-input
              [label]="t('ui.media.nombreEtiqueta')"
              [value]="nombre()"
              (valueChange)="nombre.set($event)"
            />
            <app-input
              [label]="t('ui.media.altEtiqueta')"
              [value]="alt()"
              (valueChange)="alt.set($event)"
            />
            @if (carpetas().length > 0) {
              <label class="carpeta-campo">
                {{ t('ui.media.carpetaEtiqueta') }}
                <select [value]="carpetaId() ?? ''" (change)="alCambiarCarpeta($event)">
                  <option value="">{{ t('ui.media.todasLasCarpetas') }}</option>
                  @for (carpeta of carpetas(); track carpeta.id) {
                    <option [value]="carpeta.id">{{ carpeta.name }}</option>
                  }
                </select>
              </label>
            }
            <app-button
              type="button"
              variant="secundario"
              [disabled]="!nombre().trim() || guardandoMetadatos()"
              [loading]="guardandoMetadatos()"
              (pulsado)="guardarMetadatos()"
            >
              {{
                guardandoMetadatos()
                  ? t('ui.media.guardandoCambios')
                  : t('ui.media.guardarCambios')
              }}
            </app-button>
          </section>

          <section class="recorte">
            <app-media-crop-editor
              [url]="actual.url"
              [confirmando]="recortandoEnCurso()"
              (confirmado)="confirmarRecorte($event)"
              (cancelado)="cancelarRecorte()"
            />
          </section>
        }
      </app-dialog>
    </ng-container>
  `,
  styles: `
    .titulo {
      margin: 0 0 var(--sp-3);
    }
    .error {
      color: var(--danger);
      font-size: var(--fs-sm);
      margin: 0 0 var(--space-sm);
    }
    .metadatos {
      display: grid;
      gap: var(--space-sm);
      padding-bottom: var(--sp-4);
      margin-bottom: var(--sp-4);
      border-bottom: 1px solid var(--border);
    }
    .carpeta-campo {
      display: grid;
      gap: var(--space-xs);
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .carpeta-campo select {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      font: inherit;
      background: var(--surface);
      color: var(--fg);
    }
  `,
})
export class MediaEditDialog {
  readonly kind = input.required<MediaKind>();
  readonly carpetas = input<readonly MediaFolder[]>([]);

  /** Los metadatos (nombre/alt/carpeta) se guardaron — el padre refresca
   * su rejilla. */
  readonly metadatosGuardados = output<void>();
  /** El recorte se confirmó y subió como `Media` nuevo — el padre refresca
   * su rejilla. Sin `id`/`url`: ver el JSDoc de la clase, este modal no
   * elige imagen para ningún campo. */
  readonly recorteGuardado = output<void>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly dialogo = viewChild.required(Dialog);

  protected readonly item = signal<MediaItem | null>(null);
  protected readonly nombre = signal('');
  protected readonly alt = signal('');
  protected readonly carpetaId = signal<string | null>(null);
  protected readonly guardandoMetadatos = signal(false);
  protected readonly recortandoEnCurso = signal(false);
  protected readonly error = signal<string | null>(null);

  abrir(item: MediaItem): void {
    this.item.set(item);
    this.nombre.set(item.filename);
    this.alt.set(item.alt ?? '');
    this.carpetaId.set(item.folder_id);
    this.error.set(null);
    this.dialogo().abrir();
  }

  protected alCambiarCarpeta(evento: Event): void {
    this.carpetaId.set((evento.target as HTMLSelectElement).value || null);
  }

  /** El "Cancelar" del propio `MediaCropEditor` solo significa "descarto
   * este arrastre de selección" — nunca "cierro el modal entero" (hallazgo
   * de code-review: cerrar aquí descartaba en silencio cambios de nombre/
   * alt/carpeta sin guardar, ya escritos pero no confirmados todavía).
   * Cerrar el modal sigue siendo una acción explícita de la persona
   * (botón/Escape del propio `<dialog>`), no una consecuencia de cancelar
   * el recorte. */
  protected cancelarRecorte(): void {
    this.error.set(null);
  }

  protected async guardarMetadatos(): Promise<void> {
    const actual = this.item();
    const nombre = this.nombre().trim();
    if (!actual || !nombre) {
      return;
    }
    this.guardandoMetadatos.set(true);
    this.error.set(null);
    try {
      const alt = this.alt().trim();
      const actualizado = await firstValueFrom(
        this.http.patch<MediaItem>(`${this.api.url(baseDeMedia(this.kind()))}/${actual.id}`, {
          filename: nombre,
          alt: alt || null,
          folder_id: this.carpetaId(),
        }),
      );
      // Guarda solo si el modal sigue mostrando el mismo item: si se cerró
      // y se reabrió para otro (`abrir()`) mientras este PATCH seguía en
      // vuelo, una respuesta tardía no debe pisar el formulario ya en uso
      // para el nuevo item (hallazgo de code-review).
      if (this.item()?.id === actual.id) {
        this.item.set(actualizado);
      }
      this.metadatosGuardados.emit();
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.guardandoMetadatos.set(false);
    }
  }

  /** Trasladado tal cual desde `MediaFields.confirmarRecorte` (antes de
   * `260922-0125-prd-iconos-hover-biblioteca-medios`, fase 2) — misma lógica
   * de subida y herencia de carpeta, sin reescribir. Único cambio real: no
   * emite ningún evento de "imagen elegida" (ver JSDoc de la clase). */
  protected async confirmarRecorte(blob: Blob): Promise<void> {
    const actual = this.item();
    if (!actual) {
      return;
    }
    this.recortandoEnCurso.set(true);
    this.error.set(null);
    try {
      const datos = new FormData();
      datos.append('fichero', blob, `${actual.filename}-recorte.webp`);
      if (this.kind() !== 'platform') {
        datos.append('kind', this.kind());
      }
      const nuevo = await firstValueFrom(
        this.http.post<MediaItem>(this.api.url(baseDeMedia(this.kind())), datos),
      );
      // La subida genérica no acepta `folder_id` — el recorte SÍ conoce su
      // carpeta (heredada del original), así que hace falta un segundo paso
      // explícito para no perderla. No atómico con la subida: si este paso
      // falla, el recorte YA existe y ya es válido (solo queda en la raíz en
      // vez de su carpeta), así que se trata como un fallo menor que no debe
      // impedir ofrecer el resultado.
      if (actual.folder_id) {
        try {
          await firstValueFrom(
            this.http.patch<MediaItem>(`${this.api.url(baseDeMedia(this.kind()))}/${nuevo.id}`, {
              folder_id: actual.folder_id,
            }),
          );
        } catch {
          // Ignorado a propósito: ver comentario de arriba.
        }
      }
      this.recorteGuardado.emit();
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.recortandoEnCurso.set(false);
    }
  }

  private mensajeDeError(error: unknown): string {
    return error instanceof ApiError ? error.message : this.transloco.translate('comun.error');
  }
}
