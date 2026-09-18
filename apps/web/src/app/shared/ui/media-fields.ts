import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from './button';
import { Input } from './input';

/**
 * Contenido de selección de medios: pestañas Subir (dropzone + selector de
 * fichero), URL (importar por dirección) y Biblioteca (rejilla de imágenes
 * existentes que quien llama facilite).
 *
 * Sin envoltorio de modal a propósito: `MediaDialog` lo mete dentro de
 * `app-dialog` para el caso "cambiar" (ya hay imagen, no se quiere ocupar el
 * espacio del campo con el dropzone entero); `MediaPicker` lo usa directo,
 * sin modal, mientras el campo no tenga imagen — abrir un diálogo para el
 * primer paso es fricción de más cuando no hay nada que tapar.
 */
@Component({
  selector: 'app-media-fields',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, Input],
  template: `
    <ng-container *transloco="let t">
      <div class="pestanas" role="tablist">
        @for (tab of pestanasDisponibles; track tab.valor) {
          <button
            type="button"
            role="tab"
            [class.pestana-activa]="pestana() === tab.valor"
            [attr.aria-selected]="pestana() === tab.valor"
            (click)="pestana.set(tab.valor)"
          >
            {{ t(tab.etiqueta) }}
          </button>
        }
      </div>

      @switch (pestana()) {
        @case ('subir') {
          <label
            class="dropzone"
            [class.encima]="arrastrando()"
            (dragover)="alArrastrarEncima($event)"
            (dragleave)="arrastrando.set(false)"
            (drop)="alSoltar($event)"
          >
            <input
              type="file"
              class="fichero-oculto"
              [accept]="aceptados()"
              (change)="alElegirFichero($event)"
            />
            <span>{{ t('ui.media.sueltaAqui') }}</span>
            <small>{{ t('ui.media.oPulsaParaElegir') }}</small>
          </label>
        }
        @case ('url') {
          <app-input
            fieldId="media-url"
            [label]="t('ui.media.urlEtiqueta')"
            [value]="urlEscrita()"
            (valueChange)="urlEscrita.set($event)"
          />
          <app-button
            type="button"
            variant="secundario"
            [disabled]="!urlEscrita().trim()"
            (pulsado)="elegirUrl()"
          >
            {{ t('ui.media.usarUrl') }}
          </app-button>
        }
        @case ('biblioteca') {
          @if (biblioteca().length === 0) {
            <p class="vacio">{{ t('ui.media.bibliotecaVacia') }}</p>
          } @else {
            <div class="rejilla" role="listbox" [attr.aria-label]="tituloBiblioteca()">
              @for (item of biblioteca(); track item.url) {
                <button
                  type="button"
                  role="option"
                  class="item"
                  [attr.aria-selected]="urlEscrita() === item.url"
                  (click)="elegirBiblioteca(item.url)"
                >
                  <img [src]="item.url" [alt]="item.etiqueta" loading="lazy" />
                </button>
              }
            </div>
          }
        }
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .pestanas {
      display: flex;
      gap: var(--sp-1);
      border-bottom: 1px solid var(--border);
      margin-bottom: var(--sp-4);
    }
    [role='tab'] {
      padding: var(--sp-2) var(--sp-3);
      border: none;
      background: none;
      color: var(--muted);
      font: inherit;
      font-size: var(--fs-sm);
      cursor: pointer;
      border-bottom: 2px solid transparent;
    }
    .pestana-activa {
      color: var(--fg);
      border-bottom-color: var(--accent);
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
    .fichero-oculto {
      display: none;
    }
    .vacio {
      color: var(--muted);
      margin: 0;
    }
    .rejilla {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(6rem, 1fr));
      gap: var(--sp-2);
      max-height: 16rem;
      overflow: auto;
    }
    .item {
      padding: 0;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: none;
      cursor: pointer;
      overflow: hidden;
      aspect-ratio: 1;
    }
    .item img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    app-button {
      margin-top: var(--space-sm);
    }
  `,
})
export class MediaFields {
  /** Tipos aceptados por el selector de fichero (igual que `accept`). */
  readonly aceptados = input.required<string>();
  /** Imágenes existentes para la pestaña Biblioteca (opcional). */
  readonly biblioteca = input<readonly { url: string; etiqueta: string }[]>([]);
  /** Etiqueta accesible de la rejilla de biblioteca (título del campo/diálogo). */
  readonly tituloBiblioteca = input('');

  /** El `File` elegido en la pestaña Subir. */
  readonly ficheroElegido = output<File>();
  /** La URL escrita o elegida de la biblioteca. */
  readonly urlElegida = output<string>();

  protected readonly pestana = signal<'subir' | 'url' | 'biblioteca'>('subir');
  protected readonly arrastrando = signal(false);
  protected readonly urlEscrita = signal('');

  protected readonly pestanasDisponibles = [
    { valor: 'subir' as const, etiqueta: 'ui.media.pestanaSubir' },
    { valor: 'url' as const, etiqueta: 'ui.media.pestanaUrl' },
    { valor: 'biblioteca' as const, etiqueta: 'ui.media.pestanaBiblioteca' },
  ];

  /** Reinicia a la pestaña Subir y limpia la URL escrita — quien envuelve
   * este componente en un diálogo lo llama al reabrirlo, para no arrastrar
   * el estado de la vez anterior. */
  reiniciar(): void {
    this.pestana.set('subir');
    this.urlEscrita.set('');
  }

  protected alArrastrarEncima(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(true);
  }

  protected alElegirFichero(evento: Event): void {
    const fichero = (evento.target as HTMLInputElement).files?.[0];
    if (fichero) {
      this.ficheroElegido.emit(fichero);
    }
  }

  protected alSoltar(evento: DragEvent): void {
    evento.preventDefault();
    this.arrastrando.set(false);
    const fichero = evento.dataTransfer?.files?.[0];
    if (fichero) {
      this.ficheroElegido.emit(fichero);
    }
  }

  protected elegirUrl(): void {
    const url = this.urlEscrita().trim();
    if (url) {
      this.urlElegida.emit(url);
    }
  }

  protected elegirBiblioteca(url: string): void {
    this.urlElegida.emit(url);
  }
}
