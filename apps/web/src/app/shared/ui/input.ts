import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  model,
  output,
  signal,
} from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

/**
 * Campo de formulario con etiqueta flotante animada, texto de ayuda y mensaje de
 * error.
 *
 * La etiqueta empieza dentro del campo, como un `placeholder`, y sube cuando el
 * campo tiene foco o contenido — no depende del color para comunicar el estado
 * (1.4.1): sigue enlazada por `for`/`id` en todo momento, así que un lector de
 * pantalla la anuncia igual esté arriba o dentro. El error y la ayuda comparten un
 * único `aria-describedby`: el error, cuando existe, sustituye a la ayuda en vez de
 * apilarse con ella.
 */
@Component({
  selector: 'app-input',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="campo" [class.flotando]="flotando()">
      <div class="control">
        <input
          [id]="idCampo()"
          [type]="tipoEfectivo()"
          [value]="value()"
          [attr.autocomplete]="autocomplete()"
          [attr.required]="required() ? '' : null"
          [attr.aria-invalid]="error() ? 'true' : null"
          [attr.aria-describedby]="descripcionId()"
          [class.con-boton]="esPassword()"
          (input)="alEscribir($event)"
          (focus)="enFoco.set(true)"
          (blur)="enFoco.set(false); blurred.emit()"
        />
        <label [for]="idCampo()">{{ label() }}</label>
        @if (esPassword()) {
          <button
            type="button"
            class="alternar"
            (click)="mostrar.set(!mostrar())"
            [attr.aria-label]="mostrar() ? t('comun.ocultarPassword') : t('comun.mostrarPassword')"
          >
            @if (mostrar()) {
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path
                  d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <circle cx="12" cy="12" r="3" />
              </svg>
            } @else {
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path
                  d="M3 3l18 18M10.6 10.6a3 3 0 0 0 4.24 4.24M9.4 5.5A10.9 10.9 0 0 1 12 5c6.5 0 10 7 10 7a13.6 13.6 0 0 1-3.2 4M6.6 6.6C4 8.3 2 12 2 12s3.5 7 10 7a10 10 0 0 0 3.4-.6"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            }
          </button>
        }
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
    input {
      width: 100%;
      box-sizing: border-box;
      padding: 1.25rem 0.75rem 0.4rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 3.25rem;
      transition: border-color 0.15s ease;
    }
    input:focus {
      outline: none;
      border-color: var(--color-primary);
      box-shadow: 0 0 0 1px var(--color-primary);
    }
    input.con-boton {
      padding-right: 2.75rem;
    }
    label {
      position: absolute;
      left: 0.8rem;
      top: 50%;
      transform: translateY(-50%);
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
      top: 0.6rem;
      transform: translateY(0) scale(0.78);
      color: var(--color-primary);
    }
    .alternar {
      position: absolute;
      right: 0.5rem;
      top: 50%;
      transform: translateY(-50%);
      display: grid;
      place-items: center;
      width: 2.25rem;
      height: 2.25rem;
      border: none;
      background: none;
      color: var(--color-text-muted, #6b7280);
      cursor: pointer;
      border-radius: var(--radius-md);
    }
    .alternar:hover {
      color: var(--color-text);
    }
    .alternar:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
    }
    .alternar svg {
      width: 1.25rem;
      height: 1.25rem;
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
export class Input {
  readonly label = input.required<string>();
  readonly type = input<'text' | 'email' | 'password' | 'url' | 'date'>('text');
  readonly autocomplete = input<string | null>(null);
  readonly required = input(false);
  readonly error = input<string | null>(null);
  /** Texto de ayuda bajo el campo, oculto mientras haya un error que mostrar. */
  readonly hint = input<string | null>(null);
  /** Id estable para enlazar desde fuera (p. ej. un resumen de errores). Si se omite,
   * se genera uno automático. */
  readonly fieldId = input<string | null>(null);
  readonly value = model('');
  /** Se emite al perder el foco, para validar en el momento en que tiene sentido: ni
   * en cada pulsación (interrumpiría mientras se escribe) ni solo al enviar. */
  readonly blurred = output<void>();

  private readonly transloco = inject(TranslocoService);

  private static contador = 0;
  private readonly indice = Input.contador++;
  protected readonly idCampo = computed(() => this.fieldId() ?? `campo-${this.indice}`);
  protected readonly idError = computed(() => `${this.idCampo()}-error`);
  protected readonly idAyuda = computed(() => `${this.idCampo()}-ayuda`);

  protected readonly enFoco = signal(false);
  protected readonly mostrar = signal(false);
  protected readonly esPassword = computed(() => this.type() === 'password');
  protected readonly tipoEfectivo = computed(() =>
    this.esPassword() && this.mostrar() ? 'text' : this.type(),
  );
  protected readonly flotando = computed(() => this.enFoco() || this.value().length > 0);
  protected readonly descripcionId = computed(() => {
    if (this.error()) return this.idError();
    if (this.hint()) return this.idAyuda();
    return null;
  });

  protected t(clave: string): string {
    return this.transloco.translate(clave);
  }

  protected alEscribir(evento: Event): void {
    this.value.set((evento.target as HTMLInputElement).value);
  }
}
