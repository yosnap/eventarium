import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { AiUsageOut } from '../../../core/api/generated/models/ai-usage-out';
import { OrganizationAiSettingsOut } from '../../../core/api/generated/models/organization-ai-settings-out';
import { ProveedorDelCatalogoOut } from '../../../core/api/generated/models/proveedor-del-catalogo-out';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { KpiCard } from '../../../shared/ui/kpi-card';
import { PageHeader } from '../../../shared/ui/page-header';
import { RadioGroup } from '../../../shared/ui/radio';
import { AiCatalogService } from '../ai/ai-catalog.service';
import { AiConfigFields } from '../ai/ai-config-fields';
import { AiUsageTables } from '../ai/ai-usage-tables';

const AJUSTES = '/organizations/me/ai-settings';
const USO = '/organizations/me/ai-usage';

/** Qué configuración quiere usar la organización. */
type Modo = 'heredada' | 'propia';

/**
 * Configuración de IA **de la organización**.
 *
 * Por defecto hereda la de la plataforma; puede sobrescribirla con su propio
 * proveedor, modelo, clave y límite de gasto, y volver a heredar borrándola.
 *
 * La autorización la decide el backend, no esta pantalla: la ruta es
 * alcanzable para cualquier miembro, y quien no sea propietario recibe un 403
 * del `GET` y ve el aviso de solo lectura. Calcular aquí quién puede editar
 * sería una segunda fuente de verdad que podría contradecir a la real.
 *
 * En la vista heredada se muestran proveedor, modelo y si hay clave, pero
 * **nunca** la pista de la clave de plataforma: es compartida por toda la
 * instalación (V-11).
 */
