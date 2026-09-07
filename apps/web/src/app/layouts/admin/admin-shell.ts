import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthService, displayName } from '../../core/auth/auth.service';
import { ThemingService } from '../../core/theming/theming.service';
import { Button } from '../../shared/ui/button';

/** Estructura del panel de administración. */
@Component({
  selector: 'app-admin-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TranslocoDirective, Button],
  template: `
    <ng-container *transloco="let t">
      <a class="skip-link" href="#contenido-admin">{{ t('comun.saltarAlContenido') }}</a>

      <header>
        <p class="marca">{{ theming.organizationName() }} · {{ t('admin.titulo') }}</p>
        <div class="sesion">
          @if (auth.currentUser(); as usuario) {
            <span>{{ t('admin.sesionDe', { nombre: nombreDe(usuario) }) }}</span>
          }
          <app-button variant="secundario" (pulsado)="cerrarSesion()">
            {{ t('admin.cerrarSesion') }}
          </app-button>
        </div>
      </header>

      <div class="cuerpo">
        <nav [attr.aria-label]="t('admin.navegacion')">
          <ul>
            <li>
              <a
                routerLink="/admin"
                routerLinkActive="activo"
                [routerLinkActiveOptions]="{ exact: true }"
              >
                {{ t('admin.escritorio') }}
              </a>
            </li>
            <li>
              <a routerLink="/admin/organization" routerLinkActive="activo">
                {{ t('admin.organizacion.titulo') }}
              </a>
            </li>
            <li>
              <a routerLink="/admin/branding" routerLinkActive="activo">
                {{ t('admin.identidadVisual') }}
              </a>
            </li>
          </ul>
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
    .cuerpo {
      display: grid;
      grid-template-columns: minmax(12rem, 16rem) 1fr;
    }
    @media (max-width: 48rem) {
      .cuerpo {
        grid-template-columns: 1fr;
      }
    }
    nav {
      padding: var(--space-md);
      border-right: 1px solid var(--color-border);
      background-color: var(--color-surface-muted);
    }
    nav ul {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-xs);
    }
    nav a {
      display: block;
      padding: var(--space-sm) var(--space-md);
      border-radius: var(--radius-md);
      color: var(--color-text);
      text-decoration: none;
    }
    nav a.activo {
      background-color: var(--color-primary);
      color: var(--color-primary-contrast);
    }
    main {
      padding: var(--space-lg);
    }
  `,
})
export class AdminShell {
  protected readonly auth = inject(AuthService);
  protected readonly theming = inject(ThemingService);
  protected readonly nombreDe = displayName;
  private readonly router = inject(Router);

  protected async cerrarSesion(): Promise<void> {
    await this.auth.logout();
    await this.router.navigate(['/admin/login']);
  }
}
