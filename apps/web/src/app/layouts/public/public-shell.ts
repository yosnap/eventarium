import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { CookieBanner } from '../../shared/cookies/cookie-banner';
import { CookieConsentService } from '../../core/cookies/cookie-consent.service';
import { ThemingService } from '../../core/theming/theming.service';
import { BrandMark } from '../../shared/ui/brand-mark';
import { Button } from '../../shared/ui/button';
import { ThemeToggle } from '../../shared/ui/theme-toggle';

/**
 * Estructura de la web pública: cabecera con la marca de la organización, contenido y
 * pie. Los `landmark` (`header`, `nav`, `main`, `footer`) permiten navegar por regiones
 * con un lector de pantalla.
 */
@Component({
  selector: 'app-public-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, TranslocoDirective, CookieBanner, ThemeToggle, BrandMark, Button],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <div class="ancho-maximo header-en">
          <a routerLink="/" class="marca">
            @if (theming.branding()?.logo_url; as logo) {
              <img [src]="logo" [alt]="theming.organizationName()" height="40" />
            } @else {
              <app-brand-mark [nombre]="theming.organizationName()" />
              <span class="nombre">{{ theming.organizationName() }}</span>
            }
          </a>
          <nav [attr.aria-label]="t('publico.navegacion')">
            <a routerLink="/">{{ t('publico.inicio') }}</a>
            <a routerLink="/eventos">{{ t('publico.eventos.listadoTitulo') }}</a>
            <a routerLink="/admin">{{ t('publico.accesoPanel') }}</a>
          </nav>
          <app-theme-toggle />
        </div>
      </header>

      <main id="contenido" tabindex="-1">
        <router-outlet />
      </main>

      <footer [attr.aria-label]="t('publico.piePagina')">
        <div class="ancho-maximo footer-en">
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
            </ul>
          </nav>
          <app-button variant="terciario" [compacto]="true" (pulsado)="gestionarCookies()">
            {{ t('cookies.gestionar') }}
          </app-button>
        </div>
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
    /* .nav (eventarium.css:137-141): fija arriba con desenfoque y borde inferior,
       a sangre completa; el contenido interno (.nav__in.wrap) es quien se centra
       al ancho máximo, no la barra en sí. */
    header {
      position: sticky;
      top: 0;
      z-index: 40;
      background: var(--nav-bg);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }
    /* .nav__in (eventarium.css:141): min-height:64px, gap:var(--sp-5)=24px. */
    .header-en {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      min-height: 64px;
    }
    .marca {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      text-decoration: none;
      color: inherit;
    }
    /* .brand__name (eventarium.css:148): sin negrita explícita en la referencia,
       mayúsculas con tracking amplio. */
    .nombre {
      font-family: var(--font-display);
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
    /* Sin padding propio: cada página gestiona su spacing vertical, y el ancho
       horizontal lo impone siempre .ancho-maximo dentro de la página, nunca
       este contenedor — así una sección puede seguir siendo a sangre completa
       (fondo, borde) con su contenido centrado dentro, igual que el header. */
    main {
      display: block;
    }
    /* .foot (eventarium.css:271-272): separador con borde superior a sangre
       completa, sin relleno de fondo — no es un panel. */
    footer {
      margin-top: var(--sp-9);
      border-top: 1px solid var(--border);
      color: var(--muted);
    }
    .footer-en {
      padding: var(--sp-6) 0 var(--sp-7);
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
  private readonly consentimiento = inject(CookieConsentService);

  protected gestionarCookies(): void {
    this.consentimiento.abrirGestionDeCookies();
  }
}
