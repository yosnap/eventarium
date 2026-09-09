import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface ResumenDeError {
  readonly campoId: string;
  readonly mensaje: string;
}

/**
 * Resumen de errores enlazado a cada campo, para formularios con varios fallos a la
 * vez (contraseña filtrada, clave repetida, campos obligatorios…).
 *
 * Un error inline por campo basta cuando solo falla uno; con varios a la vez, quien
 * usa un lector de pantalla no tiene forma de saber cuántos hay ni dónde están sin
 * recorrer el formulario entero primero. Por eso solo aparece a partir de dos errores
 * — con uno, el error inline ya es suficiente y duplicarlo aquí sería ruido.
 */
@Component({
  selector: 'app-error-summary',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (errores().length > 1) {
      <div class="resumen" role="alert">
        <p>{{ titulo() }}</p>
        <ul>
          @for (error of errores(); track error.campoId) {
            <li>
              <a [href]="'#' + error.campoId">{{ error.mensaje }}</a>
            </li>
          }
        </ul>
      </div>
    }
  `,
  styles: `
    .resumen {
      padding: var(--space-md);
      border: 1px solid var(--danger);
      border-radius: var(--radius-md);
      background-color: var(--danger-dim);
      color: var(--fg);
    }
    .resumen p {
      margin: 0 0 var(--space-xs);
      font-weight: 600;
    }
    .resumen ul {
      margin: 0;
      padding-left: 1.25rem;
    }
    .resumen a {
      color: inherit;
    }
  `,
})
export class ErrorSummary {
  readonly errores = input.required<readonly ResumenDeError[]>();
  readonly titulo = input('Corrige los siguientes errores:');
}
