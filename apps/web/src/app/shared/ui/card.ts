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
          <h3 [id]="idTitulo">{{ titulo }}</h3>
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
      /* .card usa --r-md (eventarium.css:183), que en nuestro sistema es --radius-md
         (8px), no --radius-lg (16px). */
      border-radius: var(--radius-md);
      /* .card no lleva box-shadow en la referencia (eventarium.css:183). */
      /* .card usa padding:var(--sp-5) (eventarium.css:183/37), 24px: no hay token
         de espaciado exacto en nuestra escala (--space-md es 16px, --space-lg 32px). */
      padding: 1.5rem;
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
    /* Tamaño y tipografía vienen del h3 global (eventarium.css:120): DM Sans
       500, sin mayúsculas — un título de tarjeta no es un titular de página. */
    h3 {
      margin: 0;
    }
  `,
})
export class Card {
  readonly heading = input<string | null>(null);

  private static contador = 0;
  protected readonly idTitulo = `card-titulo-${Card.contador++}`;
}
