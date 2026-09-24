import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Chip } from '../../../shared/ui/chip';
import { AMBITOS, type Ambito, McpPermisosSelector } from '../../admin/mcp/mcp-permisos-selector';

interface Solicitud {
  readonly client_id: string;
  readonly client_name: string | null;
  readonly no_verificado: boolean;
  readonly redirect_uri: string;
  readonly organization_name: string;
  readonly ambitos_pedidos: readonly string[];
  readonly ambitos_permitidos: readonly string[];
  readonly ambitos_por_defecto: readonly string[];
}

/**
 * Consentimiento OAuth: un asistente (Claude, ChatGPT, Cursor…) pide
 * conectarse con la cuenta de la persona. Se enseña quién lo pide y adónde
 * volverá — completos, porque el nombre lo pone el propio cliente —, en qué
 * organización actuará, y la persona elige permisos y eventos. `eventos:cancelar`
 * nunca viene marcado. Aprobar o denegar devuelve a la dirección del cliente.
 */
@Component({
  selector: 'app-consentimiento-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Button, Chip, McpPermisosSelector],
  template: `
    <ng-container *transloco="let t; read: 'oauth.consentimiento'">
      <app-auth-frame [titulo]="t('titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (solicitud(); as s) {
          <p class="cliente">
            <strong>{{ s.client_name || t('sinNombre') }}</strong>
            @if (s.no_verificado) {
              <app-chip tone="espera">{{ t('noVerificado') }}</app-chip>
            }
          </p>
          <dl class="datos">
            <dt>{{ t('identificador') }}</dt>
            <dd>
              <code>{{ s.client_id }}</code>
            </dd>
            <dt>{{ t('volveraA') }}</dt>
            <dd>
              <code>{{ s.redirect_uri }}</code>
            </dd>
            <dt>{{ t('organizacion') }}</dt>
            <dd>{{ s.organization_name }}</dd>
          </dl>
          <p>{{ t('explicacion') }}</p>
          @if (pedidos().length) {
            <!-- Los nombres de los ámbitos son los del selector de permisos. -->
            <p *transloco="let ambitoT; read: 'admin.mcp.nueva.ambito'">
              {{ t('pide') }}
              @for (ambito of pedidos(); track ambito; let ultimo = $last) {
                <strong>{{ ambitoT(ambito.replace(':', '_')) }}</strong
                >{{ ultimo ? '.' : ', ' }}
              }
            </p>
          }

          <app-mcp-permisos-selector
            [permitidos]="s.ambitos_permitidos"
            [(marcados)]="marcados"
            [(todosLosEventos)]="todosLosEventos"
            [(eventosElegidos)]="eventosElegidos"
          />

          <div class="acciones">
            <app-button
              type="button"
              [loading]="enviando() === 'aprobar'"
              [disabled]="!valido() || enviando() !== null"
              (pulsado)="responder('aprobar')"
            >
              {{ t('permitir') }}
            </app-button>
            <app-button
              type="button"
              variant="secundario"
              [loading]="enviando() === 'denegar'"
              [disabled]="enviando() !== null"
              (pulsado)="responder('denegar')"
            >
              {{ t('denegar') }}
            </app-button>
          </div>
        } @else if (!error()) {
          <p>{{ t('cargando') }}</p>
        }
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    .cliente {
      display: flex;
      gap: var(--sp-3);
      align-items: center;
      flex-wrap: wrap;
    }
    .datos {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: var(--sp-2) var(--sp-4);
    }
    .datos dt {
      color: var(--muted);
    }
    .datos dd {
      margin: 0;
    }
    code {
      font-family: var(--font-mono);
      word-break: break-all;
    }
    .acciones {
      display: flex;
      gap: var(--sp-3);
      flex-wrap: wrap;
      margin-top: var(--sp-4);
    }
  `,
})
export class ConsentimientoPage implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly transloco = inject(TranslocoService);

  private readonly id = this.ruta.snapshot.queryParamMap.get('solicitud') ?? '';
  protected readonly solicitud = signal<Solicitud | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly enviando = signal<'aprobar' | 'denegar' | null>(null);
  protected readonly marcados = signal<ReadonlySet<Ambito>>(new Set());
  protected readonly todosLosEventos = signal(true);
  protected readonly eventosElegidos = signal<ReadonlySet<string>>(new Set());
  /** Lo que pidió el cliente, para compararlo con lo que se marque. */
  protected readonly pedidos = computed(() => {
    const pedidos = this.solicitud()?.ambitos_pedidos ?? [];
    return AMBITOS.filter((a) => pedidos.includes(a));
  });
  protected readonly valido = computed(
    () => this.marcados().size > 0 && (this.todosLosEventos() || this.eventosElegidos().size > 0),
  );

  ngOnInit(): void {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    if (!this.id) {
      this.error.set(this.transloco.translate('oauth.consentimiento.sinSolicitud'));
      return;
    }
    try {
      const solicitud = await firstValueFrom(
        this.http.get<Solicitud>(this.api.url(`/oauth/solicitudes/${this.id}`)),
      );
      this.marcados.set(new Set(AMBITOS.filter((a) => solicitud.ambitos_por_defecto.includes(a))));
      this.solicitud.set(solicitud);
    } catch (error) {
      this.error.set(
        error instanceof ApiError && error.status === 403
          ? this.transloco.translate('oauth.consentimiento.sinPermiso')
          : this.mensaje(error),
      );
    }
  }

  protected async responder(accion: 'aprobar' | 'denegar'): Promise<void> {
    this.enviando.set(accion);
    this.error.set(null);
    try {
      const cuerpo =
        accion === 'aprobar'
          ? {
              scopes: AMBITOS.filter((a) => this.marcados().has(a)),
              event_ids: this.todosLosEventos() ? null : [...this.eventosElegidos()],
            }
          : {};
      const { redirect_to } = await firstValueFrom(
        this.http.post<{ redirect_to: string }>(
          this.api.url(`/oauth/solicitudes/${this.id}/${accion}`),
          cuerpo,
        ),
      );
      // Salida del sitio a la dirección del cliente (validada en la API al
      // registrarse): navegación completa, no del router. Solo se renderiza
      // en el navegador (`RenderMode.Client`).
      window.location.href = redirect_to;
    } catch (error) {
      this.error.set(this.mensaje(error));
      this.enviando.set(null);
    }
  }

  private mensaje(error: unknown): string {
    return error instanceof ApiError
      ? error.message
      : this.transloco.translate('oauth.consentimiento.error');
  }
}
