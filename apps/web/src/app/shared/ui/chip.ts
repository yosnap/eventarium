import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type ChipTone = 'neutro' | 'ok' | 'espera' | 'apagado';

/**
 * Chip de estado: etiqueta corta con refuerzo visual de color.
 *
 * No es interactivo: es un `<span>`, no un `<button>`. Un chip que parece pulsable y
 * no lo es cuesta más de lo que ahorra.
 *
 * El estado se lee siempre por el texto que contiene (WCAG 1.4.1): el color del tono
 * es refuerzo, nunca el único medio, así que el texto siempre va en color neutro de
 * alto contraste y el tono solo tiñe el fondo y el borde.
 */
@Component({
  selector: 'app-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span [class]="'chip ' + tone()">
      <ng-content />
    </span>
  `,
  styles: `
    .chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      padding: 0.25rem 0.625rem;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      font-size: 0.8125rem;
      font-weight: 600;
      line-height: 1.4;
      color: var(--fg);
      white-space: nowrap;
    }
    .neutro {
      background-color: var(--surface-hi);
      border-color: var(--border);
    }
    .ok {
      background-color: var(--accent-dim);
      border-color: var(--accent);
    }
    .espera {
      background-color: var(--warn-dim);
      border-color: var(--warn);
    }
    .apagado {
      background-color: var(--danger-dim);
      border-color: var(--danger);
    }
  `,
})
export class Chip {
  readonly tone = input<ChipTone>('neutro');
}
