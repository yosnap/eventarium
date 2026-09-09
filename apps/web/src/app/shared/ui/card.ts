import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Tarjeta de contenido. Si recibe título, se expone como región etiquetada.
 *
 * Hay un único `<ng-content>` para el contenido principal: Angular proyecta el
 * contenido una sola vez, así que repetirlo en dos ramas de un `@if` deja vacía la
 * que no lo recibe. La cabecera admite además una segunda ranura opcional,
 * `[acciones]`, para botones a la derecha del título («cabecera con acciones»,
 * cubre lo que un `panel.ts` aparte solo duplicaría). Sin contenido proyectado en esa
 * ranura, la tarjeta se comporta exactamente igual que antes: cambio
 * retrocompatible.
 */
@Component({
  selector: 'app-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section [attr.aria-labelledby]="heading() ? idTitulo : null">
      @if (heading(); as titulo) {
        <div class="cabecera">
          <h2 [id]="idTitulo">{{ titulo }}</h2>
          <div class="acciones">
            <ng-content select="[acciones]" />
          </div>
        </div>
      }
      <ng-content />
    </section>
  `,
  styles: `
    section {
      background-color: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-md);
      padding: var(--space-lg);
      display: grid;
      gap: var(--space-md);
    }
    .cabecera {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
    }
    .acciones:empty {
      display: none;
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
      flex-shrink: 0;
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
