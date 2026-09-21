import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { PageHeader } from '../../../shared/ui/page-header';
import { MediaElegida, MediaPicker } from '../../../shared/ui/media-picker';
import { LOGO_ACEPTADOS } from '../../../shared/uploads/image-upload-constraints';

/** Identidad de la plataforma tal y como la devuelve `GET /admin/identity`. */
interface IdentidadDePlataforma {
  name: string;
  logo_url: string | null;
  favicon_url: string | null;
  social_links: readonly { kind: string; url: string }[];
}

const CLAVE_IDENTIDAD = '/admin/identity';

/**
 * Identidad de la web de la instalación: nombre, logotipo y favicon. Es la
 * marca de **Eventarium**, no la de una organización; por eso vive en el
 * panel de administración de plataforma. La plantilla del chrome no se
 * elige aquí: vive solo en «Plantillas de tema» (`theme-templates-page.ts`),
 * que ya tiene su propio flujo completo de aplicar — este formulario no
 * duplica ese selector.
 */
@Component({
  selector: 'app-platform-identity-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, PageHeader, MediaPicker],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.plataforma.identidad.rotulo')">
        {{ t('admin.plataforma.identidad.descripcion') }}
      </app-page-header>

      @if (error(); as mensaje) {
        <app-alert tone="error" [title]="t('comun.error')">{{ mensaje }}</app-alert>
      }
      @if (guardado()) {
        <app-alert tone="exito" [title]="t('comun.guardado')">
          {{ t('admin.plataforma.identidad.guardado') }}
        </app-alert>
      }

      <app-card [heading]="t('admin.plataforma.identidad.marca')">
        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else {
          <form (submit)="guardar($event)">
            <app-input
              [label]="t('admin.plataforma.identidad.nombre')"
              [required]="true"
              [(value)]="nombre"
            />

            <app-button type="submit" [loading]="guardando()">
              {{ t('comun.guardar') }}
            </app-button>
          </form>
        }
      </app-card>

      <app-card [heading]="t('admin.plataforma.identidad.imagenes')">
        <div class="imagenes">
          <app-media-picker
            #logoPicker
            class="imagen"
            [etiqueta]="t('admin.plataforma.identidad.logotipo')"
            [aceptados]="LOGO_ACEPTADOS"
            kind="platform"
            [url]="logoUrl()"
            (mediaElegido)="asignarImagen($event, 'logo', logoPicker)"
          />
          <app-media-picker
            #faviconPicker
            class="imagen"
            [etiqueta]="t('admin.plataforma.identidad.favicon')"
            [aceptados]="LOGO_ACEPTADOS"
            kind="platform"
            [url]="faviconUrl()"
            (mediaElegido)="asignarImagen($event, 'favicon', faviconPicker)"
          />
        </div>
      </app-card>
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
      gap: 1rem;
      max-width: 32rem;
    }
    .imagenes {
      display: flex;
      flex-wrap: wrap;
      gap: 2rem;
    }
    .imagen {
      display: grid;
      gap: 0.5rem;
    }
    .etiqueta {
      font-weight: 600;
    }
    .vacio {
      color: var(--muted);
    }
    .subir {
      cursor: pointer;
      text-decoration: underline;
      font-size: 0.875rem;
    }
    .subir input {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
    }
  `,
})
export class PlatformIdentityPage {
  protected readonly LOGO_ACEPTADOS = LOGO_ACEPTADOS;

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  readonly cargando = signal(true);
  readonly guardando = signal(false);
  readonly guardado = signal(false);
  readonly error = signal<string | null>(null);

  readonly nombre = signal('');
  readonly logoUrl = signal<string | null>(null);
  readonly faviconUrl = signal<string | null>(null);

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const identidad = await firstValueFrom(
        this.http.get<IdentidadDePlataforma>(this.api.url(CLAVE_IDENTIDAD), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.nombre.set(identidad.name);
      this.logoUrl.set(identidad.logo_url);
      this.faviconUrl.set(identidad.favicon_url);
    } catch {
      this.error.set(this.transloco.translate('admin.plataforma.identidad.errorCarga'));
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
      const identidad = await firstValueFrom(
        this.http.patch<IdentidadDePlataforma>(
          this.api.url(CLAVE_IDENTIDAD),
          { name: this.nombre().trim() },
          { headers: this.api.serverForwardHeaders() },
        ),
      );
      this.aplicar(identidad);
      this.guardado.set(true);
    } catch (fallo) {
      this.error.set(this.mensajeDeError(fallo, 'admin.plataforma.identidad.errorGuardar'));
    } finally {
      this.guardando.set(false);
    }
  }

  /** El fichero/URL/biblioteca ya se resolvió a un `media_id` dentro de
   * `MediaPicker` (Fase 3 del plan de biblioteca de medios): aquí solo queda
   * asignarlo al campo correspondiente de la identidad de plataforma. Si
   * falla, `picker.revertir()` deshace la previsualización optimista. */
  async asignarImagen(
    media: MediaElegida,
    tipo: 'logo' | 'favicon',
    picker: MediaPicker,
  ): Promise<void> {
    this.guardado.set(false);
    this.error.set(null);
    try {
      const identidad = await firstValueFrom(
        this.http.put<IdentidadDePlataforma>(
          this.api.url(`${CLAVE_IDENTIDAD}/${tipo}`),
          { media_id: media.id },
          { headers: this.api.serverForwardHeaders() },
        ),
      );
      this.aplicar(identidad);
      this.guardado.set(true);
    } catch (fallo) {
      picker.revertir();
      this.error.set(this.mensajeDeError(fallo, 'admin.plataforma.identidad.errorSubida'));
    }
  }

  private aplicar(identidad: IdentidadDePlataforma): void {
    this.nombre.set(identidad.name);
    this.logoUrl.set(identidad.logo_url);
    this.faviconUrl.set(identidad.favicon_url);
  }

  private mensajeDeError(fallo: unknown, clave: string): string {
    if (fallo instanceof ApiError) {
      return fallo.message;
    }
    return this.transloco.translate(clave);
  }
}
