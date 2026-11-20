import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import type { ProveedorDelCatalogoOut } from '../../../core/api/generated/models';
import { AuthService } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { AvisoClavePropia } from '../../../shared/ui/aviso-clave-propia';
import { Button } from '../../../shared/ui/button';
import { AiCatalogService } from '../ai/ai-catalog.service';
import { AiConfigFields } from '../ai/ai-config-fields';

const AJUSTES = '/organizations/me/ai-settings';

/**
 * Asistente de clave de IA al activar un idioma sin clave propia: pregunta si se
 * quiere traducción automática y, si sí, pide proveedor (OpenRouter, OpenAI,
 * compatible con OpenAI, Anthropic, Gemini…), modelo y clave. Antes de guardar,
 * el servidor traduce de verdad una frase de prueba con ellos
 * (`verify_translation`): si falla, no se guarda nada. Si no, el idioma queda
 * activo para traducir a mano. Solo el propietario configura la clave.
 */
@Component({
  selector: 'app-asistente-clave-traduccion',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, AiConfigFields, AvisoClavePropia, Button],
  template: `
    <ng-container *transloco="let t; prefix: 'admin.organizacion.asistenteClave'">
      @if (!esPropietario()) {
        <app-aviso-clave-propia />
      } @else if (paso() === 'pregunta') {
        <p>{{ t('pregunta') }}</p>
        <p class="nota">{{ t('sinClave') }}</p>
        <div class="acciones">
          <app-button variant="secundario" (pulsado)="descartado.emit()">{{
            t('aMano')
          }}</app-button>
          <app-button (pulsado)="empezar()">{{ t('configurar') }}</app-button>
        </div>
      } @else {
        <form (submit)="guardar($event)" novalidate class="formulario">
          <p class="nota">{{ t('ayuda') }}</p>
          <app-ai-config-fields
            idPrefijo="asistente-clave"
            [catalogo]="catalogo()"
            [(provider)]="provider"
            [(defaultModel)]="defaultModel"
            [(apiBase)]="apiBase"
            [(apiKey)]="apiKey"
          />
          <app-alert tone="info">{{ t('otrasFunciones') }}</app-alert>
          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }
          <div class="acciones">
            <app-button variant="secundario" (pulsado)="descartado.emit()">{{
              t('aMano')
            }}</app-button>
            <app-button type="submit" [loading]="guardando()">{{ t('probarYGuardar') }}</app-button>
          </div>
        </form>
      }
    </ng-container>
  `,
  styles: `
    p {
      margin: 0 0 var(--space-sm);
    }
    .nota {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
    }
    .acciones {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: var(--space-sm);
    }
  `,
})
export class AsistenteClaveTraduccion {
  /** La clave se ha probado y guardado: ya se puede traducir con IA. */
  readonly configurada = output<void>();
  /** Prefiere traducir a mano. */
  readonly descartado = output<void>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly catalogoDeIa = inject(AiCatalogService);
  private readonly auth = inject(AuthService);

  protected readonly esPropietario = computed(() => this.auth.roles()?.includes('owner') ?? false);
  protected readonly paso = signal<'pregunta' | 'clave'>('pregunta');
  protected readonly catalogo = signal<readonly ProveedorDelCatalogoOut[]>([]);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);

  readonly provider = signal('');
  readonly defaultModel = signal('');
  readonly apiBase = signal('');
  readonly apiKey = signal('');

  protected async empezar(): Promise<void> {
    this.paso.set('clave');
    try {
      this.catalogo.set(await this.catalogoDeIa.cargar());
    } catch {
      this.error.set(this.transloco.translate('admin.ia.errorCarga'));
    }
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    const proveedor = this.provider().trim();
    const modelo = this.defaultModel().trim();
    const clave = this.apiKey().trim();
    if (!proveedor || !modelo || !clave) {
      this.error.set(this.transloco.translate('admin.organizacion.asistenteClave.faltanDatos'));
      return;
    }
    const editable =
      this.catalogo().find((entrada) => entrada.clave === proveedor)?.api_base_editable ?? false;
    const cuerpo: Record<string, string | boolean> = {
      provider: proveedor,
      default_model: modelo,
      api_key: clave,
      verify_translation: true,
    };
    if (editable) {
      cuerpo['api_base'] = this.apiBase().trim();
    }
    this.guardando.set(true);
    this.error.set(null);
    try {
      await firstValueFrom(this.http.put(this.api.url(AJUSTES), cuerpo));
      this.apiKey.set('');
      this.configurada.emit();
    } catch (fallo) {
      this.error.set(
        fallo instanceof ApiError
          ? fallo.message
          : this.transloco.translate('admin.organizacion.asistenteClave.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
