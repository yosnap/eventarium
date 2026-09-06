import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

/**
 * Campo de formulario con etiqueta y mensaje de error asociados.
 *
 * La etiqueta se enlaza con `for`/`id` y el error con `aria-describedby`: sin eso, un
 * lector de pantalla anuncia el campo sin decir qué se pide ni qué ha fallado.
 */
@Component({
  selector: 'app-input',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="campo">
      <label [for]="idCampo">{{ label() }}</label>
      <input
        [id]="idCampo"
        [type]="type()"
        [value]="value()"
        [attr.autocomplete]="autocomplete()"
        [attr.required]="required() ? '' : null"
        [attr.aria-invalid]="error() ? 'true' : null"
        [attr.aria-describedby]="error() ? idError : null"
        (input)="alEscribir($event)"
      />
      @if (error()) {
        <p [id]="idError" class="error">{{ error() }}</p>
      }
    </div>
  `,
  styles: `
    .campo {
      display: grid;
      gap: var(--space-xs);
    }
    label {
      font-weight: 600;
    }
    input {
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 2.75rem;
    }
    .error {
      margin: 0;
      color: var(--color-danger);
      font-size: 0.875rem;
    }
  `,
})
export class Input {
  readonly label = input.required<string>();
  readonly type = input<'text' | 'email' | 'password'>('text');
  readonly autocomplete = input<string | null>(null);
  readonly required = input(false);
  readonly error = input<string | null>(null);
  readonly value = model('');

  private static contador = 0;
  private readonly indice = Input.contador++;
  protected readonly idCampo = `campo-${this.indice}`;
  protected readonly idError = `campo-${this.indice}-error`;

  protected alEscribir(evento: Event): void {
    this.value.set((evento.target as HTMLInputElement).value);
  }
}
