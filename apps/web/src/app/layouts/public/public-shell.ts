import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { ThemingService } from '../../core/theming/theming.service';

/**
 * Estructura de la web pública: cabecera con la marca de la organización, contenido y
 * pie. Los `landmark` (`header`, `nav`, `main`, `footer`) permiten navegar por regiones
 * con un lector de pantalla.
 */
@Component({
  selector: 'app-public-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <a routerLink="/" class="marca">
          @if (theming.branding()?.logo_url; as logo) {
            <img [src]="logo" [alt]="theming.organizationName()" height="40" />
          } @else {
            <span class="nombre">{{ theming.organizationName() }}</span>
          }
        </a>
        <nav [attr.aria-label]="t('publico.navegacion')">
          <a routerLink="/">{{ t('publico.inicio') }}</a>
          <a routerLink="/eventos">{{ t('publico.eventos.listadoTitulo') }}</a>
          <a routerLink="/admin">{{ t('publico.accesoPanel') }}</a>
        </nav>
      </header>

      <main id="contenido" tabindex="-1">
        <router-outlet />
      </main>

      <footer [attr.aria-label]="t('publico.piePagina')">
        <p>{{ t('publico.organizadoPor', { nombre: theming.organizationName() }) }}</p>
        @if (theming.branding()?.social_links?.length) {
          <nav [attr.aria-label]="t('publico.redesSociales')">
            <ul>
              @for (enlace of theming.branding()!.social_links; track enlace.url) {
                <li>
                  <a [href]="enlace.url" rel="noopener noreferrer" target="_blank">
                    {{ enlace.kind }}
                  </a>
                </li>
              }
            </ul>
          </nav>
        }
      </footer>
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 100vh;
    }
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      padding: var(--space-md) var(--space-lg);
      border-bottom: 1px solid var(--color-border);
    }
    .marca {
      display: inline-flex;
      align-items: center;
      text-decoration: none;
      color: inherit;
    }
    .nombre {
      font-family: var(--font-heading);
      font-size: 1.25rem;
      font-weight: 700;
    }
    nav {
      display: flex;
      gap: var(--space-md);
    }
    nav a {
      color: var(--color-primary);
    }
    main {
      padding: var(--space-lg);
    }
    footer {
      padding: var(--space-lg);
      background-color: var(--color-surface-muted);
      color: var(--color-text-muted);
      display: grid;
      gap: var(--space-sm);
    }
    footer ul {
      display: flex;
      gap: var(--space-md);
      list-style: none;
      margin: 0;
      padding: 0;
    }
  `,
})
export class PublicShell {
  protected readonly theming = inject(ThemingService);
}
