import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { CookieBanner } from '../../shared/cookies/cookie-banner';
import { CookieConsentService } from '../../core/cookies/cookie-consent.service';
import { ThemingService } from '../../core/theming/theming.service';
import { AccessMenu } from '../../shared/ui/access-menu';
import { BrandLockup } from '../../shared/ui/brand-lockup';
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
  imports: [
    RouterOutlet,
    RouterLink,
    TranslocoDirective,
    CookieBanner,
    ThemeToggle,
    BrandLockup,
    Button,
    AccessMenu,
  ],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <div class="ancho-maximo header-en">
          <a routerLink="/" class="marca">
            <app-brand-lockup />
          </a>
          <div class="bloque-derecho">
            <nav [attr.aria-label]="t('publico.navegacion')">
              <!-- Sin «Inicio»: el logo ya enlaza a la raíz (la landing de la
                   instalación); aquí solo van el directorio y «Mis eventos». -->
              <a routerLink="/eventos">{{ t('publico.eventos.listadoTitulo') }}</a>
              <a routerLink="/mis-eventos">{{ t('publico.misEventos.enlaceNav') }}</a>
            </nav>
            <div class="controles-usuario">
              <!-- Mismo destino con o sin sesión: el guard del panel manda a
                   «/acceder?redirigir=…» a quien no la tiene, y desde ahí puede
                   registrarse; tras entrar vuelve directo a crear el evento. -->
              <a routerLink="/dashboard/events/nuevo" class="crear-evento">
                {{ t('publico.crearEvento') }}
              </a>
              <app-theme-toggle />
              <app-access-menu />
            </div>
          </div>
        </div>
      </header>

      <main id="contenido" tabindex="-1">
        <router-outlet />
      </main>

      <footer [attr.aria-label]="t('publico.piePagina')">
        <div class="ancho-maximo footer-en">
          <!-- Sin "Organizado por X": sin dominio por organización (fase 4
               del plan de organización sin dominio), este pie es el mismo
               para toda la web pública, pero cada página de evento puede
               ser de una organización distinta — "la" organización del
               sitio ya no existe. La atribución del organizador, si se
               quiere, iría en la propia ficha del evento, no en el chrome
               global (requeriría exponer el nombre de la organización en
               PublicEventDetail, no hecho aquí). -->
          @if (theming.plataforma()?.social_links?.length) {
            <nav [attr.aria-label]="t('publico.redesSociales')">
              <ul>
                @for (enlace of theming.plataforma()!.social_links; track enlace.url) {
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
          <a
            class="atribucion"
            href="https://humanitek.org"
            rel="noopener noreferrer"
            target="_blank"
          >
            <span>{{ t('publico.landing.pie.parteDe') }}</span>
            <!-- SVG como <img>, nunca inline: es un fichero de terceros y así no
                 puede ejecutar nada. Dimensiones fijas para evitar saltos de
                 maquetación. -->
            <img
              src="assets/humanitek-logo.svg"
              [alt]="t('publico.landing.pie.humanitek')"
              width="96"
              height="40"
            />
          </a>
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
      text-decoration: none;
      color: inherit;
    }
    /* Agrupa enlaces + controles de usuario como un único bloque a la
       derecha del logo — antes eran 4 hijos sueltos de .header-en con
       space-between, que los repartía a distancias iguales por todo el
       ancho en vez de agruparlos (hallazgo: el icono de tema quedaba lejos
       del menú de acceso en vez de pegado a él). */
    .bloque-derecho {
      display: flex;
      align-items: center;
      gap: 1.5rem;
    }
    .controles-usuario {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    /* Aspecto de app-button primario compacto; es un enlace (navega), no un
       botón. Misma altura que el conmutador de tema y el menú de acceso. */
    .crear-evento {
      display: inline-flex;
      align-items: center;
      min-height: 2.25rem;
      padding: 0 0.875rem;
      border-radius: var(--radius-sm);
      background-color: var(--accent);
      color: var(--on-accent);
      font-size: var(--fs-label);
      font-weight: 700;
      letter-spacing: 0.06em;
      text-decoration: none;
      white-space: nowrap;
      transition: background-color 0.15s ease;
    }
    .crear-evento:hover,
    .crear-evento:focus-visible {
      background-color: var(--accent-hi);
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
    .atribucion {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      justify-self: start;
      color: inherit;
      text-decoration: none;
      font-size: var(--fs-sm);
    }
    .atribucion img {
      display: block;
      height: 2.5rem;
      width: auto;
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
