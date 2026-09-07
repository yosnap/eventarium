import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  model,
  output,
  signal,
} from '@angular/core';

/**
 * Campo de texto largo con la misma etiqueta flotante y ayuda que `Input`.
 *
 * Componente aparte en vez de un `type` más en `Input`: un `<textarea>` no comparte
 * elemento HTML con un `<input>`, así que reutilizar el mismo componente exigiría
 * ramificar toda la plantilla para un caso que en este panel solo usan dos campos.
 */
@Component({
  selector: 'app-textarea',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="campo" [class.flotando]="flotando()">
      <div class="control">
        <textarea
          [id]="idCampo()"
          [rows]="rows()"
          [attr.aria-invalid]="error() ? 'true' : null"
          [attr.aria-describedby]="descripcionId()"
          (input)="alEscribir($event)"
          (focus)="enFoco.set(true)"
          (blur)="enFoco.set(false); blurred.emit()"
          >{{ value() }}</textarea>
        <label [for]="idCampo()">{{ label() }}</label>
      </div>
      @if (error()) {
        <p [id]="idError()" class="error">{{ error() }}</p>
      } @else if (hint()) {
        <p [id]="idAyuda()" class="ayuda">{{ hint() }}</p>
      }
    </div>
  `,
  styles: `
    .campo {
      display: grid;
      gap: var(--space-xs);
    }
    .control {
      position: relative;
    }
    textarea {
      width: 100%;
      box-sizing: border-box;
      padding: 1.25rem 0.75rem 0.4rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      resize: vertical;
      transition: border-color 0.15s ease;
    }
    textarea:focus {
      outline: none;
      border-color: var(--color-primary);
      box-shadow: 0 0 0 1px var(--color-primary);
    }
    label {
      position: absolute;
      left: 0.8rem;
      top: 0.9rem;
      transform-origin: left top;
      font-weight: 500;
      color: var(--color-text-muted, #6b7280);
      pointer-events: none;
      transition:
        transform 0.15s ease,
        top 0.15s ease,
        color 0.15s ease;
      max-width: calc(100% - 1.6rem);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .flotando label {
      top: 0.35rem;
      transform: scale(0.78);
      color: var(--color-primary);
    }
    .error {
      margin: 0;
      color: var(--color-danger);
      font-size: 0.875rem;
    }
    .ayuda {
      margin: 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.8125rem;
    }
    @media (prefers-reduced-motion: reduce) {
      label {
        transition: none;
      }
    }
  `,
})
export class Textarea {
  readonly label = input.required<string>();
  readonly rows = input(4);
  readonly error = input<string | null>(null);
  readonly hint = input<string | null>(null);
  /** Id estable para enlazar desde fuera (p. ej. un resumen de errores). Si se omite,
   * se genera uno automático. */
  readonly fieldId = input<string | null>(null);
  readonly value = model('');
  readonly blurred = output<void>();

  private static contador = 0;
  private readonly indice = Textarea.contador++;
  protected readonly idCampo = computed(() => this.fieldId() ?? `area-${this.indice}`);
  protected readonly idError = computed(() => `${this.idCampo()}-error`);
  protected readonly idAyuda = computed(() => `${this.idCampo()}-ayuda`);

  protected readonly enFoco = signal(false);
  protected readonly flotando = computed(() => this.enFoco() || this.value().length > 0);
  protected readonly descripcionId = computed(() => {
    if (this.error()) return this.idError();
    if (this.hint()) return this.idAyuda();
    return null;
  });

  protected alEscribir(evento: Event): void {
    this.value.set((evento.target as HTMLTextAreaElement).value);
  }
}
