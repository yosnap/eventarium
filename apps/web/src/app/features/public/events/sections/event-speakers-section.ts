import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { rolLegible } from '../event-page.types';

export interface Speaker {
  readonly publicSlug: string;
  readonly displayName: string;
  readonly roleKey: string;
}

/**
 * Rejilla de ponentes, sobre `.speaker`/`.speaker__mark` de la referencia
 * (`evento-iawic.html:196-232`). La caja de iniciales es un patrón propio (dos
 * iniciales, 52×52px) y no `app-brand-mark`: ese componente es la marca de
 * 26×26px con una sola inicial junto al nombre de la organización
 * (`shared/ui/brand-mark.ts`), un contexto visual distinto al de una ficha de
 * ponente.
 *
 * Extraído de `event-page.ts` para no pasar de las ~700-800 líneas
 * recomendadas en un solo fichero.
 */
@Component({
  selector: 'app-event-speakers-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <div class="rejilla">
        @for (ponente of ponentes(); track ponente.publicSlug) {
          <a class="ponente" [routerLink]="['/ponentes', ponente.publicSlug]">
            <span class="marca" aria-hidden="true">{{ iniciales(ponente.displayName) }}</span>
            <span class="datos">
              <strong>{{ ponente.displayName }}</strong>
              <span class="rol">{{ rolLegible(ponente.roleKey, t) }}</span>
            </span>
          </a>
        }
      </div>
    </ng-container>
  `,
  styles: `
    .rejilla {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(16.25rem, 1fr));
      gap: var(--sp-4);
    }
    .ponente {
      display: flex;
      gap: var(--sp-4);
      align-items: flex-start;
      padding: var(--sp-4);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      text-decoration: none;
      color: inherit;
      transition:
        border-color 0.15s,
        background-color 0.15s;
    }
    .ponente:hover {
      border-color: var(--faint);
      background-color: var(--surface-hi);
    }
    .marca {
      flex: 0 0 auto;
      width: 3.25rem;
      height: 3.25rem;
      display: grid;
      place-items: center;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      font-family: var(--font-display);
      font-size: 1.4rem;
      letter-spacing: 0.04em;
      color: var(--muted);
      padding-top: 3px;
    }
    .datos {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .rol {
      font-size: var(--fs-sm);
      color: var(--muted);
    }
  `,
})
export class EventSpeakersSection {
  readonly ponentes = input.required<readonly Speaker[]>();

  protected rolLegible(roleKey: string, traducir: (clave: string) => string): string {
    return rolLegible(roleKey, traducir);
  }

  protected iniciales(nombre: string): string {
    const partes = nombre.trim().split(/\s+/).filter(Boolean);
    const primeras = partes.slice(0, 2).map((parte) => parte.charAt(0).toUpperCase());
    return primeras.join('') || '?';
  }
}
