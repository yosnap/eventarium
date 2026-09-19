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
import { Router, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthService, OrganizacionDeLaPersona } from '../../core/auth/auth.service';
import { BrandMark } from '../../shared/ui/brand-mark';
import { ThemeToggle } from '../../shared/ui/theme-toggle';
import { AccountMenu } from './account-menu';
import { AdminNav } from './admin-nav';
import { EventScope } from './event-scope';
import { PanelScope } from './panel-scope';

/**
 * Estructura del panel de administración: cabecera con marca, menú de
 * cuenta, y navegación agrupada por ámbito (`AdminNav`), colapsable en
 * pantallas estrechas con gestión de foco.
 */
@Component({
  selector: 'app-admin-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, TranslocoDirective, ThemeToggle, AdminNav, BrandMark, AccountMenu],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido-admin">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <div class="ancho-maximo header-en">
          <p class="marca">
            <app-brand-mark [nombre]="nombrePanel()" />
            @if (esPanelPlataforma()) {
              {{ t('admin.tituloPlataforma') }}
            } @else {
              {{ nombrePanel() }} · {{ t('admin.titulo') }}
            }
          </p>
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
          <app-admin-nav [plataforma]="esPanelPlataforma()" [evento]="grupoEvento()" />
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
    .marca {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 0;
      /* Tipografía de marca de .brand__name (eventarium.css:148): display,
         mayúsculas, tracking amplio, en vez de sans en negrita. */
      font-family: var(--font-display);
      font-size: 1.35rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
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
      .cuerpo {
        grid-template-columns: 1fr;
      }
      .boton-navegacion {
        display: inline-flex;
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
  private readonly eventScope = inject(EventScope);
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

  /** `null` sin evento activo o con fallo de carga: en ambos casos la navegación
   * conserva solo los dos grupos estables. */
  protected readonly grupoEvento = computed(() => {
    const id = this.eventScope.eventId();
    if (!id || this.eventScope.falloCarga()) {
      return null;
    }
    return {
      id,
      nombre: this.eventScope.nombreEvento(),
      cargando: this.eventScope.cargando(),
      aceptaPagos: this.eventScope.registrationMode() === 'paid',
    };
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
    await this.router.navigate(['/acceder']);
  }
}
