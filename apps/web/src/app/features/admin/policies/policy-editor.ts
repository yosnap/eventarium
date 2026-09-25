import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { MarkdownSeguro } from '../../../shared/legal/markdown-seguro';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Textarea } from '../../../shared/ui/textarea';
import { LIMITE_CARACTERES } from './policies-types';

let contadorDeEditores = 0;

/**
 * Editor de un texto de política: Markdown con vista previa saneada (la misma
 * que verá quien se inscribe). En pantallas anchas, texto y vista previa van en
 * dos columnas; en estrechas, en pestañas «Escribir» / «Vista previa».
 *
 * No habla con la API: emite el texto al guardar y quien lo usa decide si es
 * de la organización o de un evento.
 */
@Component({
  selector: 'app-policy-editor',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, MarkdownSeguro, Alert, Button, Textarea],
  template: `
    <ng-container *transloco="let t">
      <div class="pestanas" role="tablist" [attr.aria-label]="etiqueta()">
        <button
          type="button"
          role="tab"
          [id]="id + '-tab-escribir'"
          [attr.aria-controls]="id + '-escribir'"
          [attr.aria-selected]="pestana() === 'escribir'"
          (click)="pestana.set('escribir')"
        >
          {{ t('admin.politicas.escribir') }}
        </button>
        <button
          type="button"
          role="tab"
          [id]="id + '-tab-vista'"
          [attr.aria-controls]="id + '-vista'"
          [attr.aria-selected]="pestana() === 'vista'"
          (click)="pestana.set('vista')"
        >
          {{ t('admin.politicas.vistaPrevia') }}
        </button>
      </div>

      <div class="columnas" [class.muestra-vista]="pestana() === 'vista'">
        <div
          class="escribir"
          role="tabpanel"
          [id]="id + '-escribir'"
          [attr.aria-labelledby]="id + '-tab-escribir'"
        >
          <app-textarea
            [label]="etiqueta()"
            [rows]="14"
            [hint]="t('admin.politicas.ayudaMarkdown')"
            [error]="demasiadoLargo() ? t('admin.politicas.demasiadoLargo') : null"
            [(value)]="texto"
          />
          <p class="contador" [class.excedido]="demasiadoLargo()">
            {{ t('admin.politicas.contador', { usados: texto().length, limite: limite }) }}
          </p>
        </div>
        <div
          class="vista"
          role="tabpanel"
          [id]="id + '-vista'"
          [attr.aria-labelledby]="id + '-tab-vista'"
        >
          @if (texto().trim()) {
            <app-markdown-seguro [texto]="texto()" />
          } @else {
            <p class="vacio">{{ t('admin.politicas.vistaVacia') }}</p>
          }
        </div>
      </div>

      @if (afectaAEventoPublicado()) {
        <app-alert tone="info">{{ t('admin.politicas.avisoEventoPublicado') }}</app-alert>
      }
      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }
      <div class="acciones">
        <app-button
          [loading]="guardando()"
          [disabled]="!sePuedeGuardar()"
          (pulsado)="guardar.emit(texto())"
        >
          {{ guardando() ? t('admin.politicas.guardando') : t('comun.guardar') }}
        </app-button>
        <ng-content select="[acciones]" />
      </div>
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-md);
    }
    .pestanas {
      display: none;
      gap: var(--space-xs);
    }
    .pestanas button {
      font: inherit;
      padding: var(--space-xs) var(--space-md);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: var(--bg);
      color: var(--fg);
      cursor: pointer;
    }
    .pestanas button[aria-selected='true'] {
      background: var(--surface-hi);
      font-weight: 600;
    }
    .columnas {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-lg);
      align-items: start;
    }
    .vista {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: var(--space-md);
      min-height: 10rem;
      overflow-wrap: anywhere;
    }
    .contador {
      margin: var(--space-xs) 0 0;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .contador.excedido {
      color: var(--danger);
    }
    .vacio {
      color: var(--muted);
      margin: 0;
    }
    .acciones {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    @media (max-width: 48rem) {
      .pestanas {
        display: flex;
      }
      .columnas {
        grid-template-columns: minmax(0, 1fr);
      }
      .columnas:not(.muestra-vista) .vista,
      .columnas.muestra-vista .escribir {
        display: none;
      }
    }
  `,
})
export class PolicyEditor {
  /** Nombre visible del documento (etiqueta del campo). */
  readonly etiqueta = input.required<string>();
  /** Texto guardado; se copia al editor cada vez que cambia. */
  readonly valor = input('');
  readonly guardando = input(false);
  readonly error = input<string | null>(null);
  /** Guardar pedirá volver a aceptar a quien se esté inscribiendo ahora. */
  readonly afectaAEventoPublicado = input(false);

  readonly guardar = output<string>();

  protected readonly limite = LIMITE_CARACTERES;
  /** Prefijo único para enlazar pestañas y paneles. */
  protected readonly id = `editor-politica-${++contadorDeEditores}`;
  protected readonly texto = signal('');
  protected readonly pestana = signal<'escribir' | 'vista'>('escribir');

  protected readonly demasiadoLargo = computed(() => this.texto().length > LIMITE_CARACTERES);
  protected readonly sePuedeGuardar = computed(
    () =>
      !this.guardando() &&
      !this.demasiadoLargo() &&
      this.texto().trim().length > 0 &&
      this.texto() !== this.valor(),
  );

  /** Último valor guardado que se copió al editor. */
  private valorCopiado = '';

  constructor() {
    // Copia el texto guardado al editor, salvo que la persona ya haya escrito
    // algo distinto: si otra persona guarda a la vez (409 y recarga), el
    // borrador no se pierde.
    effect(() => {
      const valor = this.valor();
      const borrador = untracked(this.texto);
      if (borrador === this.valorCopiado) {
        this.texto.set(valor);
      }
      this.valorCopiado = valor;
    });
  }
}
