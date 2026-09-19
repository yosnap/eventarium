import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * Caja de marca de 26×26px con la inicial del nombre, sobre `.brand__mark`
 * (`eventarium.css:143-147`): borde de 1.5px en `--accent`, letra en
 * `--font-display`. Solo se pinta cuando no hay logotipo real subido — es el
 * mismo patrón que la referencia usa junto al nombre textual, no un sustituto
 * del logotipo de la organización.
 */
@Component({
  selector: 'app-brand-mark',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="marca-caja" aria-hidden="true">{{ inicial() }}</span>`,
  styles: `
    .marca-caja {
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      flex: 0 0 auto;
      border: 1.5px solid var(--accent);
      border-radius: 3px;
      font-family: var(--font-display);
      font-size: 17px;
      line-height: 1;
      color: var(--accent);
      padding-top: 2px;
    }
  `,
})
export class BrandMark {
  readonly nombre = input.required<string>();

  protected readonly inicial = computed(() => this.nombre().trim().charAt(0).toUpperCase() || '?');
}
