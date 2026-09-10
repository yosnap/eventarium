import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { CookieBanner } from '../../shared/cookies/cookie-banner';
import { CookieConsentService } from '../../core/cookies/cookie-consent.service';
import { ThemingService } from '../../core/theming/theming.service';
import { ThemeToggle } from '../../shared/ui/theme-toggle';

/**
 * Estructura de la web pública: cabecera con la marca de la organización, contenido y
 * pie. Los `landmark` (`header`, `nav`, `main`, `footer`) permiten navegar por regiones
 * con un lector de pantalla.
 */
@Component({
  selector: 'app-public-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, TranslocoDirective, CookieBanner, ThemeToggle],
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
        <app-theme-toggle />
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
        <nav [attr.aria-label]="t('publico.enlacesLegales')" class="enlaces-legales">
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
            <li>
              <a routerLink="/legal/condiciones-de-inscripcion">
                {{ t('legal.condicionesInscripcion') }}
              </a>
            </li>
            <li>
              <button type="button" class="enlace-boton" (click)="gestionarCookies()">
                {{ t('cookies.gestionar') }}
              </button>
            </li>
          </ul>
        </nav>
      </footer>

      <app-cookie-banner />
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 100vh;
    }
    /* .nav (eventarium.css:137-141): fija arriba con desenfoque y borde inferior;
       este chrome ya es una barra superior, así que se adopta literal. */
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      padding: var(--space-md) var(--space-lg);
      position: sticky;
      top: 0;
      z-index: 40;
      /* min-height:64px de .nav__in (eventarium.css:141). */
      min-height: 64px;
      background: var(--nav-bg);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }
    .marca {
      display: inline-flex;
      align-items: center;
      text-decoration: none;
      color: inherit;
    }
    /* .brand__name (eventarium.css:148): sin negrita explícita en la referencia,
       mayúsculas con tracking amplio. */
    .nombre {
      font-family: var(--font-heading);
      font-size: 1.35rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    nav {
      display: flex;
      /* gap:var(--sp-5) = 24px (eventarium.css:149/37): sin token exacto en
         nuestra escala de espaciado (--space-md es 16px). */
      gap: 1.5rem;
    }
    /* .nav__links a (eventarium.css:150-155): color muted en reposo, con
       subrayado en acento al hover/foco — no un color de acento fijo. */
    header nav a {
      color: var(--muted);
      text-decoration: none;
      font-size: var(--fs-sm);
      padding: 6px 2px;
      border-bottom: 1px solid transparent;
      transition:
        color 0.15s,
        border-color 0.15s;
    }
    header nav a:hover,
    header nav a:focus-visible {
      color: var(--fg);
      border-bottom-color: var(--accent);
    }
    main {
      padding: var(--space-lg);
    }
    /* .foot (eventarium.css:271-272): separador con borde superior, sin relleno
       de fondo — no es un panel. */
    footer {
      margin-top: 7rem; /* --sp-9 = 112px (eventarium.css:38), sin token exacto. */
      /* padding:var(--sp-6) 0 var(--sp-7) = 32px 0 48px (eventarium.css:38,271).
         --sp-6 coincide con --space-lg (32px); --sp-7 no tiene token exacto. */
      padding: var(--space-lg) 0 3rem;
      border-top: 1px solid var(--border);
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
    .enlace-boton {
      background: none;
      border: none;
      padding: 0;
      margin: 0;
      font: inherit;
      color: inherit;
      text-decoration: underline;
      cursor: pointer;
    }
  `,
})
export class PublicShell {
  protected readonly theming = inject(ThemingService);
  private readonly consentimiento = inject(CookieConsentService);

  protected gestionarCookies(): void {
    this.consentimiento.abrirGestionDeCookies();
  }
}
