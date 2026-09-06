import { DOCUMENT, Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { TransferState, makeStateKey } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { Branding } from './branding.model';
import { applyTokens } from './apply-tokens';

/** El branding resuelto en SSR viaja al navegador para no repetir la petición. */
const CLAVE_BRANDING = makeStateKey<Branding>('branding');

@Injectable({ providedIn: 'root' })
export class ThemingService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly documento = inject(DOCUMENT);
  private readonly transferState = inject(TransferState);

  private readonly estado = signal<Branding | null>(null);
  private readonly errorEstado = signal<string | null>(null);

  readonly branding = this.estado.asReadonly();
  readonly error = this.errorEstado.asReadonly();
  readonly templateKey = computed(() => this.estado()?.template_key ?? 'classic');
  readonly organizationName = computed(() => this.estado()?.organization_name ?? '');

  /**
   * Carga el branding de la organización del host actual.
   *
   * Si la API falla no se pinta el tema por defecto como si fuera el de la
   * organización: eso mostraría una marca equivocada. Se deja el error a la vista y la
   * aplicación enseña una pantalla de «sitio no disponible».
   */
  async load(): Promise<void> {
    const transferido = this.transferState.get(CLAVE_BRANDING, null);
    if (transferido) {
      this.transferState.remove(CLAVE_BRANDING);
      this.aplicar(transferido);
      return;
    }

    try {
      const branding = await firstValueFrom(
        this.http.get<Branding>(this.api.url('/tenant/branding'), {
          headers: this.api.serverForwardHeaders(),
        }),
      );
      this.aplicar(branding);
      if (this.api.isServer) {
        this.transferState.set(CLAVE_BRANDING, branding);
      }
    } catch (error) {
      const mensaje =
        error instanceof Error ? error.message : 'No se ha podido cargar la configuración.';
      this.errorEstado.set(mensaje);
      console.error('[theming] no se ha podido cargar el branding:', error);
    }
  }

  private aplicar(branding: Branding): void {
    this.estado.set(branding);
    this.errorEstado.set(null);
    applyTokens(branding, this.documento);
    this.documento.title = branding.organization_name;
    if (branding.favicon_url) {
      this.fijarFavicon(branding.favicon_url);
    }
  }

  private fijarFavicon(url: string): void {
    const existente = this.documento.querySelector<HTMLLinkElement>('link[rel~="icon"]');
    const enlace = existente ?? this.documento.createElement('link');
    enlace.rel = 'icon';
    enlace.href = url;
    if (!existente) {
      this.documento.head.appendChild(enlace);
    }
  }
}
