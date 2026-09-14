import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Textarea } from '../../../shared/ui/textarea';

interface PaginaLegal {
  content: string;
  is_custom: boolean;
}

interface PaginasLegales {
  legal_notice: PaginaLegal;
  privacy_policy: PaginaLegal;
  cookies_policy: PaginaLegal;
  registration_terms: PaginaLegal;
}

const CLAVE_LEGALES = '/admin/legal-pages';

/**
 * Las cuatro páginas legales de la **plataforma**: aviso legal, privacidad,
 * cookies y condiciones de inscripción. Eventarium es una SaaS centralizada
 * (como Luma): son siempre las de plataforma, con independencia de la
 * organización que publique el evento al que alguien se inscribe (decisión
 * del usuario, 2026-09-14; antes las condiciones de inscripción eran un
 * contrato de cada organización, editable desde su propio panel).
 */
@Component({
  selector: 'app-platform-legal-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Textarea],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.plataforma.legales.titulo') }}</h1>
      <p class="descripcion">{{ t('admin.plataforma.legales.descripcion') }}</p>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }
      @if (guardado()) {
        <app-alert tone="exito" [title]="t('comun.guardado')">
          {{ t('admin.plataforma.legales.guardado') }}
        </app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <form (submit)="guardar($event)">
          <app-card [heading]="t('admin.plataforma.legales.avisoLegal')">
            <p class="estado">{{ estadoDe(avisoEsPersonalizado()) }}</p>
            <app-textarea
              [label]="t('admin.plataforma.legales.avisoLegal')"
              [rows]="10"
              [(value)]="avisoLegal"
            />
          </app-card>

          <app-card [heading]="t('admin.plataforma.legales.privacidad')">
            <p class="estado">{{ estadoDe(privacidadEsPersonalizada()) }}</p>
            <app-textarea
              [label]="t('admin.plataforma.legales.privacidad')"
              [rows]="10"
              [(value)]="privacidad"
            />
          </app-card>

          <app-card [heading]="t('admin.plataforma.legales.cookies')">
            <p class="estado">{{ estadoDe(cookiesEsPersonalizada()) }}</p>
            <app-textarea
              [label]="t('admin.plataforma.legales.cookies')"
              [rows]="10"
              [(value)]="cookies"
            />
          </app-card>

          <app-card [heading]="t('admin.plataforma.legales.condicionesDeInscripcion')">
            <p class="estado">{{ estadoDe(condicionesEsPersonalizada()) }}</p>
            <app-textarea
              [label]="t('admin.plataforma.legales.condicionesDeInscripcion')"
              [rows]="10"
              [(value)]="condicionesDeInscripcion"
            />
          </app-card>

          <app-button type="submit" [loading]="guardando()">
            {{ t('comun.guardar') }}
          </app-button>
        </form>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-block-end: 0.25rem;
    }
    .descripcion {
      color: var(--muted);
      margin-block-end: 1.5rem;
      max-width: 68ch;
    }
    form {
      display: grid;
      gap: 1.5rem;
    }
    .estado {
      color: var(--muted);
      font-size: 0.875rem;
      margin-block-end: 0.5rem;
    }
  `,
})
export class PlatformLegalPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  readonly cargando = signal(true);
  readonly guardando = signal(false);
  readonly guardado = signal(false);
  readonly error = signal<string | null>(null);

  /** Contenido editable por página. Vacío = volver a la plantilla por defecto. */
  readonly avisoLegal = signal('');
  readonly privacidad = signal('');
  readonly cookies = signal('');
  readonly condicionesDeInscripcion = signal('');

  readonly avisoEsPersonalizado = signal(false);
  readonly privacidadEsPersonalizada = signal(false);
  readonly cookiesEsPersonalizada = signal(false);
  readonly condicionesEsPersonalizada = signal(false);

  constructor() {
    void this.cargar();
  }

  estadoDe(esPersonalizada: boolean): string {
    return this.transloco.translate(
      esPersonalizada
        ? 'admin.plataforma.legales.personalizada'
        : 'admin.plataforma.legales.plantillaPorDefecto',
    );
  }

  private async cargar(): Promise<void> {
    try {
      this.volcar(
        await firstValueFrom(
          this.http.get<PaginasLegales>(this.api.url(CLAVE_LEGALES), {
            headers: this.api.serverForwardHeaders(),
          }),
        ),
      );
    } catch {
      this.error.set(this.transloco.translate('admin.plataforma.legales.errorCarga'));
    } finally {
      this.cargando.set(false);
    }
  }

  private volcar(paginas: PaginasLegales): void {
    // El contenido que llega es el **efectivo** (editado o plantilla): se carga
    // en el campo para poder editarlo, y `is_custom` indica si hoy es una
    // edición propia o la plantilla por defecto.
    this.avisoLegal.set(paginas.legal_notice.content);
    this.privacidad.set(paginas.privacy_policy.content);
    this.cookies.set(paginas.cookies_policy.content);
    this.condicionesDeInscripcion.set(paginas.registration_terms.content);

    this.avisoEsPersonalizado.set(paginas.legal_notice.is_custom);
    this.privacidadEsPersonalizada.set(paginas.privacy_policy.is_custom);
    this.cookiesEsPersonalizada.set(paginas.cookies_policy.is_custom);
    this.condicionesEsPersonalizada.set(paginas.registration_terms.is_custom);
  }

  async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.guardando.set(true);
    this.guardado.set(false);
    this.error.set(null);

    // Vacío = volver a la plantilla por defecto (el backend lo interpreta así
    // con un `null`), no guardar una página en blanco.
    const aTexto = (valor: string): string | null => {
      const limpio = valor.trim();
      return limpio === '' ? null : limpio;
    };

    try {
      this.volcar(
        await firstValueFrom(
          this.http.patch<PaginasLegales>(
            this.api.url(CLAVE_LEGALES),
            {
              legal_notice_content: aTexto(this.avisoLegal()),
              privacy_policy_content: aTexto(this.privacidad()),
              cookies_policy_content: aTexto(this.cookies()),
              registration_terms_content: aTexto(this.condicionesDeInscripcion()),
            },
            { headers: this.api.serverForwardHeaders() },
          ),
        ),
      );
      this.guardado.set(true);
    } catch (fallo) {
      this.error.set(
        fallo instanceof ApiError
          ? fallo.message
          : this.transloco.translate('admin.plataforma.legales.errorGuardar'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
