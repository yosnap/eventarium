import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { EmailSettingsIn } from '../../../core/api/generated/models/email-settings-in';
import { EmailSettingsOut } from '../../../core/api/generated/models/email-settings-out';
import { EmailTestOut } from '../../../core/api/generated/models/email-test-out';
import { AuthService } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Checkbox } from '../../../shared/ui/checkbox';
import { Input } from '../../../shared/ui/input';
import { PageHeader } from '../../../shared/ui/page-header';
import { Select, type SelectOption } from '../../../shared/ui/select';

const AJUSTES = '/admin/email-settings';
const PRUEBA = '/admin/email-settings/test';

type Proveedor = EmailSettingsIn['provider'];

/**
 * Proveedor de correo **de la plataforma**: con qué servicio salen los
 * correos de la instalación (verificación, recuperación, invitaciones,
 * entradas).
 *
 * Mismo trato de la credencial que la página de IA: el `GET` nunca la
 * devuelve, el campo sale vacío y dejarlo así conserva la guardada. El modo
 * TLS no se elige: lo deriva el backend del puerto (465 implícito, el resto
 * STARTTLS), que es justo la combinación que no se puede equivocar.
 *
 * El correo de prueba va siempre a quien lo pide: así se comprueba el
 * remitente verificado antes de guardar sin que la página sirva de relay.
 */
