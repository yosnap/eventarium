import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import {
  IDIOMAS,
  IDIOMA_POR_DEFECTO,
  NOMBRE_DEL_IDIOMA,
  type Idioma,
} from '../../../core/i18n/idioma';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Textarea } from '../../../shared/ui/textarea';
import { PageHeader } from '../../../shared/ui/page-header';
import { SegmentedFilter } from '../../../shared/ui/segmented-filter';

interface PaginaLegal {
  content: string;
  is_custom: boolean;
  served_locale?: Idioma;
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
  imports: [TranslocoDirective, Alert, Button, Card, Textarea, PageHeader, SegmentedFilter],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.plataforma.legales.rotulo')">
        {{ t('admin.plataforma.legales.descripcion') }}
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }
      @if (guardado()) {
        <app-alert tone="exito" [title]="t('comun.guardado')">
          {{ t('admin.plataforma.legales.guardado') }}
        </app-alert>
      }

      <div class="idioma">
        <app-segmented-filter
          [opciones]="opcionesDeIdioma"
          [valor]="idioma()"
          [etiqueta]="t('admin.plataforma.legales.idioma')"
          (cambio)="cambiarIdioma($event)"
        />
        @if (idioma() !== idiomaPorDefecto) {
          <p class="estado">{{ t('admin.plataforma.legales.aMano') }}</p>
        }
      </div>

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
    .idioma {
      display: grid;
      gap: 0.5rem;
      margin-block-end: 1.5rem;
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

  /** Idioma de la versión que se edita. El legal no pasa por la IA. */
  readonly idioma = signal<Idioma>(IDIOMA_POR_DEFECTO);
  protected readonly idiomaPorDefecto = IDIOMA_POR_DEFECTO;
  protected readonly opcionesDeIdioma = IDIOMAS.map((valor) => ({
    valor,
    etiqueta: NOMBRE_DEL_IDIOMA[valor],
  }));
  private readonly enOtroIdioma = computed(() => this.idioma() !== IDIOMA_POR_DEFECTO);

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
        : this.enOtroIdioma()
          ? 'admin.plataforma.legales.sinVersion'
          : 'admin.plataforma.legales.plantillaPorDefecto',
    );
  }

  protected cambiarIdioma(idioma: Idioma): void {
    if (idioma === this.idioma()) {
      return;
    }
    this.idioma.set(idioma);
    this.guardado.set(false);
    this.error.set(null);
    this.cargando.set(true);
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    const idioma = this.idioma();
    try {
      const paginas = await firstValueFrom(
        this.http.get<PaginasLegales>(this.api.url(CLAVE_LEGALES), {
          headers: this.api.serverForwardHeaders(),
          params: { idioma },
        }),
      );
      // Una respuesta de un idioma que ya no es el elegido se descarta.
      if (idioma === this.idioma()) {
        this.volcar(paginas);
      }
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
    // En otro idioma, sin versión propia la API devuelve la española: el campo se
    // deja vacío para escribir la traducción, no para editar el texto español.
    const texto = (pagina: PaginaLegal): string =>
      this.enOtroIdioma() && pagina.served_locale !== this.idioma() ? '' : pagina.content;
    this.avisoLegal.set(texto(paginas.legal_notice));
    this.privacidad.set(texto(paginas.privacy_policy));
    this.cookies.set(texto(paginas.cookies_policy));
    this.condicionesDeInscripcion.set(texto(paginas.registration_terms));

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
              locale: this.idioma(),
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
