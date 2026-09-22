import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import type { ReceiptDraft } from './accounting-types';

/** Espejo de `ALLOWED_DOCUMENT_MIMES` del backend. */
export const MIMES_DE_JUSTIFICANTE = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'application/pdf',
] as const;

/** Espejo de `max_document_bytes` (10 MB por defecto). */
export const MAXIMO_BYTES_DE_JUSTIFICANTE = 10 * 1024 * 1024;

/**
 * Subida de un justificante de gasto.
 *
 * Zona de arrastrar y soltar (mismo patrón que el dropzone de
 * `media-fields.ts`: `<label>` que envuelve un `<input type="file">` oculto,
 * `dragover`/`dragleave`/`drop`), sin biblioteca ni recorte — un justificante
 * es de un solo uso, no una imagen reutilizable, así que no hace falta nada
 * de eso. Antes era un `<input type="file">` nativo suelto, poco visible y
 * sin ninguna pista de dónde pulsar (hallazgo del usuario).
 *
 * El resto sigue el patrón de subida que ya usa `media-fields.ts` (`FormData`,
 * `firstValueFrom(http.post(...))`, señal `subiendo`, mensaje de error en el
 * `catch`) y, como allí, **sin barra de progreso**: `reportProgress` obligaría
 * a salirse del patrón del proyecto para un fichero de 10 MB como mucho. El
 * "estamos leyéndolo" que sigue a la subida lo pinta la bandeja
 * (`receipt-drafts-panel.ts`), que hace el *polling* de verdad.
 *
 * Las comprobaciones de tipo y tamaño de aquí son **cortesía, no barrera**: el
 * backend valida los bytes reales (no la extensión) y su 422 se muestra tal
 * cual aunque esta validación no lo hubiera bloqueado.
 */
@Component({
  selector: 'app-receipt-upload',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert],
  template: `
    <ng-container *transloco="let t">
      <div class="campo">
        <span class="etiqueta" [id]="idEtiqueta">{{
          t('admin.events.accounting.justificantes.subida.etiqueta')
        }}</span>
        <label
          class="dropzone"
          [class.encima]="arrastrando()"
          [class.deshabilitado]="subiendo()"
          [attr.aria-labelledby]="idEtiqueta"
          [attr.aria-describedby]="idAyuda"
          (dragover)="alArrastrarEncima($event)"
          (dragleave)="arrastrando.set(false)"
          (drop)="alSoltar($event)"
        >
          <input
            #entrada
            [id]="idCampo"
            type="file"
            class="fichero-oculto"
            [accept]="accept"
            [disabled]="subiendo()"
            (change)="alElegirFichero($event)"
          />
          @if (subiendo()) {
            <span role="status" aria-live="polite">{{
              t('admin.events.accounting.justificantes.subida.subiendo')
            }}</span>
          } @else {
            <span>{{ t('admin.events.accounting.justificantes.subida.arrastraAqui') }}</span>
            <small>{{ t('admin.events.accounting.justificantes.subida.oPulsaParaElegir') }}</small>
          }
        </label>
        <p class="ayuda" [id]="idAyuda">
          {{ t('admin.events.accounting.justificantes.subida.ayuda') }}
        </p>
      </div>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-sm);
    }
    .campo {
      display: grid;
      gap: var(--space-xs);
    }
    .etiqueta {
      font-weight: 600;
    }
    .dropzone {
      display: grid;
      place-items: center;
      gap: var(--space-xs);
      min-height: 8rem;
      padding: var(--sp-4);
      border: 2px dashed var(--border-strong);
      border-radius: var(--radius-md);
      cursor: pointer;
      text-align: center;
      color: var(--muted);
    }
    .dropzone.encima {
      border-color: var(--accent);
      color: var(--fg);
    }
    .dropzone.deshabilitado {
      cursor: wait;
      opacity: 0.7;
    }
    .fichero-oculto {
      display: none;
    }
    .ayuda {
      margin: 0;
      color: var(--muted);
      font-size: 0.8125rem;
    }
  `,
})
export class ReceiptUpload {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  /** El evento al que se imputará el gasto que salga de este justificante. */
  readonly eventId = input.required<string>();

  /** Avisa con el borrador recién creado, para que la bandeja lo recoja. */
  readonly subido = output<ReceiptDraft>();

  protected readonly subiendo = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly arrastrando = signal(false);

  protected readonly accept = MIMES_DE_JUSTIFICANTE.join(',');

  private static contador = 0;
  private readonly indice = ReceiptUpload.contador++;
  protected readonly idCampo = `justificante-fichero-${this.indice}`;
  protected readonly idEtiqueta = `${this.idCampo}-etiqueta`;
  protected readonly idAyuda = `${this.idCampo}-ayuda`;

  private readonly entrada = viewChild.required<ElementRef<HTMLInputElement>>('entrada');

  protected alArrastrarEncima(evento: DragEvent): void {
    evento.preventDefault();
    if (!this.subiendo()) {
      this.arrastrando.set(true);
    }
  }

  protected alElegirFichero(evento: Event): void {
    const fichero = (evento.target as HTMLInputElement).files?.[0];
    if (fichero) {
      void this.subirFichero(fichero);
    }
  }

  protected alSoltar(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(false);
    if (this.subiendo()) {
      return;
    }
    const fichero = evento.dataTransfer?.files?.[0];
    if (fichero) {
      void this.subirFichero(fichero);
    }
  }

  private async subirFichero(fichero: File): Promise<void> {
    this.error.set(null);

    const clave = this.motivoDeRechazo(fichero);
    if (clave !== null) {
      this.error.set(this.transloco.translate(clave));
      this.limpiarEntrada();
      return;
    }

    this.subiendo.set(true);
    try {
      const datos = new FormData();
      datos.append('fichero', fichero);
      const borrador = await firstValueFrom(
        this.http.post<ReceiptDraft>(
          this.api.url(`/accounting/events/${this.eventId()}/expense-drafts`),
          datos,
        ),
      );
      this.limpiarEntrada();
      this.subido.emit(borrador);
    } catch (error) {
      // El 422 del backend (bytes reales distintos de la extensión, tamaño
      // real) se muestra tal cual: manda el servidor, no la comprobación de
      // cortesía de arriba.
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.accounting.error'),
      );
    } finally {
      this.subiendo.set(false);
    }
  }

  /** Clave de traducción del rechazo de cortesía, o `null` si pasa. */
  private motivoDeRechazo(fichero: File): string | null {
    const permitido = (MIMES_DE_JUSTIFICANTE as readonly string[]).includes(fichero.type);
    if (!permitido) {
      return 'admin.events.accounting.justificantes.subida.tipoNoPermitido';
    }
    if (fichero.size > MAXIMO_BYTES_DE_JUSTIFICANTE) {
      return 'admin.events.accounting.justificantes.subida.demasiadoGrande';
    }
    return null;
  }

  /** Sin esto, volver a elegir el mismo fichero no dispara `change`. */
  private limpiarEntrada(): void {
    this.entrada().nativeElement.value = '';
  }
}
