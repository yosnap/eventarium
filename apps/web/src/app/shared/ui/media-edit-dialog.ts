import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
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
import { MediaCropEditor, ResultadoDeRecorte } from './media-crop-editor';
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
 * Los metadatos son un `PATCH` en el mismo recurso. El recorte ofrece las
 * DOS vías de la referencia del usuario — «Guardar como nueva» (crea un
 * `Media` nuevo, comportamiento de siempre) y «Sobrescribir original»
 * (`PUT .../contenido`, misma `id`/URL): esto REABRE la decisión "el recorte
 * siempre crea un Media nuevo" de `plans/260921-1720-prd-editor-recorte-
 * imagen`, a petición explícita y directa del usuario en esta sesión (no una
 * inferencia ni un hallazgo de auditoría) — ver
 * `plans/260922-0125-prd-iconos-hover-biblioteca-medios/prd-modal-editar-imagen.md`.
 *
 * "Cancelar" (dentro de `MediaCropEditor`) cierra el modal entero, igual
 * que la referencia del usuario y que el resto de diálogos del proyecto —
 * es la lectura convencional de "cancelar" en cualquier modal, incluida la
 * propia referencia que también descarta ahí cualquier cambio de metadatos
 * sin guardar. Guardar los metadatos sigue sin cerrar el modal (para poder
 * encadenar con el recorte sin perderlo a mitad de camino); confirmar el
 * recorte (cualquiera de las dos vías) sí cierra, porque ahí ya no queda
 * nada más que hacer.
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
  imports: [DatePipe, TranslocoDirective, Button, Dialog, Input, MediaCropEditor],
  template: `
    <ng-container *transloco="let t">
      <app-dialog #dialogo tamano="ancho">
        @if (item(); as actual) {
          <h3 class="titulo">{{ t('ui.media.editarImagenTitulo') }}</h3>

          @if (error(); as mensaje) {
            <p class="error">{{ mensaje }}</p>
          }

          <div class="contenido">
            <section class="recorte">
              <app-media-crop-editor
                [url]="actual.url"
                [confirmando]="recortandoEnCurso()"
                (confirmado)="confirmarRecorte($event)"
                (cancelado)="dialogo.cerrar()"
              />
            </section>

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
                    <option value="" [selected]="carpetaId() === null">
                      {{ t('ui.media.todasLasCarpetas') }}
                    </option>
                    @for (carpeta of carpetas(); track carpeta.id) {
                      <option [value]="carpeta.id" [selected]="carpeta.id === carpetaId()">
                        {{ carpeta.name }}
                      </option>
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

              <dl class="datos-imagen">
                <dt>{{ t('ui.media.dimensiones') }}</dt>
                <dd>
                  {{ actual.width && actual.height ? actual.width + ' × ' + actual.height + ' px' : '—' }}
                </dd>
                <dt>{{ t('ui.media.tamano') }}</dt>
                <dd>{{ formatearTamano(actual.size) }}</dd>
                <dt>{{ t('ui.media.subida') }}</dt>
                <dd>{{ actual.created_at | date: 'medium' }}</dd>
              </dl>
              <app-button type="button" variant="secundario" (pulsado)="copiarUrl(actual.url)">
                {{ urlCopiada() ? t('ui.media.urlCopiada') : t('ui.media.copiarUrl') }}
              </app-button>
            </section>
          </div>
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
    /* Dos columnas como la referencia (recorte más ancho que metadatos) a
       partir de 48rem; apiladas debajo, el modal ancho no cabe cómodo en
       pantallas estrechas. */
    .contenido {
      display: grid;
      gap: var(--sp-5);
    }
    @media (min-width: 48rem) {
      .contenido {
        grid-template-columns: 1.4fr 1fr;
        align-items: start;
      }
    }
    .metadatos {
      display: grid;
      gap: var(--space-sm);
      align-content: start;
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
    .datos-imagen {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 0.25rem var(--space-sm);
      margin: 0;
      padding-top: var(--space-sm);
      border-top: 1px solid var(--border);
      font-size: var(--fs-sm);
    }
    .datos-imagen dt {
      color: var(--muted);
    }
    .datos-imagen dd {
      margin: 0;
      color: var(--fg);
      text-align: right;
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
  protected readonly urlCopiada = signal(false);
  private temporizadorCopiado: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => {
      if (this.temporizadorCopiado) {
        clearTimeout(this.temporizadorCopiado);
      }
    });
  }

  abrir(item: MediaItem): void {
    this.item.set(item);
    this.nombre.set(item.filename);
    this.alt.set(item.alt ?? '');
    this.carpetaId.set(item.folder_id);
    this.error.set(null);
    this.urlCopiada.set(false);
    this.dialogo().abrir();
  }

  protected alCambiarCarpeta(evento: Event): void {
    this.carpetaId.set((evento.target as HTMLSelectElement).value || null);
  }

  /** Solo lectura, sin llamada al backend: formatea el tamaño en bytes que
   * ya viene en `MediaItem.size` (mismo criterio que la referencia del
   * usuario — KB por debajo de 1 MB, MB a partir de ahí). */
  protected formatearTamano(bytes: number): string {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  protected async copiarUrl(url: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(url);
      this.urlCopiada.set(true);
      if (this.temporizadorCopiado) {
        clearTimeout(this.temporizadorCopiado);
      }
      this.temporizadorCopiado = setTimeout(() => this.urlCopiada.set(false), 2000);
    } catch {
      // Sin permiso del portapapeles (contexto no seguro, navegador
      // antiguo…): no hay nada más que ofrecer, la URL sigue visible/
      // seleccionable a mano en el propio campo del formulario si hiciera
      // falta copiarla de otra forma.
    }
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

  protected async confirmarRecorte(resultado: ResultadoDeRecorte): Promise<void> {
    const actual = this.item();
    if (!actual) {
      return;
    }
    this.recortandoEnCurso.set(true);
    this.error.set(null);
    try {
      if (resultado.sobrescribir) {
        await this.sobrescribirContenido(actual, resultado.blob);
      } else {
        await this.subirComoNuevo(actual, resultado.blob);
      }
      this.recorteGuardado.emit();
      // A diferencia de guardar metadatos (que puede encadenar con el
      // recorte a continuación), aquí ya no queda nada más que hacer — sin
      // cerrar, el modal se quedaba abierto mostrando la imagen original tal
      // cual, sin ningún indicio de que el recorte se había subido de verdad
      // (hallazgo del usuario: "cuando confirmo el recorte, la imagen no
      // hace nada"). Cerrar es la confirmación visible de que ha terminado.
      this.dialogo().cerrar();
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.recortandoEnCurso.set(false);
    }
  }

  /** Trasladado tal cual desde `MediaFields.confirmarRecorte` (antes de
   * `260922-0125-prd-iconos-hover-biblioteca-medios`, fase 2) — misma lógica
   * de subida y herencia de carpeta, sin reescribir. Único cambio real: no
   * emite ningún evento de "imagen elegida" (ver JSDoc de la clase). */
  private async subirComoNuevo(actual: MediaItem, blob: Blob): Promise<void> {
    const datos = new FormData();
    datos.append('fichero', blob, this.nombreDelRecorte(actual.filename));
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
  }

  /** `PUT .../{id}/contenido`: reemplaza los píxeles del medio ya existente
   * — misma `id`/URL, sin carpeta/nombre/alt que reasignar (no cambian). */
  private async sobrescribirContenido(actual: MediaItem, blob: Blob): Promise<void> {
    const datos = new FormData();
    datos.append('fichero', blob, this.nombreDelRecorte(actual.filename));
    const actualizado = await firstValueFrom(
      this.http.put<MediaItem>(
        `${this.api.url(baseDeMedia(this.kind()))}/${actual.id}/contenido`,
        datos,
      ),
    );
    // Mismo guardado defensivo que `guardarMetadatos`: si el modal se
    // reabrió para otro item mientras este PUT seguía en vuelo, no pisa el
    // formulario ya en uso para el nuevo item.
    if (this.item()?.id === actual.id) {
      this.item.set(actualizado);
    }
  }

  /** `Media.filename` es `String(255)` (columna de BD) — sumar el sufijo
   * `-recorte.webp` (13 caracteres) a un nombre ya cercano a ese límite
   * supera la columna y el POST de «Guardar como nueva» devuelve un 500
   * genérico en vez de un error legible (hallazgo de code-review: un nombre
   * de 250 caracteres, válido de sobra al renombrar, basta para
   * reproducirlo). */
  private nombreDelRecorte(filename: string): string {
    const sufijo = '-recorte.webp';
    const base = filename.slice(0, 255 - sufijo.length);
    return `${base}${sufijo}`;
  }

  private mensajeDeError(error: unknown): string {
    return error instanceof ApiError ? error.message : this.transloco.translate('comun.error');
  }
}

