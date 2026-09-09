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

import { AuthService, OrganizacionDeLaPersona, displayName } from '../../core/auth/auth.service';
import { ThemingService } from '../../core/theming/theming.service';
import { Button } from '../../shared/ui/button';
import { ThemeToggle } from '../../shared/ui/theme-toggle';
import { AdminNav } from './admin-nav';
import { EventScope } from './event-scope';

/**
 * Estructura del panel de administración: cabecera con marca, selector de
 * organizaciones, cuenta y sesión; navegación agrupada por ámbito
 * (`AdminNav`), colapsable en pantallas estrechas con gestión de foco.
 */
@Component({
  selector: 'app-admin-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, TranslocoDirective, Button, ThemeToggle, AdminNav],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido-admin">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <p class="marca">{{ theming.organizationName() }} · {{ t('admin.titulo') }}</p>
        <div class="sesion">
          <app-theme-toggle />
          @if (otrasOrganizaciones().length > 0) {
            <nav [attr.aria-label]="t('admin.selectorOrganizacion.titulo')" class="selector">
              @for (organizacion of organizaciones(); track organizacion.organization_id) {
                @if (organizacion.host) {
                  <a [href]="'https://' + organizacion.host + '/admin'">{{ organizacion.name }}</a>
                }
              }
            </nav>
          }
          @if (auth.currentUser(); as usuario) {
            <a routerLink="/admin/account">{{
              t('admin.sesionDe', { nombre: nombreDe(usuario) })
            }}</a>
          }
          <app-button variant="secundario" (pulsado)="cerrarSesion()">
            {{ t('admin.cerrarSesion') }}
          </app-button>
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
          <app-admin-nav [isSuperadmin]="esSuperadmin()" [evento]="grupoEvento()" />
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
      margin: 0;
      font-weight: 700;
    }
    .sesion {
      display: flex;
      align-items: center;
      gap: var(--space-md);
    }
    .selector {
      display: flex;
      gap: var(--space-sm);
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
      border-right: 1px solid var(--color-border);
      background-color: var(--color-surface-muted);
      padding-block: var(--space-md);
    }
    main {
      padding: var(--space-lg);
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
  protected readonly theming = inject(ThemingService);
  protected readonly nombreDe = displayName;
  private readonly router = inject(Router);
  private readonly eventScope = inject(EventScope);

  protected readonly organizaciones = signal<readonly OrganizacionDeLaPersona[]>([]);
  /** El selector solo tiene sentido con más de una organización. */
  protected readonly otrasOrganizaciones = signal<readonly OrganizacionDeLaPersona[]>([]);

  protected readonly esSuperadmin = computed(() => !!this.auth.currentUser()?.is_superadmin);

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
      this.otrasOrganizaciones.set(lista.length > 1 ? lista : []);
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
    await this.router.navigate(['/admin/login']);
  }
}
