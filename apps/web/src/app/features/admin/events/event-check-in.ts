import { DatePipe, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  type OnDestroy,
  type OnInit,
  PLATFORM_ID,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import jsQR from 'jsqr';

import { ApiError } from '../../../core/api/error.interceptor';
import {
  OfflineScanQueueService,
  type QueuedScan,
} from '../../../core/tickets/offline-scan-queue.service';
import {
  type ScanInput,
  type TicketScanResult,
  type TicketScanResultOut,
  type TicketSearchItem,
  TicketsService,
} from '../../../core/tickets/tickets.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';

/** Estado de un resultado en la lista visible — `pending` no existe en la API,
 * es el estado óptimista mientras el escaneo espera a sincronizarse. */
type ResultadoUiEstado = TicketScanResult | 'pending';

interface ResultadoUi {
  readonly clientScanId: string;
  readonly result: ResultadoUiEstado;
  readonly fullName: string | null;
  readonly email: string | null;
  readonly usedAt: string | null;
  readonly usedByEventMemberId: string | null;
}

// Tope de la lista visible: es un feed en vivo, no un histórico — mantener
// solo lo reciente evita que el DOM crezca sin límite en una jornada larga.
const LIMITE_RESULTADOS_VISIBLES = 30;
// Dos detecciones del mismo texto dentro de esta ventana cuentan como el
// mismo escaneo (el código sigue en el encuadre de la cámara), no dos.
const VENTANA_DEDUPLICACION_MS = 4000;
const INTERVALO_REINTENTO_MS = 15000;
// Frecuencia real de decodificación, no de dibujado: 5/s detecta un QR quieto
// frente a la cámara de sobra y evita quemar batería decodificando en cada
// vuelta de `requestAnimationFrame` (hasta 60 veces por segundo).
const INTERVALO_DECODIFICACION_MS = 200;

const ICONOS: Record<ResultadoUiEstado, string> = {
  valid: '✓',
  manual: '✓',
  pending: '…',
  duplicate: '⚠',
  revoked: '⛔',
  expired: '⏰',
  invalid_signature: '✕',
  not_found: '✕',
};

function generarId(): string {
  return crypto.randomUUID();
}

/**
 * App de escaneo y check-in (fase 4 del PRD, fase 3 de trabajo).
 *
 * Cámara + `BarcodeDetector` nativo con `jsqr` de respaldo (decisión #10 del
 * plan), cola offline en IndexedDB que sincroniza sola (decisión #11),
 * búsqueda manual como respaldo real y un contador en vivo.
 */
@Component({
  selector: 'app-event-check-in',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, DatePipe, Alert, Button, Card, Input],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.checkIn.titulo')">
        <p class="contador" role="status">
          {{
            t('admin.events.checkIn.contador', {
              escaneados: escaneados(),
              total: totalConfirmados() ?? '—',
            })
          }}
        </p>
        @if (pendientesEnCola() > 0) {
          <p role="status">
            {{ t('admin.events.checkIn.pendientesDeSincronizar', { n: pendientesEnCola() }) }}
          </p>
        }

        <div class="camara">
          <video #video muted playsinline [hidden]="!!camaraError()"></video>
          @if (camaraError(); as mensaje) {
            <app-alert tone="info">{{ mensaje }}</app-alert>
          }
        </div>

        <h3>{{ t('admin.events.checkIn.resultadosTitulo') }}</h3>
        @if (resultados().length === 0) {
          <p>{{ t('admin.events.checkIn.sinResultados') }}</p>
        } @else {
          <ul class="resultados" aria-live="polite">
            @for (item of resultados(); track item.clientScanId) {
              <li [class]="'estado-' + item.result">
                <span class="icono" aria-hidden="true">{{ icono(item.result) }}</span>
                <span class="texto">
                  <strong>{{ t('admin.events.checkIn.resultado.' + item.result) }}</strong>
                  @if (item.fullName || item.email) {
                    <span> — {{ item.fullName }} ({{ item.email }})</span>
                  }
                  @if ((item.result === 'duplicate' || item.result === 'revoked') && item.usedAt) {
                    <span class="detalle">
                      {{
                        t('admin.events.checkIn.usadaEl', {
                          fecha: item.usedAt | date: 'short',
                        })
                      }}
                      @if (item.usedByEventMemberId) {
                        {{ t('admin.events.checkIn.porMiembro', { id: item.usedByEventMemberId }) }}
                      }
                    </span>
                  }
                </span>
              </li>
            }
          </ul>
        }

        <h3>{{ t('admin.events.checkIn.busqueda.titulo') }}</h3>
        <form (submit)="alBuscar($event)">
          <app-input
            [label]="t('admin.events.checkIn.busqueda.campo')"
            [value]="busqueda()"
            (valueChange)="busqueda.set($event)"
          />
          <app-button type="submit" [loading]="buscando()">
            {{ t('admin.events.checkIn.busqueda.boton') }}
          </app-button>
        </form>
        @if (busquedaError(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (resultadosBusqueda().length > 0) {
          <ul class="busqueda-resultados">
            @for (fila of resultadosBusqueda(); track fila.ticket_id) {
              <li>
                <span>{{ fila.full_name }} ({{ fila.email }})</span>
                @if (fila.used_at) {
                  <span class="detalle">
                    {{
                      t('admin.events.checkIn.busqueda.yaUsada', {
                        fecha: fila.used_at | date: 'short',
                      })
                    }}
                  </span>
                } @else {
                  <app-button
                    type="button"
                    variant="secundario"
                    [loading]="accionManualPendiente() === fila.ticket_id"
                    (pulsado)="marcarManual(fila.ticket_id)"
                  >
                    {{ t('admin.events.checkIn.busqueda.marcar') }}
                  </app-button>
                }
              </li>
            }
          </ul>
        } @else if (busquedaRealizada()) {
          <p>{{ t('admin.events.checkIn.busqueda.sinResultados') }}</p>
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    .contador {
      font-weight: 600;
      font-size: 1.125rem;
    }
    .camara video {
      width: 100%;
      max-width: 28rem;
      border-radius: var(--radius-md);
      background-color: #000;
    }
    .resultados,
    .busqueda-resultados {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-sm);
      max-height: 24rem;
      overflow-y: auto;
    }
    .resultados li,
    .busqueda-resultados li {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      padding: var(--space-sm);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
    }
    .icono {
      font-size: 1.25rem;
    }
    .detalle {
      display: block;
      font-size: 0.875rem;
      color: var(--color-text-muted, #6b7280);
    }
    .estado-valid,
    .estado-manual {
      border-color: var(--color-success);
    }
    .estado-duplicate,
    .estado-revoked,
    .estado-expired,
    .estado-invalid_signature,
    .estado-not_found {
      border-color: var(--color-danger);
    }
    form {
      display: flex;
      gap: var(--space-sm);
      align-items: flex-end;
      flex-wrap: wrap;
    }
  `,
})
export class EventCheckIn implements OnInit, OnDestroy {
  readonly eventId = input.required<string>();

  private readonly tickets = inject(TicketsService);
  private readonly cola = inject(OfflineScanQueueService);
  private readonly transloco = inject(TranslocoService);
  private readonly esNavegador = isPlatformBrowser(inject(PLATFORM_ID));

  private readonly videoRef = viewChild<ElementRef<HTMLVideoElement>>('video');

  protected readonly escaneados = signal(0);
  protected readonly totalConfirmados = signal<number | null>(null);
  protected readonly resultados = signal<ResultadoUi[]>([]);
  protected readonly pendientesEnCola = signal(0);
  protected readonly camaraError = signal<string | null>(null);

  protected readonly busqueda = signal('');
  protected readonly busquedaRealizada = signal(false);
  protected readonly buscando = signal(false);
  protected readonly busquedaError = signal<string | null>(null);
  protected readonly resultadosBusqueda = signal<TicketSearchItem[]>([]);
  protected readonly accionManualPendiente = signal<string | null>(null);

  private detector: BarcodeDetector | null = null;
  private stream: MediaStream | null = null;
  private bucleActivo = false;
  private frameId: number | null = null;
  private intervaloReintento: ReturnType<typeof setInterval> | null = null;
  private ultimoTokenDetectado: string | null = null;
  private ultimoTimestampDeteccion = 0;
  private sincronizando = false;
  private readonly alRecuperarConexion = (): void => void this.sincronizar();
  private urlDelManifiesto: string | null = null;

  ngOnInit(): void {
    void this.cargarEstadisticas();
    if (!this.esNavegador) {
      // SSR: sin cámara, sin IndexedDB, sin `window` — la página solo tiene
      // sentido ya hidratada en el navegador (es una PWA de escaneo).
      return;
    }
    this.instalarManifiestoDinamico();
    void this.actualizarPendientes();
    void this.iniciarCamara();
    window.addEventListener('online', this.alRecuperarConexion);
    this.intervaloReintento = setInterval(() => void this.sincronizar(), INTERVALO_REINTENTO_MS);
    // Sin esto, unos escaneos que quedaron en la cola de una sesión anterior
    // (recarga o cierre con la sincronización a medias) no se reintentan
    // hasta la primera vuelta del intervalo (hasta 15s) o el próximo
    // evento `online`.
    void this.sincronizar();
  }

  ngOnDestroy(): void {
    if (!this.esNavegador) {
      return;
    }
    this.bucleActivo = false;
    if (this.frameId !== null) {
      cancelAnimationFrame(this.frameId);
    }
    this.stream?.getTracks().forEach((pista) => pista.stop());
    if (this.intervaloReintento !== null) {
      clearInterval(this.intervaloReintento);
    }
    window.removeEventListener('online', this.alRecuperarConexion);
    if (this.urlDelManifiesto) {
      URL.revokeObjectURL(this.urlDelManifiesto);
      // No basta con revocar el blob: sin quitar el `<link>` del `<head>`,
      // el SPA lo deja apuntando a una URL ya revocada al navegar a otra
      // ruta (esta página no recarga el documento entero).
      document.head.querySelector('link[rel="manifest"]')?.remove();
    }
  }

  /**
   * Manifest propio de esta ruta (decisión del plan): se genera en memoria
   * con el `start_url` del evento activo, en vez de un fichero estático que
   * no podría saber qué evento se está escaneando ahora mismo.
   */
  private instalarManifiestoDinamico(): void {
    const manifiesto = {
      name: 'IA Week — Check-in',
      short_name: 'Check-in',
      description: 'Escaneo de entradas y control de acceso',
      start_url: `/admin/events/${this.eventId()}/check-in`,
      display: 'standalone',
      background_color: '#111827',
      theme_color: '#111827',
      icons: [{ src: '/favicon.ico', sizes: '48x48', type: 'image/x-icon' }],
    };
    const blob = new Blob([JSON.stringify(manifiesto)], { type: 'application/manifest+json' });
    this.urlDelManifiesto = URL.createObjectURL(blob);

    let enlace = document.head.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (!enlace) {
      enlace = document.createElement('link');
      enlace.rel = 'manifest';
      document.head.appendChild(enlace);
    }
    enlace.href = this.urlDelManifiesto;
  }

  protected icono(result: ResultadoUiEstado): string {
    return ICONOS[result];
  }

  private async cargarEstadisticas(): Promise<void> {
    try {
      this.totalConfirmados.set(await this.tickets.getConfirmedCount(this.eventId()));
    } catch {
      // El contador es informativo; si falla, se deja en «—» sin bloquear el escaneo.
    }
  }

  private async actualizarPendientes(): Promise<void> {
    this.pendientesEnCola.set((await this.cola.pending()).length);
  }

  // --- Cámara y decodificación --------------------------------------------

  private async iniciarCamara(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      this.camaraError.set(this.transloco.translate('admin.events.checkIn.sinCamara'));
      return;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
    } catch {
      this.camaraError.set(this.transloco.translate('admin.events.checkIn.sinCamara'));
      return;
    }
    const video = this.videoRef()?.nativeElement;
    if (!video) {
      return;
    }
    video.srcObject = this.stream;
    await video.play().catch(() => undefined);

    try {
      this.detector = window.BarcodeDetector
        ? new window.BarcodeDetector({ formats: ['qr_code'] })
        : null;
    } catch {
      // El constructor puede lanzar si el navegador anuncia `BarcodeDetector`
      // pero no soporta el formato pedido — sin este `catch`, la promesa de
      // `iniciarCamara()` (llamada con `void`) rechaza antes de activar el
      // bucle, y la cámara se queda mostrando vídeo sin escanear nunca.
      this.detector = null;
    }
    this.bucleActivo = true;
    this.programarSiguienteFrame();
  }

  private programarSiguienteFrame(): void {
    if (!this.bucleActivo) {
      return;
    }
    this.frameId = requestAnimationFrame(() => void this.procesarFrame());
  }

  private ultimaDecodificacion = 0;

  private async procesarFrame(): Promise<void> {
    const ahora = performance.now();
    // El vídeo se sigue pintando a la frecuencia nativa de `requestAnimationFrame`;
    // solo la decodificación (la parte cara) se limita a
    // `INTERVALO_DECODIFICACION_MS` para no quemar batería de sobra.
    if (ahora - this.ultimaDecodificacion >= INTERVALO_DECODIFICACION_MS) {
      this.ultimaDecodificacion = ahora;
      const video = this.videoRef()?.nativeElement;
      const detector = this.detector;
      if (video && video.readyState >= video.HAVE_CURRENT_DATA && video.videoWidth > 0) {
        const texto = detector
          ? await this.detectarConBarcodeDetector(detector, video)
          : this.detectarConJsQr(video);
        if (texto) {
          this.alDetectarCodigo(texto);
        }
      }
    }
    this.programarSiguienteFrame();
  }

  private async detectarConBarcodeDetector(
    detector: BarcodeDetector,
    video: HTMLVideoElement,
  ): Promise<string | null> {
    try {
      const codigos = await detector.detect(video);
      return codigos[0]?.rawValue ?? null;
    } catch {
      return null;
    }
  }

  private lienzo: HTMLCanvasElement | null = null;

  private detectarConJsQr(video: HTMLVideoElement): string | null {
    this.lienzo ??= document.createElement('canvas');
    this.lienzo.width = video.videoWidth;
    this.lienzo.height = video.videoHeight;
    const contexto = this.lienzo.getContext('2d', { willReadFrequently: true });
    if (!contexto) {
      return null;
    }
    contexto.drawImage(video, 0, 0, this.lienzo.width, this.lienzo.height);
    const imagen = contexto.getImageData(0, 0, this.lienzo.width, this.lienzo.height);
    const codigo = jsQR(imagen.data, imagen.width, imagen.height);
    return codigo?.data ?? null;
  }

  private alDetectarCodigo(token: string): void {
    const ahora = Date.now();
    if (
      token === this.ultimoTokenDetectado &&
      ahora - this.ultimoTimestampDeteccion < VENTANA_DEDUPLICACION_MS
    ) {
      return;
    }
    this.ultimoTokenDetectado = token;
    this.ultimoTimestampDeteccion = ahora;
    void this.encolarEscaneo(token);
  }

  // --- Cola offline y sincronización ---------------------------------------

  /** `protected`, no `private`: los tests simulan una detección real llamando
   * directamente aquí, ya que `getUserMedia`/`BarcodeDetector` no existen en
   * el entorno de pruebas (jsdom). */
  protected async encolarEscaneo(token: string): Promise<void> {
    const escaneo: QueuedScan = {
      clientScanId: generarId(),
      token,
      clientScannedAt: new Date().toISOString(),
      deviceLabel: null,
    };
    this.agregarResultadoPendiente(escaneo.clientScanId);
    await this.cola.enqueue(escaneo);
    await this.actualizarPendientes();
    // Óptimista (decisión del plan): no se espera aquí, el bucle de la
    // cámara ya invoca `encolarEscaneo` sin esperar y sigue escaneando.
    void this.sincronizar();
  }

  private agregarResultadoPendiente(clientScanId: string): void {
    this.resultados.update((actuales) =>
      [
        {
          clientScanId,
          result: 'pending' as const,
          fullName: null,
          email: null,
          usedAt: null,
          usedByEventMemberId: null,
        },
        ...actuales,
      ].slice(0, LIMITE_RESULTADOS_VISIBLES),
    );
  }

  private actualizarResultado(resultado: TicketScanResultOut): void {
    const item: ResultadoUi = {
      clientScanId: resultado.client_scan_id,
      result: resultado.result,
      fullName: resultado.full_name,
      email: resultado.email,
      usedAt: resultado.used_at,
      usedByEventMemberId: resultado.used_by_event_member_id,
    };
    this.resultados.update((actuales) => {
      const indice = actuales.findIndex((fila) => fila.clientScanId === item.clientScanId);
      if (indice === -1) {
        return [item, ...actuales].slice(0, LIMITE_RESULTADOS_VISIBLES);
      }
      const copia = [...actuales];
      copia[indice] = item;
      return copia;
    });
    if (resultado.result === 'valid' || resultado.result === 'manual') {
      this.escaneados.update((n) => n + 1);
    }
  }

  private async sincronizar(): Promise<void> {
    if (this.sincronizando || navigator.onLine === false) {
      return;
    }
    this.sincronizando = true;
    try {
      const pendientes = await this.cola.pending();
      if (pendientes.length === 0) {
        return;
      }
      const escaneos: ScanInput[] = pendientes.map((pendiente) => ({
        token: pendiente.token,
        clientScanId: pendiente.clientScanId,
        clientScannedAt: pendiente.clientScannedAt,
        deviceLabel: pendiente.deviceLabel,
      }));
      const resultados = await this.tickets.scanBatch(this.eventId(), escaneos);
      for (const resultado of resultados) {
        await this.cola.remove(resultado.client_scan_id);
        this.actualizarResultado(resultado);
      }
    } catch {
      // Se reintenta al siguiente evento `online` o en el próximo intervalo
      // corto (decisión del plan: sin backoff exponencial complejo).
    } finally {
      this.sincronizando = false;
      await this.actualizarPendientes();
    }
  }

  // --- Búsqueda manual ------------------------------------------------------

  protected alBuscar(evento: SubmitEvent): void {
    evento.preventDefault();
    void this.buscar();
  }

  private async buscar(): Promise<void> {
    const q = this.busqueda().trim();
    this.busquedaError.set(null);
    if (!q) {
      this.resultadosBusqueda.set([]);
      this.busquedaRealizada.set(false);
      return;
    }
    this.buscando.set(true);
    try {
      const resultados = await this.tickets.search(this.eventId(), q);
      this.resultadosBusqueda.set(resultados);
      this.busquedaRealizada.set(true);
    } catch (error) {
      this.busquedaError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.checkIn.busqueda.error'),
      );
    } finally {
      this.buscando.set(false);
    }
  }

  protected async marcarManual(ticketId: string): Promise<void> {
    this.accionManualPendiente.set(ticketId);
    this.busquedaError.set(null);
    try {
      const resultado = await this.tickets.checkInManual(this.eventId(), ticketId);
      this.actualizarResultado(resultado);
      this.resultadosBusqueda.update((filas) =>
        filas.map((fila) =>
          fila.ticket_id === ticketId ? { ...fila, used_at: resultado.used_at } : fila,
        ),
      );
    } catch (error) {
      this.busquedaError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.checkIn.busqueda.error'),
      );
    } finally {
      this.accionManualPendiente.set(null);
    }
  }
}
