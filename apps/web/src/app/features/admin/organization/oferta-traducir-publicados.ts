import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal, viewChild } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { AuthService } from '../../../core/auth/auth.service';
import type { Idioma } from '../../../core/i18n/idioma';
import { AvisoClavePropia } from '../../../shared/ui/aviso-clave-propia';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Dialog } from '../../../shared/ui/dialog';

interface Estimacion {
  readonly events: number;
  readonly texts: number;
  readonly estimated_cost_usd: string | null;
  readonly auto_translation_available: boolean;
}

/**
 * Al activar un idioma con eventos ya publicados, ofrece traducirlos con IA
 * mostrando el coste estimado. Si se acepta, se encolan y se traducen poco a
 * poco; si no, se traducirán al vuelo cuando alguien los visite.
 */
@Component({
  selector: 'app-oferta-traducir-publicados',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, AvisoClavePropia, Button, Dialog],
  template: `
    <ng-container *transloco="let t; prefix: 'admin.organizacion.ofertaTraducir'">
      <app-dialog #dialogo [etiqueta]="t('titulo', { idioma: t('idiomas.' + idioma()) })">
        @if (estimacion(); as e) {
          <h2>{{ t('titulo', { idioma: t('idiomas.' + idioma()) }) }}</h2>
          @if (!e.auto_translation_available) {
            <app-aviso-clave-propia />
          } @else {
            <p>{{ t('texto', { eventos: e.events, textos: e.texts }) }}</p>
            @if (e.estimated_cost_usd) {
              <p>
                <strong>{{ t('coste', { coste: e.estimated_cost_usd }) }}</strong>
              </p>
            }
            <p class="nota">{{ t('nota') }}</p>
          }
          @if (error()) {
            <app-alert tone="error">{{ t('error') }}</app-alert>
          }
        }
        <app-button pie variant="secundario" (pulsado)="dialogo.cerrar()">{{
          t('ahoraNo')
        }}</app-button>
        @if (estimacion()?.auto_translation_available) {
          <app-button pie [loading]="enviando()" (pulsado)="traducir()">{{
            t('traducir')
          }}</app-button>
        }
      </app-dialog>
    </ng-container>
  `,
  styles: `
    h2 {
      margin-top: 0;
      font-size: var(--fs-h3);
    }
    .nota {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
  `,
})
export class OfertaTraducirPublicados {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly dialogo = viewChild.required<Dialog>('dialogo');

  protected readonly estimacion = signal<Estimacion | null>(null);
  protected readonly enviando = signal(false);
  protected readonly error = signal(false);
  private readonly auth = inject(AuthService);
  protected readonly idioma = signal<Idioma>('en-US');

  /** Pide la estimación y abre el diálogo si hay algo que traducir con IA. */
  async ofrecer(idioma: Idioma): Promise<void> {
    try {
      const estimacion = await firstValueFrom(
        this.http.get<Estimacion>(this.api.url('/translations/published/estimate'), {
          params: { locale: idioma },
        }),
      );
      // Sin clave propia se avisa (el idioma no se traducirá solo); con clave,
      // solo si hay algo que traducir y quien guarda puede pedirlo.
      const puedeTraducir = this.auth.permisos()?.includes('events:write') ?? false;
      if (estimacion.auto_translation_available && (estimacion.texts === 0 || !puedeTraducir)) {
        return;
      }
      this.idioma.set(idioma);
      this.estimacion.set(estimacion);
      this.error.set(false);
      this.dialogo().abrir();
    } catch {
      // Sin estimación no se ofrece: los eventos se traducirán al vuelo.
    }
  }

  protected async traducir(): Promise<void> {
    this.enviando.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url('/translations/published'), null, {
          params: { locale: this.idioma() },
        }),
      );
      this.dialogo().cerrar();
    } catch {
      this.error.set(true);
    } finally {
      this.enviando.set(false);
    }
  }
}
