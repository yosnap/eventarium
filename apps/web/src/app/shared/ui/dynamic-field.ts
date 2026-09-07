import { ChangeDetectionStrategy, Component, computed, input, model, output } from '@angular/core';

import { Input } from './input';
import { Textarea } from './textarea';
import { ProfileField } from './dynamic-field.model';

/**
 * Un control por `field_type`, para pedir `profile_data` según lo que define el rol.
 *
 * El tipo decide el control (texto, área, fecha, selector, casilla…), pero la
 * etiqueta, la ayuda y el error se comunican siempre igual — quien use este
 * componente no necesita saber qué hay detrás de cada tipo.
 */
@Component({
  selector: 'app-dynamic-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Input, Textarea],
  template: `
    @switch (field().field_type) {
      @case ('textarea') {
        <app-textarea
          [fieldId]="idCampo()"
          [label]="field().label"
          [value]="valorTexto()"
          [error]="error()"
          (valueChange)="value.set($event)"
          (blurred)="blurred.emit()"
        />
      }
      @case ('select') {
        <div class="campo-select">
          <label [for]="idCampo()">{{ field().label }}</label>
          <select
            [id]="idCampo()"
            [attr.aria-describedby]="error() ? idError() : null"
            [attr.aria-invalid]="error() ? 'true' : null"
            (change)="alCambiarSeleccion($event)"
            (blur)="blurred.emit()"
          >
            <option value="" disabled [selected]="!valorTexto()">
              {{ placeholderSeleccion() }}
            </option>
            @for (opcion of opciones(); track opcion) {
              <option [value]="opcion" [selected]="opcion === valorTexto()">{{ opcion }}</option>
            }
          </select>
          @if (error()) {
            <p [id]="idError()" class="error">{{ error() }}</p>
          }
        </div>
      }
      @case ('boolean') {
        <div class="campo-boolean">
          <label [for]="idCampo()">
            <input
              [id]="idCampo()"
              type="checkbox"
              [checked]="valorBooleano()"
              (change)="alCambiarCasilla($event)"
              (blur)="blurred.emit()"
            />
            {{ field().label }}
          </label>
          @if (error()) {
            <p [id]="idError()" class="error">{{ error() }}</p>
          }
        </div>
      }
      @default {
        <app-input
          [fieldId]="idCampo()"
          [label]="field().label"
          [type]="tipoDeInput()"
          [error]="error()"
          [value]="valorTexto()"
          (valueChange)="value.set($event)"
          (blurred)="blurred.emit()"
        />
      }
    }
  `,
  styles: `
    .campo-select,
    .campo-boolean {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select {
      width: 100%;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 2.75rem;
    }
    .campo-boolean label {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-weight: 500;
      /* 44px de área táctil: WCAG 2.5.5. */
      min-height: 2.75rem;
    }
    .campo-boolean input[type='checkbox'] {
      width: 1.25rem;
      height: 1.25rem;
    }
    .error {
      margin: 0;
      color: var(--color-danger);
      font-size: 0.875rem;
    }
  `,
})
export class DynamicField {
  readonly field = input.required<ProfileField>();
  readonly value = model<string | boolean>('');
  readonly error = input<string | null>(null);
  /** Id estable para enlazar desde fuera (p. ej. un resumen de errores). Si se omite,
   * se genera uno automático. */
  readonly fieldId = input<string | null>(null);
  readonly blurred = output<void>();

  private static contador = 0;
  private readonly indice = DynamicField.contador++;
  protected readonly idCampo = computed(() => this.fieldId() ?? `dinamico-${this.indice}`);
  protected readonly idError = computed(() => `${this.idCampo()}-error`);

  protected readonly opciones = computed(() => this.field().options?.choices ?? []);

  protected readonly tipoDeInput = computed(() => {
    switch (this.field().field_type) {
      case 'email':
        return 'email';
      case 'url':
        return 'url';
      case 'date':
        return 'date';
      default:
        return 'text';
    }
  });

  protected valorTexto(): string {
    const actual = this.value();
    return typeof actual === 'string' ? actual : '';
  }

  protected valorBooleano(): boolean {
    return this.value() === true;
  }

  protected placeholderSeleccion(): string {
    return this.field().label;
  }

  protected alCambiarSeleccion(evento: Event): void {
    this.value.set((evento.target as HTMLSelectElement).value);
  }

  protected alCambiarCasilla(evento: Event): void {
    this.value.set((evento.target as HTMLInputElement).checked);
  }
}
