import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { PlatformAiSettingsOut } from '../../../core/api/generated/models/platform-ai-settings-out';
import { PlatformAiUsageOut } from '../../../core/api/generated/models/platform-ai-usage-out';
import { ProveedorDelCatalogoOut } from '../../../core/api/generated/models/proveedor-del-catalogo-out';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { KpiCard } from '../../../shared/ui/kpi-card';
import { PageHeader } from '../../../shared/ui/page-header';
import { AiCatalogService } from '../ai/ai-catalog.service';
import { AiConfigFields } from '../ai/ai-config-fields';
import { AiUsageTables } from '../ai/ai-usage-tables';

const AJUSTES = '/admin/ai-settings';
const USO = '/admin/ai-usage';

/**
 * Configuración de IA **de la plataforma**: el proveedor, el modelo y la clave
 * que usan por defecto todas las organizaciones que no tengan la suya, más el
 * techo de gasto de la instalación y el gasto agregado del mes.
 *
 * La clave es de escritura: el `GET` nunca la devuelve y el campo sale siempre
 * vacío, ni siquiera enmascarado. Dejarlo en blanco al guardar conserva la que
 * había; escribir una la sustituye.
 */
@Component({
  selector: 'app-ai-settings-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    Alert,
    Button,
    Card,
    KpiCard,
    PageHeader,
    AiConfigFields,
    AiUsageTables,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.ia.plataforma.titulo')">
        {{ t('admin.ia.plataforma.descripcion') }}
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }
      @if (guardado()) {
        <app-alert tone="exito" [title]="t('comun.guardado')">
          {{ t('admin.ia.plataforma.guardado') }}
        </app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <div class="secciones">
          <app-card [heading]="t('admin.ia.plataforma.configuracion')">
            <form (submit)="guardar($event)" novalidate class="formulario">
              <app-ai-config-fields
                idPrefijo="ia-plataforma"
                [catalogo]="catalogo()"
                [hasKey]="ajustes()?.has_key ?? false"
                [apiKeyHint]="ajustes()?.api_key_hint ?? null"
                [(provider)]="provider"
                [(defaultModel)]="defaultModel"
                [(apiBase)]="apiBase"
                [(apiKey)]="apiKey"
              />

              <div class="campo">
                <label for="ia-plataforma-techo">{{ t('admin.ia.plataforma.techo') }}</label>
                <input
                  id="ia-plataforma-techo"
                  type="text"
                  inputmode="decimal"
                  autocomplete="off"
                  aria-describedby="ia-plataforma-techo-ayuda"
                  [value]="techo()"
                  (input)="techo.set(alTexto($event))"
                />
                <p class="ayuda" id="ia-plataforma-techo-ayuda">
                  {{ t('admin.ia.plataforma.techoAyuda') }}
                </p>
              </div>

              <app-button type="submit" [loading]="guardando()">{{
                t('comun.guardar')
              }}</app-button>
            </form>
          </app-card>

          <app-card [heading]="t('admin.ia.uso.titulo')">
            @if (uso(); as resumen) {
              <p class="periodo">{{ t('admin.ia.uso.periodo', { periodo: resumen.periodo }) }}</p>
              <div class="kpis">
                <app-kpi-card
                  [rotulo]="t('admin.ia.uso.llamadas')"
                  [valor]="resumen.llamadas + ''"
                  [descriptor]="t('admin.ia.uso.fallidas', { veces: resumen.llamadas_fallidas })"
                />
                <app-kpi-card
                  [rotulo]="t('admin.ia.uso.gasto')"
                  [valor]="'$' + resumen.gasto_usd"
                  [descriptor]="
                    resumen.monthly_ceiling_usd
                      ? t('admin.ia.uso.deTecho', { techo: resumen.monthly_ceiling_usd })
                      : t('admin.ia.uso.sinTecho')
                  "
                />
                <app-kpi-card
                  [rotulo]="t('admin.ia.uso.tokens')"
                  [valor]="resumen.input_tokens + resumen.output_tokens + ''"
                  [descriptor]="
                    t('admin.ia.uso.tokensDetalle', {
                      entrada: resumen.input_tokens,
                      salida: resumen.output_tokens,
                    })
                  "
                />
              </div>
              @if (!resumen.gasto_auditable) {
                <app-alert tone="info" [title]="t('admin.ia.avisos.costeNoAuditableTitulo')">
                  {{ t('admin.ia.uso.totalOrientativo') }}
                </app-alert>
              }
              <app-ai-usage-tables
                [registros]="resumen.ultimos"
                [errores]="resumen.ultimos_errores"
                [conOrganizacion]="true"
              />
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
    .formulario {
      display: grid;
      gap: var(--space-md);
      max-width: 38rem;
    }
    .campo {
      display: grid;
      gap: var(--space-sm);
    }
    label {
      font-weight: 600;
    }
    input {
      box-sizing: border-box;
      width: 100%;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
      color: var(--fg);
      font: inherit;
      min-height: 2.75rem;
    }
    input:focus-visible {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent);
    }
    .ayuda,
    .periodo {
      color: var(--muted);
      font-size: var(--fs-sm);
      margin: 0 0 var(--space-md);
    }
    .kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
      gap: var(--space-md);
      margin-block-end: var(--space-md);
    }
  `,
})
export class AiSettingsPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly catalogoDeIa = inject(AiCatalogService);

  readonly cargando = signal(true);
  readonly guardando = signal(false);
  readonly guardado = signal(false);
  readonly error = signal<string | null>(null);

  readonly catalogo = signal<readonly ProveedorDelCatalogoOut[]>([]);
  readonly ajustes = signal<PlatformAiSettingsOut | null>(null);
  readonly uso = signal<PlatformAiUsageOut | null>(null);

  readonly provider = signal('');
  readonly defaultModel = signal('');
  readonly apiBase = signal('');
  /** Siempre vacío al cargar: la clave guardada no vuelve nunca al formulario. */
  readonly apiKey = signal('');
  readonly techo = signal('');

  constructor() {
    void this.cargar();
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  private async cargar(): Promise<void> {
    try {
      const [catalogo, ajustes, uso] = await Promise.all([
        this.catalogoDeIa.cargar(),
        firstValueFrom(this.http.get<PlatformAiSettingsOut>(this.api.url(AJUSTES))),
        firstValueFrom(this.http.get<PlatformAiUsageOut>(this.api.url(USO))),
      ]);
      this.catalogo.set(catalogo);
      this.uso.set(uso);
      this.volcar(ajustes);
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorCarga'));
    } finally {
      this.cargando.set(false);
    }
  }

  private volcar(ajustes: PlatformAiSettingsOut): void {
    this.ajustes.set(ajustes);
    this.provider.set(ajustes.provider ?? '');
    this.defaultModel.set(ajustes.default_model ?? '');
    this.apiBase.set(ajustes.api_base_editable ? (ajustes.api_base ?? '') : '');
    this.techo.set(ajustes.monthly_ceiling_usd ?? '');
    this.apiKey.set('');
  }

  private mensaje(fallo: unknown, claveDeRespaldo: string): string {
    return fallo instanceof ApiError ? fallo.message : this.transloco.translate(claveDeRespaldo);
  }

  async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    this.guardado.set(false);

    const cuerpo = this.construirCuerpo();
    if (cuerpo === null) {
      return;
    }
    if (Object.keys(cuerpo).length === 0) {
      this.error.set(this.transloco.translate('admin.ia.sinCambios'));
      return;
    }

    this.guardando.set(true);
    try {
      this.volcar(
        await firstValueFrom(this.http.put<PlatformAiSettingsOut>(this.api.url(AJUSTES), cuerpo)),
      );
      this.uso.set(await firstValueFrom(this.http.get<PlatformAiUsageOut>(this.api.url(USO))));
      this.guardado.set(true);
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorGuardar'));
    } finally {
      this.guardando.set(false);
    }
  }

  /**
   * El cuerpo del `PUT`, o `null` si falta algo que el backend rechazaría.
   *
   * Las reglas de todo-o-nada son del backend (V-5) y él las vuelve a aplicar:
   * aquí solo se evita el viaje de ida y vuelta cuando ya se sabe que falta la
   * clave. La clave en blanco **no** se envía: eso es lo que conserva la que
   * ya estaba guardada.
   */
  private construirCuerpo(): Record<string, string | null> | null {
    const guardado = this.ajustes();
    const clave = this.apiKey().trim();
    const proveedor = this.provider().trim();
    const modelo = this.defaultModel().trim();
    const direccion = this.apiBase().trim();
    const editable =
      this.catalogo().find((entrada) => entrada.clave === proveedor)?.api_base_editable ?? false;
    const cuerpo: Record<string, string | null> = {};

    if (clave) {
      if (!proveedor || !modelo) {
        this.error.set(this.transloco.translate('admin.ia.faltaProveedorOModelo'));
        return null;
      }
      cuerpo['provider'] = proveedor;
      cuerpo['default_model'] = modelo;
      cuerpo['api_key'] = clave;
      if (editable) {
        cuerpo['api_base'] = direccion;
      }
    } else if (
      proveedor !== (guardado?.provider ?? '') ||
      (editable && direccion !== (guardado?.api_base ?? ''))
    ) {
      this.error.set(this.transloco.translate('admin.ia.faltaClave'));
      return null;
    } else if (modelo && modelo !== (guardado?.default_model ?? '')) {
      cuerpo['default_model'] = modelo;
    }

    const techo = this.techo().trim();
    if (techo !== (guardado?.monthly_ceiling_usd ?? '')) {
      if (techo && !Number.isFinite(Number(techo))) {
        this.error.set(this.transloco.translate('admin.ia.importeInvalido'));
        return null;
      }
      cuerpo['monthly_ceiling_usd'] = techo === '' ? null : techo;
    }
    return cuerpo;
  }
}