@Component({
  selector: 'app-email-settings-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Checkbox, Input, PageHeader, Select],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.correo.titulo')">
        {{ t('admin.correo.descripcion') }}
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }
      @if (aviso(); as mensaje) {
        <app-alert tone="exito" [title]="t('comun.guardado')">{{ mensaje }}</app-alert>
      }
      @if (prueba(); as resultado) {
        @if (resultado.ok) {
          <app-alert tone="exito" [title]="t('admin.correo.probar')">
            {{ t('admin.correo.pruebaOk', { correo: resultado.sent_to }) }}
          </app-alert>
        } @else {
          <app-alert tone="error" [title]="t('admin.correo.probar')">
            {{ t('admin.correo.pruebaFallo.' + (resultado.motivo ?? 'error')) }}
          </app-alert>
        }
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (ajustes(); as estado) {
        <app-alert tone="info">
          {{
            estado.source === 'database'
              ? t('admin.correo.origenGuardado')
              : t('admin.correo.origenEntorno')
          }}
        </app-alert>

        <app-card [heading]="t('admin.correo.configuracion')">
          <form (submit)="guardar($event)" novalidate class="formulario">
            <app-select
              fieldId="correo-proveedor"
              [label]="t('admin.correo.proveedor')"
              [options]="opcionesDeProveedor()"
              [value]="provider()"
              (valueChange)="elegirProveedor($any($event))"
            />

            @if (provider() === 'ses') {
              <app-select
                fieldId="correo-region"
                [label]="t('admin.correo.region')"
                [options]="opcionesDeRegion()"
                [(value)]="region"
              />
            }
            @if (provider() === 'custom') {
              <app-input
                fieldId="correo-host"
                [label]="t('admin.correo.host')"
                autocomplete="off"
                [required]="true"
                [(value)]="host"
              />
            } @else if (hostFijo(); as fijo) {
              <p class="dato">
                <span class="dato-rotulo">{{ t('admin.correo.host') }}</span> {{ fijo }}
              </p>
            }

            <app-input
              fieldId="correo-puerto"
              [label]="t('admin.correo.puerto')"
              autocomplete="off"
              inputmode="numeric"
              [hint]="t('admin.correo.puertoAyuda')"
              [(value)]="port"
            />

            @if (usuarioFijo(); as fijo) {
              <p class="dato">
                <span class="dato-rotulo">{{ t('admin.correo.usuario') }}</span> {{ fijo }}
              </p>
            } @else {
              <app-input
                fieldId="correo-usuario"
                [label]="t('admin.correo.usuario')"
                autocomplete="off"
                [required]="true"
                [(value)]="username"
              />
            }

            <app-input
              fieldId="correo-password"
              type="password"
              autocomplete="new-password"
              [label]="
                provider() === 'resend'
                  ? t('admin.correo.passwordResend')
                  : t('admin.correo.password')
              "
              [hint]="ayudaDePassword()"
              [(value)]="password"
            />

            <app-input
              fieldId="correo-remitente"
              type="email"
              autocomplete="off"
              [label]="t('admin.correo.remitente')"
              [hint]="t('admin.correo.remitenteAyuda')"
              [required]="true"
              [(value)]="fromAddress"
            />

            @if (provider() === 'custom' && estado.allow_insecure) {
              <app-checkbox
                fieldId="correo-sin-cifrar"
                [label]="t('admin.correo.sinCifrar')"
                [(checked)]="sinCifrar"
              />
            }

            <p class="ayuda">{{ t('admin.correo.probarAyuda', { correo: miCorreo() }) }}</p>
            <div class="acciones">
              <app-button
                type="button"
                variant="secundario"
                [loading]="probando()"
                (pulsado)="probar()"
              >
                {{ t('admin.correo.probar') }}
              </app-button>
              <app-button type="submit" [loading]="guardando()">{{
                t('comun.guardar')
              }}</app-button>
              @if (estado.source === 'database') {
                <app-button
                  type="button"
                  variant="terciario"
                  [loading]="borrando()"
                  (pulsado)="volverAlEntorno()"
                >
                  {{ t('admin.correo.volverAlEntorno') }}
                </app-button>
              }
            </div>
          </form>
        </app-card>
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-lg);
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      max-width: 38rem;
      min-width: 0;
    }
    .dato {
      margin: 0;
      overflow-wrap: anywhere;
    }
    .dato-rotulo {
      font-weight: 600;
      margin-inline-end: var(--space-sm);
    }
    .ayuda {
      color: var(--muted);
      font-size: var(--fs-sm);
      margin: 0;
      overflow-wrap: anywhere;
    }
    .acciones {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    @media (max-width: 30rem) {
      .acciones > * {
        flex: 1 1 100%;
      }
    }
  `,
})
export class EmailSettingsPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly auth = inject(AuthService);

  readonly cargando = signal(true);
  readonly guardando = signal(false);
  readonly probando = signal(false);
  readonly borrando = signal(false);
  readonly error = signal<string | null>(null);
  readonly aviso = signal<string | null>(null);
  readonly prueba = signal<EmailTestOut | null>(null);
  /** Datos exactos de la última prueba aceptada, para avisar si se guarda otra cosa. */
  private ultimaPruebaOk: string | null = null;

  readonly ajustes = signal<EmailSettingsOut | null>(null);

  readonly provider = signal<Proveedor>('resend');
  readonly host = signal('');
  readonly port = signal('');
  readonly region = signal('');
  readonly username = signal('');
  /** Siempre vacía al cargar: la guardada no vuelve nunca al formulario. */
  readonly password = signal('');
  readonly fromAddress = signal('');
  readonly sinCifrar = signal(false);

  protected readonly miCorreo = computed(() => this.auth.currentUser()?.email ?? '');

  private readonly preset = computed(() =>
    this.ajustes()?.presets.find((p) => p.provider === this.provider()),
  );

  protected readonly hostFijo = computed(() => {
    if (this.provider() === 'ses') {
      return this.region() ? `email-smtp.${this.region()}.amazonaws.com` : null;
    }
    return this.preset()?.host ?? null;
  });

  protected readonly usuarioFijo = computed(() => this.preset()?.username ?? null);

  protected readonly opcionesDeProveedor = computed<SelectOption[]>(() =>
    (this.ajustes()?.presets ?? []).map((p) => ({
      value: p.provider,
      label: this.transloco.translate(`admin.correo.proveedores.${p.provider}`),
    })),
  );

  protected readonly opcionesDeRegion = computed<SelectOption[]>(() =>
    (this.ajustes()?.ses_regions ?? []).map((r) => ({ value: r, label: r })),
  );

  /** La contraseña guardada solo se conserva con el mismo proveedor (lo exige el backend). */
  private readonly conservaPassword = computed(() => {
    const estado = this.ajustes();
    return estado?.source === 'database' && estado.provider === this.provider();
  });

  protected readonly ayudaDePassword = computed(() => {
    if (this.conservaPassword()) {
      return this.transloco.translate('admin.correo.passwordAyudaGuardada', {
        pista: this.ajustes()?.password_hint ?? '',
      });
    }
    return this.provider() === 'ses'
      ? this.transloco.translate('admin.correo.passwordAyudaSes')
      : null;
  });

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      this.volcar(await firstValueFrom(this.http.get<EmailSettingsOut>(this.api.url(AJUSTES))));
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.correo.errorCarga'));
    } finally {
      this.cargando.set(false);
    }
  }

  private volcar(estado: EmailSettingsOut): void {
    this.ajustes.set(estado);
    this.password.set('');
    if (estado.source === 'database' && estado.provider) {
      this.provider.set(estado.provider);
      this.host.set(estado.provider === 'custom' ? (estado.host ?? '') : '');
      this.port.set(String(estado.port ?? ''));
      this.region.set(estado.region ?? '');
      this.username.set(estado.username ?? '');
      this.fromAddress.set(estado.from_address ?? '');
      this.sinCifrar.set(estado.tls_mode === 'none');
    } else {
      this.elegirProveedor('resend');
      this.fromAddress.set(estado.from_address ?? '');
    }
  }

  /** Cambiar de servicio rellena el puerto de su preset; el resto lo decide el preset. */
  protected elegirProveedor(proveedor: Proveedor): void {
    this.provider.set(proveedor);
    const preset = this.ajustes()?.presets.find((p) => p.provider === proveedor);
    this.port.set(String(preset?.port ?? ''));
    this.sinCifrar.set(false);
    if (proveedor === 'ses' && !this.region()) {
      this.region.set('eu-west-1');
    }
  }

  private mensaje(fallo: unknown, claveDeRespaldo: string): string {
    return fallo instanceof ApiError ? fallo.message : this.transloco.translate(claveDeRespaldo);
  }

  /** El cuerpo común de probar y guardar, o `null` si falta algo evidente. */
  private construirCuerpo(): EmailSettingsIn | null {
    const puerto = Number(this.port().trim());
    if (!Number.isInteger(puerto) || puerto <= 0) {
      this.error.set(this.transloco.translate('admin.correo.puertoInvalido'));
      return null;
    }
    const proveedor = this.provider();
    const remitente = this.fromAddress().trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(remitente)) {
      this.error.set(this.transloco.translate('admin.correo.remitenteInvalido'));
      return null;
    }
    if (proveedor === 'custom' && !this.host().trim()) {
      this.error.set(this.transloco.translate('admin.correo.faltaHost'));
      return null;
    }
    if (!this.usuarioFijo() && !this.username().trim()) {
      this.error.set(this.transloco.translate('admin.correo.faltaUsuario'));
      return null;
    }
    const password = this.password().trim();
    if (!password && !this.conservaPassword()) {
      this.error.set(this.transloco.translate('admin.correo.faltaPassword'));
      return null;
    }
    return {
      provider: proveedor,
      port: puerto,
      from_address: remitente,
      host: proveedor === 'custom' ? this.host().trim() : null,
      region: proveedor === 'ses' ? this.region() : null,
      username: this.usuarioFijo() ? null : this.username().trim(),
      password: password || null,
      tls_mode: proveedor === 'custom' && this.sinCifrar() ? 'none' : null,
    };
  }

  private reiniciarMensajes(): void {
    this.error.set(null);
    this.aviso.set(null);
    this.prueba.set(null);
  }

  async probar(): Promise<void> {
    this.reiniciarMensajes();
    const cuerpo = this.construirCuerpo();
    if (cuerpo === null) {
      return;
    }
    this.probando.set(true);
    try {
      const resultado = await firstValueFrom(
        this.http.post<EmailTestOut>(this.api.url(PRUEBA), cuerpo),
      );
      this.prueba.set(resultado);
      this.ultimaPruebaOk = resultado.ok ? JSON.stringify(cuerpo) : null;
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.correo.errorPrueba'));
    } finally {
      this.probando.set(false);
    }
  }

  async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.reiniciarMensajes();
    const cuerpo = this.construirCuerpo();
    if (cuerpo === null) {
      return;
    }
    this.guardando.set(true);
    try {
      this.volcar(
        await firstValueFrom(this.http.put<EmailSettingsOut>(this.api.url(AJUSTES), cuerpo)),
      );
      const probado = this.ultimaPruebaOk === JSON.stringify(cuerpo);
      this.aviso.set(
        this.transloco.translate(
          probado ? 'admin.correo.guardado' : 'admin.correo.guardadoSinProbar',
        ),
      );
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.correo.errorGuardar'));
    } finally {
      this.guardando.set(false);
    }
  }

  async volverAlEntorno(): Promise<void> {
    this.reiniciarMensajes();
    this.borrando.set(true);
    try {
      await firstValueFrom(this.http.delete<void>(this.api.url(AJUSTES)));
      this.volcar(await firstValueFrom(this.http.get<EmailSettingsOut>(this.api.url(AJUSTES))));
      this.aviso.set(this.transloco.translate('admin.correo.vueltoAlEntorno'));
    } catch (fallo) {
      this.error.set(this.mensaje(fallo, 'admin.correo.errorGuardar'));
    } finally {
      this.borrando.set(false);
    }
  }
}
