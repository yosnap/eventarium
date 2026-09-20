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
    /* .chip (eventarium.css:192-199) es mono, en mayúsculas y con tracking amplio:
       nada que ver con un chip sans de peso 600 en minúsculas. */
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      /* padding:3px 9px (eventarium.css:193). */
      padding: 3px 9px;
      /* border-radius:3px literal (eventarium.css:193): no es --r-sm (4px), es su
         propio valor, así que se deja como número. */
      border-radius: 3px;
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.1em;
      text-transform: uppercase;
      border: 1px solid var(--border-strong);
      font-weight: 400;
      line-height: 1.4;
      color: var(--muted);
      white-space: nowrap;
    }
    .neutro {
      background-color: transparent;
      border-color: var(--border-strong);
      color: var(--muted);
    }
    /* Los tonos con color usan el -dim del tono como fondo y un borde al tono base
       con alfa .45-.5 (eventarium.css:197-199), nunca un background-color sólido.
       El color y el fondo ya usaban el token de plantilla (--accent/--warn/
       --danger), pero el borde estaba en un oklch() literal copiado del tema
       oscuro del prototipo: una organización con otra plantilla (otro acento) veía
       el chip con el acento correcto pero el borde siempre verde. color-mix() con
       el propio token reproduce la alfa de la referencia sin fijar el tono. */
    .ok {
      color: var(--accent);
      border-color: color-mix(in oklch, var(--accent), transparent 55%);
      background: var(--accent-dim);
    }
    .espera {
      color: var(--warn);
      border-color: color-mix(in oklch, var(--warn), transparent 50%);
      background: var(--warn-dim);
    }
    .apagado {
      color: var(--danger);
      border-color: color-mix(in oklch, var(--danger), transparent 50%);
      background: var(--danger-dim);
    }
  `,
})
export class Chip {
  readonly tone = input<ChipTone>('neutro');
}
