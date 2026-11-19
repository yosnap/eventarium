import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import {
  IDIOMAS,
  IDIOMA_POR_DEFECTO,
  Idioma,
  NOMBRE_DEL_IDIOMA,
  PREFIJO_DE_IDIOMA,
} from '../../../core/i18n/idioma';
import { ThemingService } from '../../../core/theming/theming.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Checkbox } from '../../../shared/ui/checkbox';
import { PageHeader } from '../../../shared/ui/page-header';

/** Lo que esta página lee y guarda de `GET/PATCH /admin/identity`. */
interface AjustesDeIdioma {
  enabled_locales: Idioma[];
  language_switcher_visible: boolean;
}

const CLAVE_IDENTIDAD = '/admin/identity';

/**
 * Idiomas de la web pública de la instalación: cuáles se ofrecen y si se ve el
 * selector de idioma en la cabecera y el pie. El idioma por defecto no se puede
 * desactivar: es el de las URL sin prefijo.
 */
@Component({
  selector: 'app-platform-languages-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Checkbox, PageHeader],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.plataforma.idiomas.rotulo')">
        {{ t('admin.plataforma.idiomas.descripcion') }}
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }
      @if (guardado()) {
        <app-alert tone="exito" [title]="t('comun.guardado')">
          {{ t('admin.plataforma.idiomas.guardado') }}
        </app-alert>
      }

      <app-card [heading]="t('admin.plataforma.idiomas.activos')">
        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else {
          <form (submit)="guardar($event)">
            <fieldset>
              <legend>{{ t('admin.plataforma.idiomas.activosLeyenda') }}</legend>
              @for (idioma of idiomas; track idioma) {
                <app-checkbox
                  [label]="nombre(idioma)"
                  [hint]="pista(idioma)"
                  [disabled]="idioma === porDefecto"
                  [checked]="activos().includes(idioma)"
                  (checkedChange)="alternar(idioma, $event)"
                />
              }
            </fieldset>

            <app-checkbox
              [label]="t('admin.plataforma.idiomas.selector')"
              [hint]="t('admin.plataforma.idiomas.selectorPista')"
              [(checked)]="selectorVisible"
            />

            <app-button type="submit" [loading]="guardando()">
              {{ t('comun.guardar') }}
            </app-button>
          </form>
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    form {
      display: grid;
      gap: var(--space-4, 1rem);
      justify-items: start;
    }
    fieldset {
      display: grid;
      gap: var(--space-2, 0.5rem);
      margin: 0;
      padding: 0;
      border: 0;
    }
    legend {
      margin-bottom: var(--space-2, 0.5rem);
      font-weight: 600;
    }
  `,
})
export class PlatformLanguagesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly theming = inject(ThemingService);

  protected readonly idiomas = IDIOMAS;
  protected readonly porDefecto = IDIOMA_POR_DEFECTO;

  readonly cargando = signal(true);
  readonly guardando = signal(false);
  readonly guardado = signal(false);
  readonly error = signal<string | null>(null);

  readonly activos = signal<readonly Idioma[]>([IDIOMA_POR_DEFECTO]);
  readonly selectorVisible = signal(true);

  constructor() {
    void this.cargar();
  }

  protected nombre(idioma: Idioma): string {
    return NOMBRE_DEL_IDIOMA[idioma];
  }

  protected pista(idioma: Idioma): string {
    const prefijo = PREFIJO_DE_IDIOMA[idioma];
    return idioma === IDIOMA_POR_DEFECTO
      ? this.transloco.translate('admin.plataforma.idiomas.porDefecto')
      : this.transloco.translate('admin.plataforma.idiomas.prefijo', { prefijo: `/${prefijo}/` });
  }

  protected alternar(idioma: Idioma, activo: boolean): void {
    this.guardado.set(false);
    this.activos.update((actuales) =>
      IDIOMAS.filter((i) => (i === idioma ? activo : actuales.includes(i))),
    );
  }

  private async cargar(): Promise<void> {
    try {
      this.aplicar(
        await firstValueFrom(
          this.http.get<AjustesDeIdioma>(this.api.url(CLAVE_IDENTIDAD), {
            headers: this.api.serverForwardHeaders(),
          }),
        ),
      );
    } catch {
      this.error.set(this.transloco.translate('admin.plataforma.idiomas.errorCarga'));
    } finally {
      this.cargando.set(false);
    }
  }

  async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.guardando.set(true);
    this.guardado.set(false);
    this.error.set(null);
    try {
      this.aplicar(
        await firstValueFrom(
          this.http.patch<AjustesDeIdioma>(
            this.api.url(CLAVE_IDENTIDAD),
            {
              enabled_locales: this.activos(),
              language_switcher_visible: this.selectorVisible(),
            },
            { headers: this.api.serverForwardHeaders() },
          ),
        ),
      );
      // El selector y las rutas leen estos ajustes de la identidad pública.
      await this.theming.load();
      this.guardado.set(true);
    } catch (fallo) {
      this.error.set(
        fallo instanceof ApiError
          ? fallo.message
          : this.transloco.translate('admin.plataforma.idiomas.errorGuardar'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  private aplicar(ajustes: AjustesDeIdioma): void {
    this.activos.set(IDIOMAS.filter((i) => ajustes.enabled_locales.includes(i)));
    this.selectorVisible.set(ajustes.language_switcher_visible);
  }
}
