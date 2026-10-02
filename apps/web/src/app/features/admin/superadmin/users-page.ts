import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { AuthService } from '../../../core/auth/auth.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { OrganizationResponse } from '../../../core/api/generated/models/organization-response';
import { PagePlatformUserSummary } from '../../../core/api/generated/models/page-platform-user-summary';
import { PlatformUserDetail } from '../../../core/api/generated/models/platform-user-detail';
import { PlatformUserSummary } from '../../../core/api/generated/models/platform-user-summary';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Chip } from '../../../shared/ui/chip';
import { DataTable, DataTableColumn } from '../../../shared/ui/data-table';
import { Input } from '../../../shared/ui/input';
import { PageHeader } from '../../../shared/ui/page-header';
import { Select, SelectOption } from '../../../shared/ui/select';

const LIMITE = 20;

/**
 * Directorio de usuarios de la instalación (`/admin/usuarios`).
 *
 * Listado + detalle en la misma página (decisión de implementación de la
 * fase 4 del plan `260916-0810-usuarios-y-permisos-plataforma`): las
 * acciones sensibles (desactivar, rol de plataforma) están deshabilitadas
 * para quien no es superadmin -`soporte` solo ve, nunca escribe- y para la
 * propia cuenta, mismo patrón de confirmación en dos pasos que ya usa
 * `roles-page.ts` para no dejar un botón destructivo a un solo clic.
 *
 * Verificar a mano y reenviar la verificación viven en la propia fila (no
 * solo en el detalle): es la acción que más se repite cuando el correo no
 * llega, y abrir el detalle por cada cuenta pendiente sobraba.
 */
