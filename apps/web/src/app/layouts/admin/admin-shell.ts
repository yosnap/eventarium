import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthService, OrganizacionDeLaPersona } from '../../core/auth/auth.service';
import { BrandLockup } from '../../shared/ui/brand-lockup';
import { ThemeToggle } from '../../shared/ui/theme-toggle';
import { AccountMenu } from './account-menu';
import { AdminNav } from './admin-nav';
import { PanelScope } from './panel-scope';

/**
 * Estructura del panel de administración: cabecera con marca, menú de
 * cuenta, y navegación agrupada por ámbito (`AdminNav`), colapsable en
 * pantallas estrechas con gestión de foco.
 */
@Component({
  selector: 'app-admin-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterOutlet,
    RouterLink,
    TranslocoDirective,
    ThemeToggle,
    AdminNav,
    BrandLockup,
    AccountMenu,
  ],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido-admin">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <div class="ancho-maximo header-en">
          <div class="marca">
            <a routerLink="/" class="enlace-marca">
              <app-brand-lockup />
            </a>
            <p class="contexto">
              @if (esPanelPlataforma()) {
                {{ t('admin.tituloPlataforma') }}
              } @else {
                {{ nombrePanel() }} · {{ t('admin.titulo') }}
              }
            </p>
          </div>
          <div class="sesion">
            <app-theme-toggle />
            <app-account-menu
              [email]="auth.currentUser()?.email ?? ''"
              [nuevaOrganizacion]="!esPanelPlataforma()"
              (cerrarSesion)="cerrarSesion()"
            />
          </div>
        </div>
      </header>

      <div class="cuerpo">
        <button
          #botonNavegacion
          type="button"
          class="boton-navegacion"
          [attr.aria-expanded]="navegacionAbierta()"
          aria-controls="panel-navegacion-admin"
          (click)="alternarNavegacion()"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
            @if (navegacionAbierta()) {
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" fill="none" />
            } @else {
              <path
                d="M4 7h16M4 12h16M4 17h16"
                stroke="currentColor"
                stroke-width="2"
                fill="none"
              />
            }
          </svg>
          {{
            navegacionAbierta() ? t('admin.nav.cerrarNavegacion') : t('admin.nav.abrirNavegacion')
          }}
        </button>

        <nav
          #panelNavegacion
          id="panel-navegacion-admin"
          class="panel-navegacion"
          tabindex="-1"
          [class.abierta]="navegacionAbierta()"
          [attr.aria-label]="t('admin.navegacion')"
          (keydown.escape)="cerrarNavegacion()"
        >
          <app-admin-nav [plataforma]="esPanelPlataforma()" />
        </nav>

        <main id="contenido-admin" tabindex="-1">
          <router-outlet />
        </main>
      </div>
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 100vh;
    }
    /* .nav (eventarium.css:137-141): fija arriba, con desenfoque de fondo y borde
       inferior, a sangre completa; el contenido interno (.nav__in.wrap) es quien
       se centra al ancho máximo, no la barra en sí — mismo patrón que
       PublicShell y AuthFrame, para que la cabecera sea igual en toda la web. */
    header {
      position: sticky;
      top: 0;
      z-index: 40;
      background: var(--nav-bg);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }
    /* .nav__in (eventarium.css:141): min-height:64px. */
    .header-en {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
      padding: var(--space-md) var(--space-lg);
      min-height: 64px;
    }
    /* El logo de la plataforma es el mismo que en la web pública; el panel
       en el que se está va al lado, como texto secundario. */
    .marca {
      display: flex;
      align-items: center;
      gap: var(--space-md);
    }
    .enlace-marca {
      display: inline-flex;
      text-decoration: none;
      color: inherit;
    }
    .contexto {
      margin: 0;
      padding-left: var(--space-md);
      border-left: 1px solid var(--border);
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .sesion {
      display: flex;
      align-items: center;
      gap: var(--space-md);
    }
    .cuerpo {
      display: grid;
      grid-template-columns: minmax(12rem, 16rem) 1fr;
    }
    .boton-navegacion {
      display: none;
      margin: var(--space-md);
    }
    .panel-navegacion {
      border-right: 1px solid var(--border);
      background-color: var(--surface-2);
      padding-block: var(--space-md);
    }
    /* .main del prototipo: --sp-6 (32px) arriba y a los lados, --sp-8 (72px)
       abajo — el panel respira al final de la página. */
    main {
      padding: var(--sp-6) var(--sp-6) var(--sp-8);
    }
    @media (max-width: 48rem) {
      /* Cabecera compacta: logo, tema y cuenta en una fila; el nombre de la
         organización debajo, en una línea. Antes ocupaba casi 200 px. */
      .header-en {
        display: grid;
        /* El logo nunca encoge; lo que sobra lo cede la cuenta (el correo
           se recorta con puntos suspensivos). */
        grid-template-columns: auto minmax(0, 1fr);
        grid-template-areas:
          'logo sesion'
          'contexto contexto';
        gap: var(--space-xs) var(--space-sm);
        padding: var(--space-sm) var(--space-md);
        min-height: 0;
      }
      .marca {
        display: contents;
      }
      .enlace-marca {
        grid-area: logo;
      }
      .sesion {
        grid-area: sesion;
        justify-content: flex-end;
        min-width: 0;
        gap: var(--space-sm);
      }
      .contexto {
        grid-area: contexto;
        padding-left: 0;
        border-left: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .cuerpo {
        grid-template-columns: minmax(0, 1fr);
      }
      .boton-navegacion {
        display: inline-flex;
        align-items: center;
        gap: var(--space-sm);
        min-height: 44px;
        margin: var(--space-sm) var(--space-md) 0;
        padding: 0 var(--space-md);
        border: 1px solid var(--border-strong);
        border-radius: var(--radius-sm);
        background-color: var(--surface);
        color: var(--fg);
        font: inherit;
        font-size: var(--fs-sm);
        font-weight: 500;
        cursor: pointer;
      }
      main {
        padding: var(--space-md) var(--space-md) var(--sp-8);
      }
      .panel-navegacion:not(.abierta) {
        display: none;
      }
    }
  `,
})
export class AdminShell {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly panelScope = inject(PanelScope);

  /** En qué panel está el shell (`/admin` plataforma, `/dashboard` organización). */
  protected readonly esPanelPlataforma = this.panelScope.esPlataforma;

  protected readonly organizaciones = signal<readonly OrganizacionDeLaPersona[]>([]);
  /**
   * Nombre a mostrar en la cabecera del panel de organización.
   *
   * Antes venía de `theming.nombreDeOrganizacion()` (`/tenant/branding`,
   * resuelto por host) — sin dominio por organización, ese host ya no tiene
   * ninguna relación con la organización activa de la sesión (fase 4 del
   * plan de organización sin dominio): mostraría siempre la misma
   * organización para todo el mundo, sin importar a cuál se haya cambiado.
   * Se calcula en su lugar cruzando `organization_id` del usuario cargado
   * con la lista de organizaciones a las que pertenece. Mientras ninguna de
   * las dos cargas ha resuelto, cadena vacía — nunca el nombre por host: un
   * parpadeo en blanco es aceptable, mostrar la organización equivocada es
   * el mismo error que esto corrige.
   */
  protected readonly nombrePanel = computed(() => {
    const id = this.auth.currentUser()?.organization_id;
    const encontrada = id ? this.organizaciones().find((o) => o.organization_id === id) : null;
    return encontrada?.name ?? '';
  });

  protected readonly navegacionAbierta = signal(false);
  private readonly panelNavegacion = viewChild<ElementRef<HTMLElement>>('panelNavegacion');
  private readonly botonNavegacion = viewChild<ElementRef<HTMLButtonElement>>('botonNavegacion');
  private seAbrioAlgunaVez = false;

  constructor() {
    void this.cargarOrganizaciones();
    // `authGuard` solo renueva el token en una recarga, nunca recarga el
    // usuario: sin esto, `nombrePanel`/`auth.currentUser()` se quedarían
    // vacíos justo después de cambiar o crear una organización (que recargan
    // la página entera a propósito).
    void this.auth.loadCurrentUser().catch(() => {
      // Mismo criterio que `cargarOrganizaciones`: un fallo aquí no debe
      // impedir usar el resto del panel.
    });

    // Gestión de foco del panel colapsable (WCAG 2.4.3): al abrir, el foco entra en
    // el primer enlace del panel; al cerrar, vuelve al botón que lo abrió.
    effect(() => {
      if (this.navegacionAbierta()) {
        this.seAbrioAlgunaVez = true;
        this.panelNavegacion()?.nativeElement.querySelector<HTMLElement>('a, button')?.focus();
      } else if (this.seAbrioAlgunaVez) {
        this.seAbrioAlgunaVez = false;
        this.botonNavegacion()?.nativeElement.focus();
      }
    });

    // `authGuard` solo comprueba la sesión AL ENTRAR — si el token se queda a
    // `null` mientras la persona ya está dentro del panel (el refresh de
    // `authInterceptor` agotó su único reintento: cookie de refresco
    // caducada, sesión cerrada en otra pestaña…), nada volvía a comprobarlo:
    // cada petición seguía saliendo sin cabecera y la pantalla se quedaba
    // mostrando el error crudo del backend indefinidamente (hallazgo del
    // usuario, en un polling de OCR de justificantes que llevaba minutos
    // reintentando sin avisar). El shell envuelve TODO el panel, así que es
    // el único sitio que ve la sesión morir sin importar en qué página
    // estuviera — mismo destino y mismo `redirigir` que usa `authGuard` al
    // entrar, para volver exactamente a donde estaba tras loguearse de nuevo.
    //
    // Es el ÚNICO sitio que navega a `/acceder` cuando la sesión muere —
    // `cerrarSesion()` ya no llama a `router.navigate()` por su cuenta (ver
    // más abajo). Antes lo hacían los dos: `cerrarSesion()` navegaba sin
    // `redirigir`, y este efecto, al ver `isAuthenticated()` a `false`
    // (`logout()` también limpia el token), lanzaba una SEGUNDA navegación
    // con `redirigir` detrás — `router.url` todavía no reflejaba la
    // navegación de `cerrarSesion()` en curso (no se actualiza hasta que
    // resuelve, y de camino pasa por `guestGuard`, que es asíncrono), así
    // que la comprobación `!router.url.startsWith('/acceder')` no la
    // detectaba a tiempo: la segunda navegación ganaba la carrera y la
    // sesión siguiente aterrizaba de vuelta en el panel en vez del login
    // limpio (hallazgo de code-review, reproducido). Con un único punto de
    // navegación la carrera desaparece por construcción, no por temporización.
    //
    // El motivo del cierre (`cierreFueDeliberado`) lo lleva `AuthService`,
    // no una bandera local puesta antes de `await auth.logout()`: si la
    // sesión muriera por otra vía (refresh fallido) mientras ese `await`
    // sigue en vuelo, una bandera local la consumiría la transición
    // equivocada y perdería el `redirigir`. `clear()` conoce el motivo en
    // el momento exacto en que ocurre.
    effect(() => {
      if (this.auth.isAuthenticated()) {
        return;
      }
      if (this.auth.cierreFueDeliberado()) {
        void this.router.navigate(['/acceder']);
      } else {
        void this.router.navigate(['/acceder'], { queryParams: { redirigir: this.router.url } });
      }
    });
  }

  private async cargarOrganizaciones(): Promise<void> {
    try {
      const lista = await this.auth.listMyOrganizations();
      this.organizaciones.set(lista);
    } catch {
      // El selector es una ayuda de navegación, no algo crítico: un fallo aquí no
      // debe impedir usar el resto del panel.
    }
  }

  protected alternarNavegacion(): void {
    this.navegacionAbierta.update((abierta) => !abierta);
  }

  protected cerrarNavegacion(): void {
    this.navegacionAbierta.set(false);
  }

  protected async cerrarSesion(): Promise<void> {
    await this.auth.logout();
  }
}