@Component({
  selector: 'app-organization-ai-settings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    Alert,
    Button,
    Card,
    KpiCard,
    PageHeader,
    RadioGroup,
    AiConfigFields,
    AiUsageTables,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.ia.organizacion.titulo')">
        {{ t('admin.ia.organizacion.descripcion') }}
      </app-page-header>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (soloLectura()) {
        <app-alert tone="info" [title]="t('admin.ia.organizacion.soloLecturaTitulo')">
          {{ t('admin.ia.organizacion.soloLectura') }}
        </app-alert>
      } @else {
        @if (error(); as mensaje) {
          <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
        }
        @if (guardado()) {
          <app-alert tone="exito" [title]="t('comun.guardado')">
            {{ t('admin.ia.organizacion.guardado') }}
          </app-alert>
        }
        @if (ajustes(); as estado) {
          @if (!estado.servicio_ia_activo) {
            <app-alert tone="info" [title]="t('admin.ia.organizacion.servicioApagadoTitulo')">
              {{ t('admin.ia.organizacion.servicioApagado') }}
            </app-alert>
          }

          <div class="secciones">
            <app-card [heading]="t('admin.ia.organizacion.configuracion')">
              <p class="estado">{{ textoDelOrigen() }}</p>

              <app-radio-group
                nombre="ia-modo"
                [etiqueta]="t('admin.ia.organizacion.modo')"
                [opciones]="opcionesDeModo()"
                [(valor)]="modo"
              />

              @if (modo() === 'heredada') {
                <dl class="heredada">
                  <dt>{{ t('admin.ia.campos.proveedor') }}</dt>
                  <dd>{{ etiquetaDeProveedor(estado.provider) }}</dd>
                  <dt>{{ t('admin.ia.campos.modelo') }}</dt>
                  <dd>{{ estado.default_model ?? '—' }}</dd>
                  <dt>{{ t('admin.ia.campos.clave') }}</dt>
                  <!-- Nunca la pista de la clave de plataforma (V-11): solo si existe. -->
                  <dd>
                    {{
                      estado.has_key
                        ? t('admin.ia.organizacion.claveDePlataforma')
                        : t('admin.ia.organizacion.sinClaveDePlataforma')
                    }}
                  </dd>
                </dl>
                @if (estado.origen === 'propia') {
                  <app-button
                    variant="secundario"
                    [loading]="borrando()"
                    (click)="volverAHeredar()"
                  >
                    {{ t('admin.ia.organizacion.volverAHeredar') }}
                  </app-button>
                }
              } @else {
                <form (submit)="guardar($event)" novalidate class="formulario">
                  <app-ai-config-fields
                    idPrefijo="ia-organizacion"
                    [catalogo]="catalogo()"
                    [hasKey]="estado.origen === 'propia' && estado.has_key"
                    [apiKeyHint]="estado.origen === 'propia' ? estado.api_key_hint : null"
                    [(provider)]="provider"
                    [(defaultModel)]="defaultModel"
                    [(apiBase)]="apiBase"
                    [(apiKey)]="apiKey"
                  />

                  <div class="campo">
                    <label for="ia-organizacion-limite">{{
                      t('admin.ia.organizacion.limite')
                    }}</label>
                    <input
                      id="ia-organizacion-limite"
                      type="text"
                      inputmode="decimal"
                      autocomplete="off"
                      aria-describedby="ia-organizacion-limite-ayuda"
                      [value]="limite()"
                      (input)="limite.set(alTexto($event))"
                    />
                    <p class="ayuda" id="ia-organizacion-limite-ayuda">
                      {{
                        estado.monthly_ceiling_usd
                          ? t('admin.ia.organizacion.limiteAyuda', {
                              techo: estado.monthly_ceiling_usd,
                            })
                          : t('admin.ia.organizacion.limiteSinTecho')
                      }}
                    </p>
                  </div>

                  @if (limiteSobreElTecho()) {
                    <app-alert tone="error" [title]="t('admin.ia.organizacion.limiteAltoTitulo')">
                      {{
                        t('admin.ia.organizacion.limiteAlto', { techo: estado.monthly_ceiling_usd })
                      }}
                    </app-alert>
                  }

                  <app-button type="submit" [loading]="guardando()">
                    {{ t('comun.guardar') }}
                  </app-button>
                </form>
              }
            </app-card>

            <app-card [heading]="t('admin.ia.uso.titulo')">
              @if (uso(); as resumen) {
                <p class="estado">{{ t('admin.ia.uso.periodo', { periodo: resumen.periodo }) }}</p>
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
                      resumen.limite_efectivo_usd
                        ? t('admin.ia.uso.deLimite', { limite: resumen.limite_efectivo_usd })
                        : t('admin.ia.uso.sinLimite')
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
                />
              }
            </app-card>
          </div>
        }
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
      margin-block-start: var(--space-md);
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
    .estado {
      color: var(--muted);
      font-size: var(--fs-sm);
      margin: 0 0 var(--space-md);
    }
    .heredada {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: var(--space-sm) var(--space-md);
      margin: var(--space-md) 0;
    }
    .heredada dt {
      font-weight: 600;
    }
    .heredada dd {
      margin: 0;
    }
    .kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
      gap: var(--space-md);
      margin-block-end: var(--space-md);
    }
  `,
})
export class OrganizationAiSettings {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly catalogoDeIa = inject(AiCatalogService);

  readonly cargando = signal(true);
  readonly guardando = signal(false);
  readonly borrando = signal(false);
  readonly guardado = signal(false);
  readonly error = signal<string | null>(null);
  /** `true` cuando el backend ha respondido 403: quien mira no es propietario. */
  readonly soloLectura = signal(false);

  readonly catalogo = signal<readonly ProveedorDelCatalogoOut[]>([]);
  readonly ajustes = signal<OrganizationAiSettingsOut | null>(null);
  readonly uso = signal<AiUsageOut | null>(null);

  readonly modo = signal<Modo>('heredada');
  readonly provider = signal('');
  readonly defaultModel = signal('');
  readonly apiBase = signal('');
  /** Siempre vacío al cargar: la clave guardada no vuelve nunca al formulario. */
  readonly apiKey = signal('');
  readonly limite = signal('');

  protected readonly opcionesDeModo = computed<readonly { valor: Modo; etiqueta: string }[]>(() => [
    { valor: 'heredada', etiqueta: this.transloco.translate('admin.ia.organizacion.modoHeredada') },
    { valor: 'propia', etiqueta: this.transloco.translate('admin.ia.organizacion.modoPropia') },
  ]);

  protected readonly textoDelOrigen = computed(() => {
    const origen = this.ajustes()?.origen ?? 'sin_configuracion';
    return this.transloco.translate(`admin.ia.organizacion.origen.${origen}`);
  });

  /**
   * Aviso local: el límite propio no puede superar el techo de plataforma. La
   * barrera real es el 422 del backend; esto solo evita el viaje en balde.
   */
  protected readonly limiteSobreElTecho = computed(() => {
    const techo = this.ajustes()?.monthly_ceiling_usd;
    const valor = Number(this.limite().trim());
    if (!techo || !this.limite().trim() || !Number.isFinite(valor)) {
      return false;
    }
    return valor > Number(techo);
  });

  constructor() {
    void this.cargar();
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  protected etiquetaDeProveedor(clave: string | null): string {
    if (!clave) {
      return '—';
    }
    return this.catalogo().find((entrada) => entrada.clave === clave)?.etiqueta ?? clave;
  }

  private async cargar(): Promise<void> {
    try {
      const [catalogo, ajustes, uso] = await Promise.all([
        this.catalogoDeIa.cargar(),
        firstValueFrom(this.http.get<OrganizationAiSettingsOut>(this.api.url(AJUSTES))),
        firstValueFrom(this.http.get<AiUsageOut>(this.api.url(USO))),
      ]);
      this.catalogo.set(catalogo);
      this.uso.set(uso);
      this.volcar(ajustes);
    } catch (fallo) {
      if (fallo instanceof ApiError && fallo.status === 403) {
        this.soloLectura.set(true);
      } else {
        this.error.set(this.mensaje(fallo, 'admin.ia.errorCarga'));
      }
    } finally {
      this.cargando.set(false);
    }
  }

  private volcar(ajustes: OrganizationAiSettingsOut): void {
    this.ajustes.set(ajustes);
    this.modo.set(ajustes.origen === 'propia' ? 'propia' : 'heredada');
    const propia = ajustes.origen === 'propia';
    this.provider.set(propia ? (ajustes.provider ?? '') : '');
    this.defaultModel.set(propia ? (ajustes.default_model ?? '') : '');
    this.apiBase.set(propia && ajustes.api_base_editable ? (ajustes.api_base ?? '') : '');
    this.limite.set(ajustes.monthly_limit_usd ?? '');
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
        await firstValueFrom(
          this.http.put<OrganizationAiSettingsOut>(this.api.url(AJUSTES), cuerpo),
        ),
      );
      await this.recargarUso();
      this.guardado.set(true);
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorGuardar'));
    } finally {
      this.guardando.set(false);
    }
  }

  /** Borra la configuración propia: la organización vuelve a heredar. */
  async volverAHeredar(): Promise<void> {
    this.error.set(null);
    this.guardado.set(false);
    this.borrando.set(true);
    try {
      await firstValueFrom(this.http.delete(this.api.url(AJUSTES)));
      this.volcar(
        await firstValueFrom(this.http.get<OrganizationAiSettingsOut>(this.api.url(AJUSTES))),
      );
      await this.recargarUso();
      this.guardado.set(true);
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.ia.errorGuardar'));
    } finally {
      this.borrando.set(false);
    }
  }

  private async recargarUso(): Promise<void> {
    this.uso.set(await firstValueFrom(this.http.get<AiUsageOut>(this.api.url(USO))));
  }

  /**
   * El cuerpo del `PUT`, o `null` si falta algo que el backend rechazaría.
   *
   * Las reglas de todo-o-nada (V-5) y el techo (422) los vuelve a aplicar el
   * backend: aquí solo se ahorra el viaje. La clave en blanco no se envía, que
   * es lo que conserva la que ya estaba guardada.
   */
  private construirCuerpo(): Record<string, string | null> | null {
    const guardado = this.ajustes();
    const propia = guardado?.origen === 'propia';
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
      proveedor !== (propia ? (guardado?.provider ?? '') : '') ||
      (editable && direccion !== (propia ? (guardado?.api_base ?? '') : ''))
    ) {
      this.error.set(this.transloco.translate('admin.ia.faltaClave'));
      return null;
    } else if (modelo && propia && modelo !== (guardado?.default_model ?? '')) {
      cuerpo['default_model'] = modelo;
    }

    const limite = this.limite().trim();
    if (limite !== (guardado?.monthly_limit_usd ?? '')) {
      if (limite && !Number.isFinite(Number(limite))) {
        this.error.set(this.transloco.translate('admin.ia.importeInvalido'));
        return null;
      }
      if (this.limiteSobreElTecho()) {
        this.error.set(
          this.transloco.translate('admin.ia.organizacion.limiteAlto', {
            techo: guardado?.monthly_ceiling_usd,
          }),
        );
        return null;
      }
      cuerpo['monthly_limit_usd'] = limite === '' ? null : limite;
    }
    return cuerpo;
  }
}
