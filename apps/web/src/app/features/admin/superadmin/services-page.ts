import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { OrganizationResponse } from '../../../core/api/generated/models/organization-response';
import { OrganizationServiceOut } from '../../../core/api/generated/models/organization-service-out';
import { ServiceOut } from '../../../core/api/generated/models/service-out';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { PageHeader } from '../../../shared/ui/page-header';
import { Select, type SelectOption } from '../../../shared/ui/select';
import { Toggle } from '../../../shared/ui/toggle';

const SERVICIOS = '/admin/services';
const ORGANIZACIONES = '/admin/organizations';

/**
 * Interruptores de servicio de la instalación.
 *
 * Dos niveles, con una asimetría deliberada (V-7/V-8): el interruptor global
 * apaga o enciende un servicio para todo el mundo, y el de una organización
 * concreta **solo puede apagar**. Un servicio apagado globalmente no se
 * reactiva por organización, y por eso ese segundo interruptor aparece
 * bloqueado mientras el global esté apagado. Ambos los escribe solo el admin:
 * el organizador no tiene ningún endpoint de servicios.
 */
@Component({
  selector: 'app-services-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Card, PageHeader, Select, Toggle],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.ia.servicios.titulo')">
        {{ t('admin.ia.servicios.descripcion') }}
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <div class="secciones">
          <app-card [heading]="t('admin.ia.servicios.globales')">
            <div class="interruptores">
              @for (servicio of globales(); track servicio.service_key) {
                <app-toggle
                  [fieldId]="'servicio-global-' + servicio.service_key"
                  [label]="servicio.etiqueta"
                  [hint]="servicio.descripcion"
                  [estado]="
                    servicio.enabled
                      ? t('admin.ia.servicios.activo')
                      : t('admin.ia.servicios.apagado')
                  "
                  [checked]="servicio.enabled"
                  [disabled]="guardando()"
                  (checkedChange)="cambiarGlobal(servicio.service_key, $event)"
                />
              }
            </div>
          </app-card>

          <app-card [heading]="t('admin.ia.servicios.porOrganizacion')">
            <p class="ayuda">{{ t('admin.ia.servicios.porOrganizacionAyuda') }}</p>
            <app-select
              fieldId="servicios-organizacion"
              [label]="t('admin.ia.servicios.organizacion')"
              [placeholder]="t('admin.ia.servicios.elegirOrganizacion')"
              [options]="opcionesDeOrganizacion()"
              [value]="organizacionId()"
              (valueChange)="elegirOrganizacion($event)"
            />

            @if (organizacionId()) {
              <div class="interruptores">
                @for (servicio of deLaOrganizacion(); track servicio.service_key) {
                  <app-toggle
                    [fieldId]="'servicio-org-' + servicio.service_key"
                    [label]="servicio.etiqueta"
                    [hint]="
                      servicio.global_enabled
                        ? t('admin.ia.servicios.overrideAyuda')
                        : t('admin.ia.servicios.apagadoGlobalmente')
                    "
                    [estado]="
                      servicio.enabled
                        ? t('admin.ia.servicios.heredado')
                        : t('admin.ia.servicios.forzadoOff')
                    "
                    [checked]="!servicio.overridden_off"
                    [disabled]="guardando() || !servicio.global_enabled"
                    (checkedChange)="cambiarDeLaOrganizacion(servicio.service_key, $event)"
                  />
                }
              </div>
            }
          </app-card>
        </div>
      }
    </ng-container>
  `,
  styles: `
    .secciones {
      display: grid;
      gap: var(--space-lg);
    }
    .interruptores {
      display: grid;
      gap: var(--space-md);
      margin-block-start: var(--space-md);
    }
    .ayuda {
      color: var(--muted);
      font-size: var(--fs-sm);
      margin: 0 0 var(--space-md);
    }
  `,
})
export class ServicesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  readonly cargando = signal(true);
  readonly guardando = signal(false);
  readonly error = signal<string | null>(null);

  readonly globales = signal<readonly ServiceOut[]>([]);
  readonly organizaciones = signal<readonly OrganizationResponse[]>([]);
  readonly organizacionId = signal('');
  readonly deLaOrganizacion = signal<readonly OrganizationServiceOut[]>([]);

  protected readonly opcionesDeOrganizacion = computed<SelectOption[]>(() =>
    this.organizaciones().map((organizacion) => ({
      value: organizacion.id,
      label: organizacion.name,
    })),
  );

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const [servicios, organizaciones] = await Promise.all([
        firstValueFrom(this.http.get<ServiceOut[]>(this.api.url(SERVICIOS))),
        firstValueFrom(this.http.get<OrganizationResponse[]>(this.api.url(ORGANIZACIONES))),
      ]);
      this.globales.set(servicios);
      this.organizaciones.set(organizaciones);
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorCarga'));
    } finally {
      this.cargando.set(false);
    }
  }

  private mensaje(fallo: unknown, claveDeRespaldo: string): string {
    return fallo instanceof ApiError ? fallo.message : this.transloco.translate(claveDeRespaldo);
  }

  async elegirOrganizacion(organizationId: string): Promise<void> {
    this.organizacionId.set(organizationId);
    await this.cargarServiciosDeLaOrganizacion(organizationId);
  }

  private async cargarServiciosDeLaOrganizacion(organizationId: string): Promise<void> {
    this.deLaOrganizacion.set([]);
    if (!organizationId) {
      return;
    }
    this.error.set(null);
    try {
      this.deLaOrganizacion.set(
        await firstValueFrom(
          this.http.get<OrganizationServiceOut[]>(
            this.api.url(`${ORGANIZACIONES}/${organizationId}/services`),
          ),
        ),
      );
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorCarga'));
    }
  }

  async cambiarGlobal(serviceKey: string, enabled: boolean): Promise<void> {
    this.error.set(null);
    this.guardando.set(true);
    try {
      this.globales.set(
        await firstValueFrom(
          this.http.put<ServiceOut[]>(this.api.url(SERVICIOS), {
            services: [{ service_key: serviceKey, enabled }],
          }),
        ),
      );
      // Apagar el global cambia lo que puede hacer el interruptor por
      // organización: hay que releerlo, no deducirlo aquí.
      if (this.organizacionId()) {
        await this.cargarServiciosDeLaOrganizacion(this.organizacionId());
      }
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorGuardar'));
      await this.cargar();
    } finally {
      this.guardando.set(false);
    }
  }

  /**
   * `enabled=false` fuerza el servicio a apagado para esa organización;
   * `enabled=true` borra el override y vuelve a heredar — nunca enciende por
   * encima de una decisión global de apagado (lo garantiza el backend).
   */
  async cambiarDeLaOrganizacion(serviceKey: string, enabled: boolean): Promise<void> {
    const organizationId = this.organizacionId();
    if (!organizationId) {
      return;
    }
    this.error.set(null);
    this.guardando.set(true);
    try {
      this.deLaOrganizacion.set(
        await firstValueFrom(
          this.http.put<OrganizationServiceOut[]>(
            this.api.url(`${ORGANIZACIONES}/${organizationId}/services`),
            { services: [{ service_key: serviceKey, enabled }] },
          ),
        ),
      );
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorGuardar'));
      await this.cargarServiciosDeLaOrganizacion(organizationId);
    } finally {
      this.guardando.set(false);
    }
  }
}
