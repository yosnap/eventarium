import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

export interface BreadcrumbItem {
  readonly label: string;
  /** Ausente en el último elemento: esa es la página actual, se pinta como
   * texto plano, no como enlace a sí misma. */
  readonly routerLink?: readonly (string | number)[];
  readonly fragment?: string;
}

/**
 * Ruta de navegación (`.crumb` de `ficha-sesion.html:92-96`): enlaces
 * separados por «·», con el último elemento siempre como texto plano (la
 * página en la que ya está la persona). `items` decide toda la jerarquía —
 * este componente no conoce rutas de ningún dominio concreto.
 */
@Component({
  selector: 'app-breadcrumb',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <nav class="crumb" [attr.aria-label]="ariaLabel()">
      @for (item of items(); track $index) {
        @if ($last) {
          <span aria-current="page">{{ item.label }}</span>
        } @else {
          <a [routerLink]="item.routerLink" [fragment]="item.fragment">{{ item.label }}</a>
          <span aria-hidden="true">·</span>
        }
      }
    </nav>
  `,
  styles: `
    .crumb {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-2);
      align-items: baseline;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .crumb a {
      color: var(--muted);
      text-decoration: underline;
    }
    .crumb a:hover {
      color: var(--accent);
    }
  `,
})
export class Breadcrumb {
  readonly items = input.required<readonly BreadcrumbItem[]>();
  readonly ariaLabel = input.required<string>();
}
