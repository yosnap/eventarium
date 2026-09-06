import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Tarjeta de contenido. Si recibe título, se expone como región etiquetada.
 *
 * Hay un único `<ng-content>`: Angular proyecta el contenido una sola vez, así que
 * repetirlo en dos ramas de un `@if` deja vacía la que no lo recibe.
 */
@Component({
  selector: 'app-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section [attr.aria-labelledby]="heading() ? idTitulo : null">
      @if (heading(); as titulo) {
        <h2 [id]="idTitulo">{{ titulo }}</h2>
      }
      <ng-content />
    </section>
  `,
  styles: `
    section {
      background-color: var(--color-surface);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-card);
      padding: var(--space-lg);
      display: grid;
      gap: var(--space-md);
    }
    h2 {
      margin: 0;
      font-size: 1.125rem;
    }
  `,
})
export class Card {
  readonly heading = input<string | null>(null);

  private static contador = 0;
  protected readonly idTitulo = `card-titulo-${Card.contador++}`;
}
