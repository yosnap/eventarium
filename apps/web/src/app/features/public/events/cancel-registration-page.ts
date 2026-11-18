import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  PLATFORM_ID,
  type ElementRef,
  computed,
  inject,
  signal,
  viewChild,
  LOCALE_ID,
} from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { seoDePagina } from '../../../core/seo/meta.service';
import {
  RegistrationsService,
  type VistaPreviaCancelacion,
} from '../../../core/registrations/registrations.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { formatearFecha } from '../../../shared/text/formatear-fecha';

type Estado = 'comprobando' | 'listo' | 'ya-cancelada' | 'empezado' | 'exito' | 'error';

/**
 * Cancelación por el enlace del correo, en dos pasos: primero enseña qué se
 * cancela (sin gastar el token) y solo el clic de confirmación cancela. Así
 * un clic por error, o el escáner de enlaces del correo, no cancela la plaza.
 */
@Component({
  selector: 'app-cancel-registration-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Button, Card, Reveal],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('cancelarInscripcion.titulo')">
        <div class="envoltura" appReveal>
          <app-card [heading]="t('cancelarInscripcion.titulo')">
            <div aria-live="polite" tabindex="-1" #resultado class="resultado">
              @switch (estado()) {
                @case ('comprobando') {
                  <app-alert tone="info">{{ t('cancelarInscripcion.comprobando') }}</app-alert>
                }
                @case ('listo') {
                  <div class="confirmar">
                    <p>
                      {{ t('cancelarInscripcion.pregunta') }}
                      <strong>{{ vista()?.event_title }}</strong>
                      <span class="fecha">{{ fecha() }}</span>
                    </p>
                    @if (vista()?.status === 'confirmed') {
                      <p>{{ t('cancelarInscripcion.plaza') }}</p>
                    }
                    @if (vista()?.refund === 'en_curso') {
                      <app-alert tone="info">{{ t('cancelarInscripcion.conReembolso') }}</app-alert>
                    } @else if (vista()?.refund === 'sin_reembolso') {
                      <app-alert tone="info">{{ t('cancelarInscripcion.sinReembolso') }}</app-alert>
                    }
                    <app-button variant="peligro" [loading]="cancelando()" (pulsado)="confirmar()">
                      {{ t('cancelarInscripcion.confirmar') }}
                    </app-button>
                  </div>
                }
                @case ('ya-cancelada') {
                  <app-alert tone="info">{{
                    vista()?.status === 'rejected'
                      ? t('cancelarInscripcion.noActiva')
                      : t('cancelarInscripcion.yaCancelada')
                  }}</app-alert>
                }
                @case ('empezado') {
                  <app-alert tone="info" [title]="t('cancelarInscripcion.empezadoTitulo')">
                    {{ t('cancelarInscripcion.empezadoDetalle') }}
                  </app-alert>
                }
                @case ('exito') {
                  <app-alert tone="exito" [title]="t('cancelarInscripcion.exitoTitulo')">
                    {{ mensaje() }}
                  </app-alert>
                }
                @case ('error') {
                  <app-alert tone="error" [title]="t('cancelarInscripcion.errorTitulo')">
                    {{ t('cancelarInscripcion.errorDetalle') }}
                  </app-alert>
                }
              }
            </div>
          </app-card>
        </div>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    .envoltura {
      width: min(26rem, 100%);
    }
    .resultado:focus {
      outline: none;
    }
    .confirmar {
      display: grid;
      gap: var(--space-md);
    }
    .confirmar p {
      margin: 0;
    }
    .fecha {
      display: block;
      color: var(--muted);
    }
  `,
})
export class CancelRegistrationPage {
  /** Idioma de la visita, para fechas e importes. */
  private readonly idioma = inject(LOCALE_ID);
  private readonly seo = seoDePagina();
  private readonly transloco = inject(TranslocoService);
  private readonly registrations = inject(RegistrationsService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly enNavegador = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly token = this.ruta.snapshot.queryParamMap.get('token');

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly mensaje = signal('');
  protected readonly vista = signal<VistaPreviaCancelacion | null>(null);
  protected readonly cancelando = signal(false);
  private readonly resultado = viewChild<ElementRef<HTMLElement>>('resultado');

  /** En la zona horaria del evento, que es la que la persona tiene en su entrada. */
  protected readonly fecha = computed(() => {
    const vista = this.vista();
    if (!vista) return '';
    return formatearFecha(vista.starts_at, this.idioma, {
      dateStyle: 'full',
      timeStyle: 'short',
      timeZone: vista.timezone,
    });
  });

  constructor() {
    // La URL lleva un token: que ningún buscador la guarde.
    this.seo.set({
      title: this.transloco.translate('cancelarInscripcion.titulo'),
      noIndexar: true,
    });
    if (!this.token) {
      this.estado.set('error');
      return;
    }
    // La vista previa no gasta el token, pero se pide solo en el navegador:
    // el servidor pinta «comprobando» y la hidratación no la repite.
    if (this.enNavegador) {
      void this.cargar(this.token);
    }
  }

  private async cargar(token: string): Promise<void> {
    try {
      const vista = await this.registrations.previewCancel(token);
      this.vista.set(vista);
      if (vista.status === 'cancelled' || vista.status === 'rejected') {
        this.estado.set('ya-cancelada');
      } else if (vista.already_started) {
        this.estado.set('empezado');
      } else {
        this.estado.set('listo');
      }
    } catch {
      this.estado.set('error');
    }
  }

  protected async confirmar(): Promise<void> {
    if (!this.token || this.cancelando()) return;
    this.cancelando.set(true);
    try {
      const resultado = await this.registrations.cancel(this.token);
      this.mensaje.set(resultado.message);
      this.estado.set('exito');
    } catch (error) {
      this.estado.set(error instanceof ApiError && error.status === 409 ? 'empezado' : 'error');
    } finally {
      this.cancelando.set(false);
    }
    // El botón desaparece con el resultado: el foco pasa al aviso para que
    // quien navega con teclado o lector no lo pierda.
    setTimeout(() => this.resultado()?.nativeElement.focus());
  }
}
