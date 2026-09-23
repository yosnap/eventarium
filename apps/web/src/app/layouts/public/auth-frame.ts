import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { BrandLockup } from '../../shared/ui/brand-lockup';
import { ThemeToggle } from '../../shared/ui/theme-toggle';

/**
 * Marco mínimo para las 10 pantallas públicas que no viven dentro de
 * `PublicShell` (registro, verificación de correo, recuperación de contraseña,
 * confirmaciones por enlace de correo, entrada…): misma marca y conmutador de
 * tema que el chrome principal, sin la navegación completa ni el pie extenso,
 * que no tienen sentido en una pantalla de un solo paso.
 *
 * Un solo `<main id="contenido" tabindex="-1">`: la pantalla que lo usa no
 * pinta el suyo, para no anidar dos landmarks `main`.
 *
 * `titulo` pinta un `<h1>` visualmente oculto: sin él, ninguna de estas 10
 * pantallas tenía un `<h1>` real — solo el `<h2>`/`<h3>` del título de
 * `app-card`, que sí se ve pero no sustituye al `<h1>` de página (WCAG 2.4.6 /
 * estructura de encabezados). Oculto porque el título visible ya lo da la
 * tarjeta con el mismo texto; duplicarlo en pantalla sería ruido.
 */
@Component({
  selector: 'app-auth-frame',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TranslocoDirective, ThemeToggle, BrandLockup],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <div class="ancho-maximo header-en">
          <a routerLink="/" class="marca">
            <app-brand-lockup />
          </a>
          <app-theme-toggle />
        </div>
      </header>

      <main id="contenido" tabindex="-1">
        @if (titulo(); as texto) {
          <h1 class="oculto-visual">{{ texto }}</h1>
        }
        <ng-content />
      </main>

      <footer [attr.aria-label]="t('publico.enlacesLegales')">
        <nav [attr.aria-label]="t('publico.enlacesLegales')">
          <ul>
            <li>
              <a routerLink="/legal/aviso-legal">{{ t('legal.avisoLegal') }}</a>
            </li>
            <li>
              <a routerLink="/legal/privacidad">{{ t('legal.privacidad') }}</a>
            </li>
            <li>
              <a routerLink="/legal/cookies">{{ t('legal.cookies') }}</a>
            </li>
          </ul>
        </nav>
      </footer>
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 100vh;
    }
    /* A sangre completa como en PublicShell y AdminShell; el contenido interno
       (.header-en) es quien se centra al ancho máximo. */
    header {
      background: var(--nav-bg);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }
    .header-en {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      padding: var(--space-md) var(--space-lg);
      min-height: 64px;
    }
    .marca {
      display: inline-flex;
      text-decoration: none;
      color: inherit;
    }
    main {
      display: grid;
      align-content: center;
      justify-content: center;
      padding: var(--space-lg);
    }
    .oculto-visual {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }
    footer {
      padding: var(--space-md) var(--space-lg) var(--space-lg);
      border-top: 1px solid var(--border);
      display: grid;
    }
    footer ul {
      display: flex;
      justify-content: center;
      gap: var(--space-md);
      list-style: none;
      margin: 0;
      padding: 0;
    }
    footer a {
      color: var(--muted);
      text-decoration: none;
      font-size: var(--fs-sm);
    }
    footer a:hover,
    footer a:focus-visible {
      color: var(--fg);
    }
  `,
})
export class AuthFrame {
  readonly titulo = input<string | null>(null);
}
