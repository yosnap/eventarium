import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  type OnInit,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { fechaRelativa } from '../../../shared/text/fecha-relativa';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Panel } from '../../../shared/ui/panel';
import {
  ERRORES_DE_CONFIGURACION,
  ERROR_REINTENTABLE,
  type ErrorDeExtraccion,
  MOTOR_PENDIENTE,
  type ReceiptDraft,
} from './accounting-types';
import type { PartidaParaGasto } from './expense-form';
import { ReceiptReviewForm } from './receipt-review-form';
import { ReceiptUpload } from './receipt-upload';

/**
 * Esperas del *polling* de la extracción, en milisegundos. Retroceso con tope:
 * la extracción tarda segundos, pero puede tardar minutos si la cola va
 * cargada, y preguntar cada dos segundos para siempre machacaría el API sin
 * enterarse antes de nada.
 */
const ESPERAS_MS = [2000, 4000, 8000, 16000, 30000] as const;

/** Los `error_code` que esta pantalla sabe traducir uno a uno. Cualquier otro
 * cae en el mensaje genérico en vez de enseñar un código crudo. */
const ERRORES_CONOCIDOS: readonly ErrorDeExtraccion[] = [
  'servicio_desactivado',
  'sin_configuracion',
  'limite_superado',
  'credencial_ilegible',
  'proveedor_error',
  'modelo_sin_vision',
  'clave_rechazada',
  'payload_invalido',
  'reserva_abandonada',
];

/**
 * Bandeja de justificantes de un evento: la subida, la espera de la extracción
 * y la revisión de cada borrador.
 *
 * Es el dueño del estado asíncrono —el listado y su *polling* con retroceso—,
 * y por eso monta también la subida: quien sube es quien tiene que ver el
 * borrador aparecer, y hacerlo pasar por la pantalla de arriba solo añadiría
 * un salto más sin dueño claro.
 *
 * El *polling* arranca solo si hay algún borrador en `pending_extraction`, para
 * y reinicia su retroceso cuando no queda ninguno, y se cancela al destruir el
 * componente: un temporizador huérfano seguiría pidiendo listados de una
 * pantalla que ya no existe.
 */