@Component({
  selector: 'app-users-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Chip, DataTable, Input, PageHeader, Select],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.plataforma.usuarios.titulo')">
        {{ t('admin.plataforma.usuarios.descripcion') }}
      </app-page-header>

      <app-card [heading]="t('admin.plataforma.usuarios.filtros')">
        <div class="filtros">
          <app-input
            [label]="t('admin.plataforma.usuarios.buscar')"
            [(value)]="q"
            (blurred)="irAPagina(0)"
          />
          <app-select
            [label]="t('admin.plataforma.usuarios.organizacion')"
            [options]="opcionesDeOrganizacion()"
            [(value)]="organizationId"
          />
          <app-select
            [label]="t('admin.plataforma.usuarios.rolDePlataforma')"
            [options]="opcionesDeRol()"
            [(value)]="platformRole"
          />
          <app-button type="button" variant="secundario" (pulsado)="irAPagina(0)">
            {{ t('admin.plataforma.usuarios.filtrar') }}
          </app-button>
        </div>
      </app-card>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }
      @if (aviso(); as mensaje) {
        <app-alert tone="exito">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (usuarios().length === 0) {
        <p>{{ t('admin.plataforma.usuarios.sinResultados') }}</p>
      } @else {
        <app-data-table [columnas]="columnas()" [caption]="t('admin.plataforma.usuarios.titulo')">
          @for (usuario of usuarios(); track usuario.id) {
            <tr [class.fila-seleccionada]="usuarioSeleccionadoId() === usuario.id">
              <td>
                <button type="button" class="fila-boton" (click)="seleccionar(usuario.id)">
                  {{ nombreDe(usuario) }}
                </button>
              </td>
              <td>{{ usuario.email }}</td>
              <td>
                {{
                  usuario.is_active
                    ? t('admin.plataforma.usuarios.activo')
                    : t('admin.plataforma.usuarios.inactivo')
                }}
              </td>
              <td>
                @if (usuario.email_verified) {
                  <app-chip tone="ok">{{ t('admin.plataforma.usuarios.verificado') }}</app-chip>
                } @else {
                  <app-chip tone="espera">{{
                    t('admin.plataforma.usuarios.sinVerificar')
                  }}</app-chip>
                }
              </td>
              <td>{{ usuario.platform_role ?? t('admin.plataforma.usuarios.sinRol') }}</td>
              <td>
                {{ usuario.organization_names || t('admin.plataforma.usuarios.sinOrganizaciones') }}
              </td>
              @if (esSuperadmin()) {
                <td>
                  @if (!usuario.email_verified && usuario.is_active) {
                    <div class="acciones-fila">
                      <app-button
                        type="button"
                        variant="secundario"
                        [compacto]="true"
                        [loading]="accionEnCurso() === usuario.id + ':verificar'"
                        [disabled]="accionEnCurso() !== null"
                        [ariaLabel]="
                          t('admin.plataforma.usuarios.verificarAManoAria', {
                            correo: usuario.email,
                          })
                        "
                        (pulsado)="verificarAMano(usuario)"
                      >
                        {{ t('admin.plataforma.usuarios.verificarAMano') }}
                      </app-button>
                      <app-button
                        type="button"
                        variant="terciario"
                        [compacto]="true"
                        [loading]="accionEnCurso() === usuario.id + ':reenviar'"
                        [disabled]="accionEnCurso() !== null"
                        [ariaLabel]="
                          t('admin.plataforma.usuarios.reenviarVerificacionAria', {
                            correo: usuario.email,
                          })
                        "
                        (pulsado)="reenviarVerificacion(usuario)"
                      >
                        {{ t('admin.plataforma.usuarios.reenviarVerificacion') }}
                      </app-button>
                    </div>
                  }
                </td>
              }
            </tr>
          }
        </app-data-table>

        @if (totalPaginas() > 1) {
          <nav [attr.aria-label]="t('admin.plataforma.usuarios.titulo')" class="paginacion">
            <app-button
              variant="secundario"
              type="button"
              [disabled]="offset() === 0"
              (pulsado)="irAPagina(offset() - limite)"
            >
              {{ t('admin.members.anterior') }}
            </app-button>
            <span>
              {{ t('admin.members.paginaDe', { actual: paginaActual(), total: totalPaginas() }) }}
            </span>
            <app-button
              variant="secundario"
              type="button"
              [disabled]="offset() + limite >= total()"
              (pulsado)="irAPagina(offset() + limite)"
            >
              {{ t('admin.members.siguiente') }}
            </app-button>
          </nav>
        }
      }

      @if (detalle(); as usuario) {
        <app-card [heading]="t('admin.plataforma.usuarios.detalle')">
          @if (errorDetalle(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <dl class="detalle-datos">
            <dt>{{ t('admin.plataforma.usuarios.buscar') }}</dt>
            <dd>{{ usuario.email }}</dd>
            <dt>{{ t('admin.plataforma.usuarios.columnaVerificacion') }}</dt>
            <dd>
              {{
                usuario.email_verified
                  ? t('admin.plataforma.usuarios.verificado')
                  : t('admin.plataforma.usuarios.sinVerificar')
              }}
            </dd>
            <dt>{{ t('admin.plataforma.usuarios.organizacion') }}</dt>
            <dd>
              @if (usuario.organizations.length === 0) {
                {{ t('admin.plataforma.usuarios.sinOrganizaciones') }}
              } @else {
                <ul>
                  @for (org of usuario.organizations; track org.organization_id) {
                    <li>{{ org.organization_name }} — {{ org.role_name }}</li>
                  }
                </ul>
              }
            </dd>
            <dt>{{ t('admin.plataforma.usuarios.inscripciones') }}</dt>
            <dd>{{ usuario.registrations_count }}</dd>
            <dt>{{ t('admin.plataforma.usuarios.preferenciaNotificaciones') }}</dt>
            <dd>
              {{ usuario.notify_similar_events ? t('comun.si') : t('comun.no') }}
            </dd>
          </dl>

          @if (esSuperadmin()) {
            <div class="acciones-detalle">
              <app-select
                [label]="t('admin.plataforma.usuarios.rolDePlataforma')"
                [options]="opcionesDeRolEditable()"
                [(value)]="rolSeleccionado"
                [disabled]="usuario.id === miPropioId()"
              />
              <app-button
                type="button"
                variant="secundario"
                [loading]="guardandoRol()"
                [disabled]="usuario.id === miPropioId()"
                (pulsado)="guardarRol(usuario.id)"
              >
                {{ t('admin.plataforma.usuarios.guardarRol') }}
              </app-button>

              @if (usuario.is_active) {
                @if (pendienteDeDesactivar()) {
                  <app-button
                    type="button"
                    variant="peligro"
                    [loading]="desactivando()"
                    [disabled]="usuario.id === miPropioId()"
                    (pulsado)="confirmarDesactivar(usuario.id)"
                  >
                    {{ t('admin.plataforma.usuarios.confirmarDesactivar') }}
                  </app-button>
                  <app-button
                    type="button"
                    variant="secundario"
                    (pulsado)="pendienteDeDesactivar.set(false)"
                  >
                    {{ t('admin.roles.cancelar') }}
                  </app-button>
                } @else {
                  <app-button
                    type="button"
                    variant="secundario"
                    [disabled]="usuario.id === miPropioId()"
                    (pulsado)="pendienteDeDesactivar.set(true)"
                  >
                    {{ t('admin.plataforma.usuarios.desactivar') }}
                  </app-button>
                }
              }
            </div>
          }
        </app-card>
      }
    </ng-container>
  `,
  styles: `
    .filtros {
      display: grid;
      grid-template-columns: 2fr 1fr 1fr auto;
      gap: var(--space-md);
      align-items: end;
    }
    @media (max-width: 48rem) {
      .filtros {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    .fila-boton {
      background: none;
      border: none;
      color: var(--accent);
      cursor: pointer;
      font: inherit;
      padding: 0;
      text-align: left;
    }
    .fila-seleccionada {
      background-color: var(--surface-hi);
    }
    .paginacion {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: var(--space-md);
      margin-top: var(--space-md);
    }
    .detalle-datos {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: var(--space-xs) var(--space-md);
      margin: 0 0 var(--space-md);
    }
    .detalle-datos dt {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .detalle-datos dd {
      margin: 0;
    }
    .detalle-datos ul {
      margin: 0;
      padding-left: 1.2em;
    }
    .acciones-fila {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs);
    }
    .acciones-detalle {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      align-items: end;
    }
  `,
})
export class UsersPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly auth = inject(AuthService);

  protected readonly cargando = signal(true);
  protected readonly usuarios = signal<PlatformUserSummary[]>([]);
  protected readonly total = signal(0);
  protected readonly offset = signal(0);
  protected readonly limite = LIMITE;
  protected readonly error = signal<string | null>(null);

  protected readonly q = signal('');
  protected readonly organizationId = signal('');
  protected readonly platformRole = signal('');
  protected readonly organizaciones = signal<OrganizationResponse[]>([]);

  protected readonly usuarioSeleccionadoId = signal<string | null>(null);
  protected readonly detalle = signal<PlatformUserDetail | null>(null);
  protected readonly errorDetalle = signal<string | null>(null);
  protected readonly rolSeleccionado = signal('');
  protected readonly guardandoRol = signal(false);
  protected readonly pendienteDeDesactivar = signal(false);
  protected readonly desactivando = signal(false);
  /** `"<id>:verificar"` o `"<id>:reenviar"` mientras una acción de fila está
   * en vuelo; bloquea el resto para no encadenar clics sobre datos viejos. */
  protected readonly accionEnCurso = signal<string | null>(null);
  protected readonly aviso = signal<string | null>(null);

  protected readonly esSuperadmin = computed(() => this.auth.currentUser()?.is_superadmin ?? false);
  protected readonly miPropioId = computed(() => this.auth.currentUser()?.id ?? null);

  protected readonly totalPaginas = computed(() => Math.max(1, Math.ceil(this.total() / LIMITE)));
  protected readonly paginaActual = computed(() => Math.floor(this.offset() / LIMITE) + 1);
  protected readonly nombreDe = (usuario: PlatformUserSummary): string => {
    const nombre = [usuario.first_name, usuario.last_name].filter(Boolean).join(' ').trim();
    return nombre || usuario.email;
  };

  protected readonly columnas = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'nombre', label: t('admin.plataforma.usuarios.columnaNombre') },
      { key: 'correo', label: t('admin.plataforma.usuarios.columnaCorreo') },
      { key: 'estado', label: t('admin.plataforma.usuarios.columnaEstado') },
      { key: 'verificacion', label: t('admin.plataforma.usuarios.columnaVerificacion') },
      { key: 'rol', label: t('admin.plataforma.usuarios.rolDePlataforma') },
      { key: 'organizaciones', label: t('admin.plataforma.usuarios.columnaOrganizaciones') },
      // `soporte` solo lee: sin columna de acciones, no una columna vacía.
      ...(this.esSuperadmin()
        ? [{ key: 'acciones', label: t('admin.plataforma.usuarios.columnaAcciones') }]
        : []),
    ];
  });

  protected readonly opcionesDeOrganizacion = computed<SelectOption[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { value: '', label: t('admin.plataforma.usuarios.todasLasOrganizaciones') },
      ...this.organizaciones().map((org) => ({ value: org.id, label: org.name })),
    ];
  });

  protected readonly opcionesDeRol = computed<SelectOption[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { value: '', label: t('admin.plataforma.usuarios.todosLosRoles') },
      { value: 'soporte', label: 'soporte' },
    ];
  });

  protected readonly opcionesDeRolEditable = computed<SelectOption[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { value: '', label: t('admin.plataforma.usuarios.sinRol') },
      { value: 'soporte', label: 'soporte' },
    ];
  });

  constructor() {
    void this.cargarOrganizaciones();
    void this.cargar();
  }

  private async cargarOrganizaciones(): Promise<void> {
    try {
      this.organizaciones.set(
        await firstValueFrom(
          this.http.get<OrganizationResponse[]>(this.api.url('/admin/organizations')),
        ),
      );
    } catch {
      // El filtro por organización es una comodidad, no algo bloqueante: si
      // no carga, el listado sigue funcionando sin ese filtro.
    }
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    this.error.set(null);
    try {
      const params: Record<string, string | number> = {
        limit: LIMITE,
        offset: this.offset(),
      };
      if (this.q().trim()) params['q'] = this.q().trim();
      if (this.organizationId()) params['organization_id'] = this.organizationId();
      if (this.platformRole()) params['platform_role'] = this.platformRole();

      const pagina = await firstValueFrom(
        this.http.get<PagePlatformUserSummary>(this.api.url('/admin/users'), { params }),
      );
      this.usuarios.set([...pagina.items]);
      this.total.set(pagina.total);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.plataforma.usuarios.errorLista'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected irAPagina(nuevoOffset: number): void {
    this.offset.set(Math.max(0, nuevoOffset));
    void this.cargar();
  }

  protected async seleccionar(userId: string): Promise<void> {
    this.usuarioSeleccionadoId.set(userId);
    this.detalle.set(null);
    this.errorDetalle.set(null);
    this.pendienteDeDesactivar.set(false);
    try {
      const usuario = await firstValueFrom(
        this.http.get<PlatformUserDetail>(this.api.url(`/admin/users/${userId}`)),
      );
      this.detalle.set(usuario);
      this.rolSeleccionado.set(usuario.platform_role ?? '');
    } catch (error) {
      this.errorDetalle.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.plataforma.usuarios.errorDetalle'),
      );
    }
  }

  protected async guardarRol(userId: string): Promise<void> {
    this.errorDetalle.set(null);
    this.guardandoRol.set(true);
    try {
      const actualizado = await firstValueFrom(
        this.http.put<{ platform_role: string | null }>(
          this.api.url(`/admin/users/${userId}/platform-role`),
          { platform_role: this.rolSeleccionado() || null },
        ),
      );
      this.detalle.update((actual) =>
        actual ? { ...actual, platform_role: actualizado.platform_role } : actual,
      );
      await this.cargar();
    } catch (error) {
      this.errorDetalle.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.plataforma.usuarios.errorRol'),
      );
    } finally {
      this.guardandoRol.set(false);
    }
  }

  protected async confirmarDesactivar(userId: string): Promise<void> {
    this.errorDetalle.set(null);
    this.desactivando.set(true);
    try {
      await firstValueFrom(this.http.post(this.api.url(`/admin/users/${userId}/deactivate`), {}));
      await this.seleccionar(userId);
      await this.cargar();
    } catch (error) {
      this.errorDetalle.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.plataforma.usuarios.errorDesactivar'),
      );
    } finally {
      this.desactivando.set(false);
      this.pendienteDeDesactivar.set(false);
    }
  }

  protected async verificarAMano(usuario: PlatformUserSummary): Promise<void> {
    await this.accionDeVerificacion(usuario, 'verificar', 'verify-email', {
      exito: 'admin.plataforma.usuarios.correoVerificado',
      error: 'admin.plataforma.usuarios.errorVerificar',
    });
  }

  protected async reenviarVerificacion(usuario: PlatformUserSummary): Promise<void> {
    await this.accionDeVerificacion(usuario, 'reenviar', 'resend-verification', {
      exito: 'admin.plataforma.usuarios.verificacionReenviada',
      error: 'admin.plataforma.usuarios.errorReenviar',
    });
  }

  private async accionDeVerificacion(
    usuario: PlatformUserSummary,
    accion: 'verificar' | 'reenviar',
    ruta: 'verify-email' | 'resend-verification',
    claves: { readonly exito: string; readonly error: string },
  ): Promise<void> {
    this.error.set(null);
    this.aviso.set(null);
    this.accionEnCurso.set(`${usuario.id}:${accion}`);
    try {
      await firstValueFrom(this.http.post(this.api.url(`/admin/users/${usuario.id}/${ruta}`), {}));
      this.aviso.set(this.transloco.translate(claves.exito, { correo: usuario.email }));
      if (accion === 'verificar') {
        await this.cargar();
        if (this.usuarioSeleccionadoId() === usuario.id) await this.seleccionar(usuario.id);
      }
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate(claves.error),
      );
    } finally {
      this.accionEnCurso.set(null);
    }
  }
}
