import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import {
  AuthService,
  OrganizacionDeLaPersona,
  esPersonalDePlataforma,
} from '../../../core/auth/auth.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Card } from '../../../shared/ui/card';
import { monograma } from '../../../shared/text/monograma';

/**
 * Estado de una acción en curso: uno solo, global (no por tarjeta), para que
 * elegir una organización bloquee también "Admin Eventarium" y "Cerrar
 * sesión" mientras la primera está en vuelo — evita rotaciones concurrentes
 * del refresh token sobre la misma familia (mismo riesgo que
 * `admin-shell.ts::cambiandoOrganizacion`, ahí también con guarda global).
 */
type AccionEnCurso = 'organizacion' | 'plataforma' | 'sesion' | null;

/**
 * Pantalla a toda página para elegir con qué espacio de trabajo continuar:
 * una organización (con recarga completa vía `switchOrganization`, mismo
 * patrón que `admin-shell.ts::cambiarOrganizacion`) o el panel de plataforma
 * si la persona tiene ese rol.
 *
 * Vive fuera de `AdminShell` (como `login-page`), así que `authGuard` no
 * garantiza `auth.currentUser()` poblado (solo renueva el token). Por eso
 * carga explícitamente `loadCurrentUser()` antes de decidir si se muestra
 * "Admin Eventarium" — sin esto, la tarjeta desaparecería en silencio tras
 * cualquier recarga o enlace directo a esta ruta.
 */