@Component({
  selector: 'app-receipt-drafts-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TranslocoDirective, Alert, Button, Panel, ReceiptReviewForm, ReceiptUpload],
  template: `
    <ng-container *transloco="let t">
      <app-panel>
        <div cabecera>
          <span class="rotulo-seccion">{{
            t('admin.events.accounting.justificantes.titulo')
          }}</span>
        </div>

        <div class="panel-cuerpo cuerpo">
          <p class="explicacion">
            {{ t('admin.events.accounting.justificantes.explicacion') }}
          </p>

          <app-receipt-upload [eventId]="eventId()" (subido)="alSubir($event)" />

          <p class="sr-only" aria-live="polite">{{ estadoDeBandeja() }}</p>
          <p role="status" aria-live="polite" class="aviso">{{ avisoDeAccion() }}</p>

          @if (error(); as mensaje) {
            <app-alert tone="error">
              {{ mensaje }}
              <app-button variant="secundario" type="button" (pulsado)="recargar()">
                {{ t('admin.events.accounting.justificantes.bandeja.actualizar') }}
              </app-button>
            </app-alert>
          }

          @if (cargando()) {
            <p>{{ t('admin.events.accounting.justificantes.bandeja.cargando') }}</p>
          } @else if (drafts().length === 0) {
            <p>{{ t('admin.events.accounting.justificantes.bandeja.vacia') }}</p>
          }

          @if (extrayendo().length > 0) {
            <section class="grupo">
              <h3>
                {{
                  t('admin.events.accounting.justificantes.bandeja.extrayendo', {
                    n: extrayendo().length,
                  })
                }}
              </h3>
              <ul class="lista">
                @for (draft of extrayendo(); track draft.id) {
                  <li>
                    <span>{{
                      t('admin.events.accounting.justificantes.bandeja.leyendoEsteJustificante')
                    }}</span>
                    <span class="meta">{{ motor(draft) }}</span>
                    <span class="meta">{{
                      t('admin.events.accounting.justificantes.bandeja.subidoEl', {
                        fecha: fechaRelativa(draft.created_at),
                      })
                    }}</span>
                  </li>
                }
              </ul>
            </section>
          }

          @if (fallidos().length > 0) {
            <section class="grupo">
              <h3>
                {{
                  t('admin.events.accounting.justificantes.bandeja.fallidos', {
                    n: fallidos().length,
                  })
                }}
              </h3>
              @if (reintentables().length > 1) {
                <app-button variant="secundario" type="button" (pulsado)="reintentarTodos()">
                  {{ t('admin.events.accounting.justificantes.bandeja.reintentarTodos') }}
                </app-button>
              }
              <ul class="lista">
                @for (draft of fallidos(); track draft.id) {
                  <li>
                    <span>{{ mensajeDelError(draft.error_code) }}</span>
                    <span class="meta">{{ motor(draft) }}</span>
                    <span class="meta">{{
                      t('admin.events.accounting.justificantes.bandeja.subidoEl', {
                        fecha: fechaRelativa(draft.created_at),
                      })
                    }}</span>
                    <span class="acciones">
                      @if (esReintentable(draft)) {
                        <app-button
                          variant="secundario"
                          type="button"
                          (pulsado)="reintentar(draft)"
                        >
                          {{ t('admin.events.accounting.justificantes.errores.reintentar') }}
                        </app-button>
                      }
                      @if (esDeConfiguracion(draft)) {
                        <a routerLink="/dashboard/ia">{{
                          t('admin.events.accounting.justificantes.errores.irAConfiguracionDeIa')
                        }}</a>
                      }
                    </span>
                  </li>
                }
              </ul>
            </section>
          }

          @if (pendientes().length > 0) {
            <section class="grupo">
              <h3>
                {{
                  t('admin.events.accounting.justificantes.bandeja.pendientes', {
                    n: pendientes().length,
                  })
                }}
              </h3>
              @for (draft of pendientes(); track draft.id) {
                <article class="borrador">
                  <p class="meta">{{ motor(draft) }}</p>
                  <app-receipt-review-form
                    [draft]="draft"
                    [partidas]="partidas()"
                    [enfocar]="draft.id === draftAEnfocar()"
                    (confirmado)="alConfirmar(draft, $event)"
                    (descartado)="alDescartar(draft, $event)"
                  />
                </article>
              }
            </section>
          }
        </div>
      </app-panel>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .cuerpo {
      display: grid;
      gap: var(--space-md);
    }
    .explicacion {
      margin: 0;
      color: var(--muted);
    }
    .aviso:empty {
      display: none;
    }
    .grupo {
      display: grid;
      gap: var(--space-sm);
    }
    .grupo h3 {
      margin: 0;
      font-size: var(--fs-label, 0.875rem);
    }
    .lista {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-sm);
    }
    .lista li {
      display: grid;
      gap: var(--space-xs);
      padding: var(--space-sm);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
    }
    .meta {
      color: var(--muted);
      font-size: 0.8125rem;
    }
    .acciones {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-sm);
    }
    .borrador {
      display: grid;
      gap: var(--space-sm);
      padding: var(--space-md);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
  `,
})
export class ReceiptDraftsPanel implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly destroyRef = inject(DestroyRef);

  readonly eventId = input.required<string>();
  /** Las mismas partidas que recibe el alta manual: no se vuelve a cargar el
   * presupuesto para esto. */
  readonly partidas = input.required<readonly PartidaParaGasto[]>();

  /** Un borrador confirmado es un gasto nuevo: la pantalla de contabilidad
   * recarga sus cifras, igual que hace con el alta manual. */
  readonly gastoCreado = output<string>();

  protected readonly drafts = signal<readonly ReceiptDraft[]>([]);
  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly avisoDeAccion = signal('');
  protected readonly draftAEnfocar = signal<string | null>(null);

  protected readonly fechaRelativa = fechaRelativa;

  private temporizador: ReturnType<typeof setTimeout> | null = null;
  private pasoDeEspera = 0;
  /** Cancelar el temporizador al destruir no basta: una petición de listado en
   * vuelo resuelve después y programaría la siguiente contra un componente que
   * ya no existe. */
  private destruido = false;

  protected readonly extrayendo = computed(() =>
    this.drafts().filter((d) => d.status === 'pending_extraction' || d.status === 'en_extraccion'),
  );
  protected readonly pendientes = computed(() =>
    this.drafts().filter((d) => d.status === 'pending_review'),
  );
  protected readonly fallidos = computed(() =>
    this.drafts().filter((d) => d.status === 'extraction_failed'),
  );
  protected readonly reintentables = computed(() =>
    this.fallidos().filter((d) => d.error_code === ERROR_REINTENTABLE),
  );

  /** Lo que anuncia la región `aria-live` de la bandeja. */
  protected readonly estadoDeBandeja = computed(() => {
    const base = 'admin.events.accounting.justificantes.bandeja.';
    const extrayendo = this.extrayendo().length;
    if (extrayendo > 0) {
      return this.plural(base, 'extrayendoAviso', extrayendo);
    }
    const pendientes = this.pendientes().length;
    if (pendientes > 0) {
      return this.plural(base, 'listoAviso', pendientes);
    }
    const fallidos = this.fallidos().length;
    return fallidos > 0 ? this.plural(base, 'falloAviso', fallidos) : '';
  });

  private plural(base: string, clave: string, n: number): string {
    return n === 1
      ? this.transloco.translate(`${base}${clave}Uno`)
      : this.transloco.translate(`${base}${clave}`, { n });
  }

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.destruido = true;
      this.cancelarTemporizador();
    });
  }

  ngOnInit(): void {
    void this.cargar();
  }

  protected motor(draft: ReceiptDraft): string {
    const base = 'admin.events.accounting.justificantes.bandeja.';
    return draft.ocr_provider === MOTOR_PENDIENTE
      ? this.transloco.translate(`${base}motorPendiente`)
      : this.transloco.translate(`${base}motor`, { motor: draft.ocr_provider });
  }

  /** Mensaje propio por `error_code`; el genérico solo para lo que no está en
   * la taxonomía. */
  protected mensajeDelError(codigo: string | null): string {
    const base = 'admin.events.accounting.justificantes.errores.';
    const conocido = ERRORES_CONOCIDOS.find((error) => error === codigo);
    return this.transloco.translate(conocido ? `${base}${conocido}` : `${base}generico`);
  }

  /** Solo `limite_superado`: repetir la llamada con cualquier otro código
   * daría exactamente el mismo resultado, y el backend lo rechaza con 422. */
  protected esReintentable(draft: ReceiptDraft): boolean {
    return draft.error_code === ERROR_REINTENTABLE;
  }

  protected esDeConfiguracion(draft: ReceiptDraft): boolean {
    return ERRORES_DE_CONFIGURACION.some((error) => error === draft.error_code);
  }

  // --- Listado y polling ------------------------------------------------------

  protected async recargar(): Promise<void> {
    this.cancelarTemporizador();
    this.pasoDeEspera = 0;
    await this.cargar();
  }

  private async cargar(): Promise<void> {
    this.error.set(null);
    try {
      const listado = await firstValueFrom(
        this.http.get<ReceiptDraft[]>(
          this.api.url(`/accounting/events/${this.eventId()}/expense-drafts`),
        ),
      );
      if (this.destruido) {
        return;
      }
      this.aplicarListado(listado);
      this.programarSiguienteConsulta();
    } catch (error) {
      if (this.destruido) {
        return;
      }
      // Se deja de preguntar: con el listado fallando, seguir con el
      // retroceso solo acumularía errores. Queda el botón de actualizar.
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.accounting.justificantes.bandeja.errorCarga'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicarListado(listado: readonly ReceiptDraft[]): void {
    const anteriores = new Map(this.drafts().map((draft) => [draft.id, draft.status]));
    // Los confirmados ya son un gasto y los descartados no existen: la bandeja
    // es lo que queda por hacer, no un histórico.
    const vivos = listado.filter(
      (draft) =>
        draft.status === 'pending_extraction' ||
        draft.status === 'en_extraccion' ||
        draft.status === 'pending_review' ||
        draft.status === 'extraction_failed',
    );
    const recienListo = vivos.find(
      (draft) =>
        draft.status === 'pending_review' &&
        (anteriores.get(draft.id) === 'pending_extraction' ||
          anteriores.get(draft.id) === 'en_extraccion'),
    );
    this.drafts.set(vivos);
    if (recienListo) {
      this.draftAEnfocar.set(recienListo.id);
    }
  }

  private programarSiguienteConsulta(): void {
    this.cancelarTemporizador();
    if (this.destruido) {
      return;
    }
    if (this.extrayendo().length === 0) {
      this.pasoDeEspera = 0;
      return;
    }
    const espera = ESPERAS_MS[Math.min(this.pasoDeEspera, ESPERAS_MS.length - 1)];
    this.pasoDeEspera += 1;
    this.temporizador = setTimeout(() => void this.cargar(), espera);
  }

  private cancelarTemporizador(): void {
    if (this.temporizador !== null) {
      clearTimeout(this.temporizador);
      this.temporizador = null;
    }
  }

  // --- Acciones ---------------------------------------------------------------

  protected alSubir(draft: ReceiptDraft): void {
    this.avisoDeAccion.set(
      this.transloco.translate('admin.events.accounting.justificantes.subida.subido'),
    );
    // El borrador recién creado entra ya en la bandeja: la pantalla refleja
    // «extrayendo» sin esperar al siguiente listado.
    this.drafts.set([draft, ...this.drafts()]);
    this.pasoDeEspera = 0;
    this.programarSiguienteConsulta();
  }

  protected async reintentar(draft: ReceiptDraft): Promise<void> {
    this.error.set(null);
    const fallo = await this.pedirReintento(draft);
    if (fallo === null) {
      await this.recargar();
      return;
    }
    this.error.set(fallo);
  }

  /** Todos los reintentos y **una sola** recarga al final: recargar el listado
   * entre borrador y borrador duplicaría las peticiones sin enseñar nada que
   * no se vea igual al terminar. */
  protected async reintentarTodos(): Promise<void> {
    this.error.set(null);
    let alguno = false;
    let fallo: string | null = null;
    for (const draft of this.reintentables()) {
      const error = await this.pedirReintento(draft);
      if (error === null) {
        alguno = true;
      } else {
        fallo ??= error;
      }
    }
    if (alguno) {
      await this.recargar();
    }
    // Después de la recarga: `cargar()` limpia el error al empezar, y el fallo
    // de un reintento tiene que seguir viéndose.
    if (fallo !== null) {
      this.error.set(fallo);
    }
  }

  /** Reencola la extracción de un borrador. Devuelve `null` si fue bien, o el
   * mensaje de error si no; nunca recarga el listado. */
  private async pedirReintento(draft: ReceiptDraft): Promise<string | null> {
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/accounting/expense-drafts/${draft.id}/retry`), {}),
      );
      this.avisoDeAccion.set(
        this.transloco.translate('admin.events.accounting.justificantes.bandeja.reintentando'),
      );
      return null;
    } catch (error) {
      return error instanceof ApiError
        ? error.message
        : this.transloco.translate('admin.events.accounting.error');
    }
  }

  protected alConfirmar(draft: ReceiptDraft, aviso: string): void {
    this.olvidar(draft);
    this.gastoCreado.emit(aviso);
  }

  protected alDescartar(draft: ReceiptDraft, aviso: string): void {
    this.olvidar(draft);
    this.avisoDeAccion.set(aviso);
  }

  /** Un borrador confirmado o descartado sale de la bandeja sin volver a
   * pedir el listado: ya se sabe que no está, y el servidor acaba de
   * confirmarlo en la respuesta de la acción. */
  private olvidar(draft: ReceiptDraft): void {
    if (this.draftAEnfocar() === draft.id) {
      this.draftAEnfocar.set(null);
    }
    this.drafts.set(this.drafts().filter((otro) => otro.id !== draft.id));
  }
}
