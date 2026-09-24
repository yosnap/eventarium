import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  type OnInit,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { formatearPrecio } from '../../../shared/text/formatear-precio';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Dialog } from '../../../shared/ui/dialog';
import { Textarea } from '../../../shared/ui/textarea';

interface Resumen {
  readonly inscripciones_afectadas: number;
  readonly pagos_a_reembolsar: number;
  readonly importe_a_reembolsar_cents: number;
  readonly moneda: string | null;
  readonly requiere_permiso_de_pagos: boolean;
}

interface Progreso {
  readonly por_cancelar: number;
  readonly por_avisar: number;
  readonly reembolsos_fallidos: number;
}

const INTERVALO_PROGRESO_MS = 3000;
/** Fallos seguidos al leer el progreso antes de dejar de intentarlo. */
const FALLOS_MAXIMOS = 3;

/**
 * Cancelar un evento publicado (definitivo) y seguir su progreso.
 *
 * Dos pasos, como exige la API: primero se pide el resumen (a cuántas
 * personas afecta y cuánto se reembolsa) y el diálogo lo enseña; al
 * confirmar se envían esas mismas cifras. Si han cambiado entre medias, la
 * API responde 409 y se vuelve a pedir el resumen.
 *
 * Con el evento ya cancelado muestra el progreso del barrido en segundo
 * plano y los reembolsos que hayan agotado sus reintentos.
 */
@Component({
  selector: 'app-event-cancel-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Dialog, Textarea],
  template: `
    <ng-container *transloco="let t; read: 'admin.events.cancelar'">
      <app-card [heading]="t('titulo')">
        @if (cancelado()) {
          @if (progreso(); as p) {
            @if (p.por_cancelar > 0 || p.por_avisar > 0) {
              <p aria-live="polite">
                {{ t('enCurso', { cancelar: p.por_cancelar, avisar: p.por_avisar }) }}
              </p>
            } @else {
              <p aria-live="polite">{{ t('completada') }}</p>
            }
            @if (p.reembolsos_fallidos > 0) {
              <app-alert tone="error">
                {{ t('reembolsosFallidos', { n: p.reembolsos_fallidos }) }}
              </app-alert>
            }
          }
        } @else {
          <p>{{ t('explicacion') }}</p>
          <app-button
            type="button"
            variant="peligro"
            [loading]="cargandoResumen()"
            (pulsado)="abrirResumen()"
          >
            {{ t('boton') }}
          </app-button>
        }
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
      </app-card>

      <app-dialog #dialogo>
        <h3>{{ t('dialogoTitulo') }}</h3>
        @if (resumen(); as r) {
          <p>{{ t('afectadas', { n: r.inscripciones_afectadas }) }}</p>
          @if (r.pagos_a_reembolsar > 0) {
            <p>
              {{
                t('reembolsos', {
                  n: r.pagos_a_reembolsar,
                  importe: importe(r),
                })
              }}
            </p>
          }
          <p>{{ t('definitivo') }}</p>
          <app-textarea [label]="t('motivo')" [hint]="t('motivoAyuda')" [(value)]="motivo" />
        }
        @if (errorDialogo(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        <app-button pie variant="secundario" type="button" (pulsado)="dialogo.cerrar()">
          {{ t('volver') }}
        </app-button>
        <app-button
          pie
          variant="peligro"
          type="button"
          [loading]="cancelando()"
          (pulsado)="confirmar()"
        >
          {{ t('confirmar') }}
        </app-button>
      </app-dialog>
    </ng-container>
  `,
})
export class EventCancelCard implements OnInit {
  readonly eventId = input.required<string>();
  /** Estado inicial: `true` si el evento ya estaba cancelado al cargar. */
  readonly yaCancelado = input(false);
  readonly cancelacionConfirmada = output<void>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly dialogoRef = viewChild.required<Dialog>('dialogo');

  protected readonly resumen = signal<Resumen | null>(null);
  protected readonly progreso = signal<Progreso | null>(null);
  protected readonly motivo = signal('');
  protected readonly cargandoResumen = signal(false);
  protected readonly cancelando = signal(false);
  protected readonly cancelado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errorDialogo = signal<string | null>(null);

  private temporizador: ReturnType<typeof setInterval> | null = null;
  private fallosSeguidos = 0;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.pararSeguimiento());
  }

  ngOnInit(): void {
    if (this.yaCancelado()) {
      this.cancelado.set(true);
      this.seguirProgreso();
    }
  }

  protected importe(r: Resumen): string {
    return formatearPrecio(r.importe_a_reembolsar_cents, r.moneda ?? 'eur');
  }

  protected async abrirResumen(): Promise<void> {
    this.error.set(null);
    this.errorDialogo.set(null);
    this.cargandoResumen.set(true);
    try {
      this.resumen.set(
        await firstValueFrom(
          this.http.get<Resumen>(this.api.url(`/events/${this.eventId()}/cancel/preview`)),
        ),
      );
      this.dialogoRef().abrir();
    } catch (error) {
      this.error.set(this.mensaje(error));
    } finally {
      this.cargandoResumen.set(false);
    }
  }

  protected async confirmar(): Promise<void> {
    const resumen = this.resumen();
    if (!resumen) return;
    this.cancelando.set(true);
    this.errorDialogo.set(null);
    try {
      this.progreso.set(
        await firstValueFrom(
          this.http.post<Progreso>(this.api.url(`/events/${this.eventId()}/cancel`), {
            motivo: this.motivo().trim() || null,
            inscripciones_afectadas: resumen.inscripciones_afectadas,
            importe_a_reembolsar_cents: resumen.importe_a_reembolsar_cents,
          }),
        ),
      );
      this.cancelado.set(true);
      this.dialogoRef().cerrar();
      this.cancelacionConfirmada.emit();
      this.seguirProgreso();
    } catch (error) {
      // 409: las cifras cambiaron desde el resumen. Se vuelve a pedir para
      // que la persona confirme sobre datos actuales.
      if (error instanceof ApiError && error.status === 409) {
        try {
          this.resumen.set(
            await firstValueFrom(
              this.http.get<Resumen>(this.api.url(`/events/${this.eventId()}/cancel/preview`)),
            ),
          );
        } catch {
          // Si tampoco se puede releer, basta con el mensaje del 409.
        }
      }
      this.errorDialogo.set(this.mensaje(error));
    } finally {
      this.cancelando.set(false);
    }
  }

  private seguirProgreso(): void {
    void this.leerProgreso();
    this.temporizador = setInterval(() => void this.leerProgreso(), INTERVALO_PROGRESO_MS);
  }

  private async leerProgreso(): Promise<void> {
    try {
      const progreso = await firstValueFrom(
        this.http.get<Progreso>(this.api.url(`/events/${this.eventId()}/cancel/progress`)),
      );
      this.fallosSeguidos = 0;
      this.error.set(null);
      this.progreso.set(progreso);
      if (progreso.por_cancelar === 0 && progreso.por_avisar === 0) {
        this.pararSeguimiento();
      }
    } catch (error) {
      // Un corte puntual no detiene el seguimiento; varios seguidos sí, y se dice.
      this.fallosSeguidos++;
      if (this.fallosSeguidos >= FALLOS_MAXIMOS) {
        this.pararSeguimiento();
        this.error.set(this.mensaje(error));
      }
    }
  }

  private pararSeguimiento(): void {
    if (this.temporizador !== null) {
      clearInterval(this.temporizador);
      this.temporizador = null;
    }
  }

  private mensaje(error: unknown): string {
    return error instanceof ApiError
      ? error.message
      : this.transloco.translate('admin.events.formulario.error');
  }
}
