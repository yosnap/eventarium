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

const LEGAL_PAGES_URL = '/organizations/me/legal-pages';

type ClaveCampo =
  | 'legal_notice_content'
  | 'privacy_policy_content'
  | 'cookies_policy_content'
  | 'registration_terms_content';

interface PaginaLegal {
  readonly content: string;
  readonly is_custom: boolean;
}

interface LegalPagesResponse {
  readonly legal_notice: PaginaLegal;
  readonly privacy_policy: PaginaLegal;
  readonly cookies_policy: PaginaLegal;
  readonly registration_terms: PaginaLegal;
}

interface DefinicionDePagina {
  readonly campo: ClaveCampo;
  readonly clave: keyof LegalPagesResponse;
  readonly tituloTranslocoKey: string;
}

const PAGINAS: readonly DefinicionDePagina[] = [
  {
    campo: 'legal_notice_content',
    clave: 'legal_notice',
    tituloTranslocoKey: 'admin.legal.avisoLegal',
  },
  {
    campo: 'privacy_policy_content',
    clave: 'privacy_policy',
    tituloTranslocoKey: 'admin.legal.privacidad',
  },
  {
    campo: 'cookies_policy_content',
    clave: 'cookies_policy',
    tituloTranslocoKey: 'admin.legal.cookies',
  },
  {
    campo: 'registration_terms_content',
    clave: 'registration_terms',
    tituloTranslocoKey: 'admin.legal.condicionesInscripcion',
  },
];

/**
 * Edición del contenido de las cuatro páginas legales públicas.
 *
 * Un textarea por página; "restaurar plantilla por defecto" envía el campo a
 * `null` explícito (no lo omite): el backend distingue "no tocar" (campo
 * ausente) de "restaurar" (`null` presente), mismo patrón que
 * `OrganizationUpdate`.
 */
@Component({
  selector: 'app-legal-pages-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Textarea],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.legal.titulo') }}</h1>
      <p>{{ t('admin.legal.descripcion') }}</p>

      @if (error()) {
        <app-alert tone="error">{{ t('admin.legal.error') }}</app-alert>
      }
      @if (guardado()) {
        <app-alert tone="exito">{{ t('admin.legal.guardado') }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        @for (definicion of paginas; track definicion.campo) {
          <app-card>
            <h2>
              {{ t(definicion.tituloTranslocoKey) }}
              @if (esCustom(definicion.clave)) {
                <span class="etiqueta">{{ t('admin.legal.editada') }}</span>
              } @else {
                <span class="etiqueta etiqueta-defecto">{{ t('admin.legal.porDefecto') }}</span>
              }
            </h2>
            <app-textarea
              [label]="t(definicion.tituloTranslocoKey)"
              [rows]="10"
              [value]="valores()[definicion.campo]"
              (valueChange)="actualizarValor(definicion.campo, $event)"
            />
            <div class="acciones-pagina">
              <app-button [loading]="guardando()" (pulsado)="guardar(definicion.campo)">
                {{ guardando() ? t('admin.legal.guardando') : t('admin.legal.guardar') }}
              </app-button>
              <app-button
                variant="secundario"
                [disabled]="!esCustom(definicion.clave)"
                (pulsado)="restaurar(definicion.campo)"
              >
                {{ t('admin.legal.restaurarPlantilla') }}
              </app-button>
            </div>
          </app-card>
        }
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    h2 {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-size: 1.125rem;
    }
    .etiqueta {
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.15rem 0.5rem;
      border-radius: var(--radius-md);
      background-color: var(--color-primary);
      color: var(--color-primary-contrast);
    }
    .etiqueta-defecto {
      background-color: var(--color-surface-muted);
      color: var(--color-text-muted, #6b7280);
    }
    app-card {
      display: block;
      margin-bottom: var(--space-md);
    }
    .acciones-pagina {
      display: flex;
      gap: var(--space-sm);
      margin-top: var(--space-sm);
    }
  `,
})
export class LegalPagesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly paginas = PAGINAS;

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly guardado = signal(false);
  protected readonly error = signal(false);

  private readonly respuesta = signal<LegalPagesResponse | null>(null);
  protected readonly valores = signal<Record<ClaveCampo, string>>({
    legal_notice_content: '',
    privacy_policy_content: '',
    cookies_policy_content: '',
    registration_terms_content: '',
  });

  constructor() {
    void this.cargar();
  }

  protected esCustom(clave: keyof LegalPagesResponse): boolean {
    return this.respuesta()?.[clave].is_custom ?? false;
  }

  protected actualizarValor(campo: ClaveCampo, valor: string): void {
    this.valores.update((actuales) => ({ ...actuales, [campo]: valor }));
  }

  private async cargar(): Promise<void> {
    try {
      const datos = await firstValueFrom(
        this.http.get<LegalPagesResponse>(this.api.url(LEGAL_PAGES_URL)),
      );
      this.aplicar(datos);
    } catch {
      this.error.set(true);
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicar(datos: LegalPagesResponse): void {
    this.respuesta.set(datos);
    this.valores.set({
      legal_notice_content: datos.legal_notice.content,
      privacy_policy_content: datos.privacy_policy.content,
      cookies_policy_content: datos.cookies_policy.content,
      registration_terms_content: datos.registration_terms.content,
    });
  }

  protected async guardar(campo: ClaveCampo): Promise<void> {
    await this.enviar({ [campo]: this.valores()[campo] });
  }

  protected async restaurar(campo: ClaveCampo): Promise<void> {
    await this.enviar({ [campo]: null });
  }

  private async enviar(cambios: Partial<Record<ClaveCampo, string | null>>): Promise<void> {
    this.guardando.set(true);
    this.guardado.set(false);
    this.error.set(false);
    try {
      const datos = await firstValueFrom(
        this.http.patch<LegalPagesResponse>(this.api.url(LEGAL_PAGES_URL), cambios),
      );
      this.aplicar(datos);
      this.guardado.set(true);
    } catch (error) {
      this.error.set(true);
      if (!(error instanceof ApiError)) {
        console.error('[legal] no se han podido guardar los cambios:', error);
      }
    } finally {
      this.guardando.set(false);
    }
  }
}