@Component({
  selector: 'app-workspace-selector-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Card],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('admin.espacioDeTrabajo.titulo')">
        <app-card [heading]="t('admin.espacioDeTrabajo.titulo')">
          <p>{{ t('admin.espacioDeTrabajo.descripcion') }}</p>

          @if (error(); as mensaje) {
            <p role="alert" class="error">{{ mensaje }}</p>
          }

          @if (cargando()) {
            <p aria-live="polite">{{ t('comun.cargando') }}</p>
          } @else {
            <ul class="espacios">
              @for (org of organizaciones(); track org.organization_id) {
                <li>
                  <button
                    type="button"
                    [disabled]="accionEnCurso() !== null"
                    [attr.aria-busy]="accionEnCurso() === 'organizacion' ? 'true' : null"
                    (click)="elegirOrganizacion(org.organization_id)"
                  >
                    <span class="monograma" aria-hidden="true">{{
                      monograma(org.name, null, org.name)
                    }}</span>
                    <span class="texto">
                      <span class="nombre">{{ org.name }}</span>
                      @if (org.role_name; as rol) {
                        <span class="rol">{{ rol }}</span>
                      }
                    </span>
                    <span class="chevron" aria-hidden="true">›</span>
                  </button>
                </li>
              }
              @if (esAdminPlataforma()) {
                <li>
                  <button
                    type="button"
                    class="plataforma"
                    [disabled]="accionEnCurso() !== null"
                    [attr.aria-busy]="accionEnCurso() === 'plataforma' ? 'true' : null"
                    (click)="elegirPlataforma()"
                  >
                    <span class="monograma distintivo" aria-hidden="true">★</span>
                    <span class="texto">
                      <span class="nombre">{{ t('admin.espacioDeTrabajo.plataforma') }}</span>
                    </span>
                    <span class="chevron" aria-hidden="true">›</span>
                  </button>
                </li>
              }
            </ul>
          }

          <p class="cerrar-sesion">
            <button type="button" [disabled]="accionEnCurso() !== null" (click)="cerrarSesion()">
              {{ t('admin.cerrarSesion') }}
            </button>
          </p>
        </app-card>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    app-card {
      width: min(28rem, 100%);
      margin: var(--space-lg) auto;
    }
    p {
      margin: 0;
      color: var(--fg-muted, var(--fg));
    }
    .error {
      color: var(--danger, crimson);
    }
    .espacios {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      overflow: hidden;
    }
    .espacios li + li {
      border-top: 1px solid var(--border);
    }
    .espacios button {
      width: 100%;
      display: flex;
      align-items: center;
      gap: var(--space-md);
      padding: var(--space-md);
      background: none;
      border: none;
      text-align: left;
      cursor: pointer;
      font: inherit;
      color: inherit;
    }
    .espacios button:hover:not(:disabled) {
      background: var(--surface-hover, var(--surface));
    }
    .espacios button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .monograma {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 2.5rem;
      height: 2.5rem;
      border-radius: var(--radius-md);
      background: var(--surface);
      border: 1px solid var(--border);
      flex-shrink: 0;
    }
    /* Distintivo propio de la tarjeta de plataforma: no depende de ningún
       dato controlado por una organización (a diferencia de role_name,
       texto libre que una organización podría fijar como "Admin Eventarium"
       para confundir con esta tarjeta). */
    .monograma.distintivo {
      background: var(--accent, var(--fg));
      color: var(--on-accent, var(--bg));
      border-color: transparent;
    }
    .texto {
      display: grid;
      min-width: 0;
    }
    .nombre {
      font-weight: 600;
    }
    .rol {
      font-size: var(--fs-sm, 0.875rem);
      color: var(--fg-muted, var(--fg));
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .chevron {
      margin-left: auto;
      color: var(--fg-muted, var(--fg));
    }
    .cerrar-sesion {
      text-align: center;
    }
    .cerrar-sesion button {
      background: none;
      border: none;
      font: inherit;
      color: inherit;
      text-decoration: underline;
      cursor: pointer;
      padding: var(--space-sm);
    }
    .cerrar-sesion button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  `,
})
export class WorkspaceSelectorPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly transloco = inject(TranslocoService);

  protected readonly monograma = monograma;

  protected readonly cargando = signal(true);
  protected readonly organizaciones = signal<readonly OrganizacionDeLaPersona[]>([]);
  protected readonly esAdminPlataforma = signal(false);
  protected readonly accionEnCurso = signal<AccionEnCurso>(null);
  protected readonly error = signal<string | null>(null);

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      // `authGuard` solo renueva el token, nunca recarga el usuario: sin
      // esto, `esPersonalDePlataforma` vería siempre `currentUser() === null`
      // tras una recarga completa de esta pantalla.
      const usuario = await this.auth.loadCurrentUser();
      this.esAdminPlataforma.set(esPersonalDePlataforma(usuario));
      this.organizaciones.set(await this.auth.listMyOrganizations());
    } catch {
      this.error.set(this.transloco.translate('admin.espacioDeTrabajo.error'));
    } finally {
      this.cargando.set(false);
    }
  }

  protected async elegirOrganizacion(organizationId: string): Promise<void> {
    if (this.accionEnCurso()) {
      return;
    }
    this.accionEnCurso.set('organizacion');
    this.error.set(null);
    try {
      await this.auth.switchOrganization(organizationId);
      // Recarga completa, no `router.navigateByUrl`: mismo patrón que
      // `admin-shell.ts::cambiarOrganizacion` — más simple y fiable que
      // invalidar en memoria cada estado que depende de la organización
      // activa.
      window.location.href = '/dashboard';
    } catch (error) {
      this.accionEnCurso.set(null);
      if (error instanceof ApiError && error.status === 401) {
        await this.router.navigate(['/acceder']);
        return;
      }
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.espacioDeTrabajo.error'),
      );
    }
  }

  protected elegirPlataforma(): void {
    if (this.accionEnCurso()) {
      return;
    }
    this.accionEnCurso.set('plataforma');
    window.location.href = '/admin';
  }

  protected async cerrarSesion(): Promise<void> {
    if (this.accionEnCurso()) {
      return;
    }
    this.accionEnCurso.set('sesion');
    await this.auth.logout();
    await this.router.navigate(['/acceder']);
  }
}
