import { DOCUMENT, Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { TransferState, makeStateKey } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { Branding, OrganizationBranding, PlatformBranding } from './branding.model';
import { applyTokensDeOrganizacion, applyTokensDePlataforma } from './apply-tokens';

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

  /**
   * Identidad de la plataforma (Eventarium). Presente en cualquier host: es la
   * marca del chrome de la web pública.
   */
  readonly plataforma = computed<PlatformBranding | null>(() => this.estado()?.platform ?? null);

  /**
   * Identidad de la organización del host, o `null` en un host de plataforma.
   * Es su marca para las páginas de evento, no para el chrome.
   */
  readonly organizacion = computed<OrganizationBranding | null>(
    () => this.estado()?.organization ?? null,
  );

  /** Nombre que muestra el chrome: siempre el de la plataforma. */
  readonly nombreDeMarca = computed(() => this.plataforma()?.name ?? '');

  /**
   * Nombre de la organización, para los paneles internos que son **suyos**
   * (su escritorio, su configuración). En un host de plataforma no hay
   * organización y cae al nombre de la plataforma, que es lo correcto: es la
   * única marca que existe ahí.
   */
  readonly nombreDeOrganizacion = computed(
    () => this.organizacion()?.name ?? this.plataforma()?.name ?? '',
  );

  /** Plantilla de composición de las páginas públicas. */
  readonly templateKey = computed(() => this.organizacion()?.template_key ?? 'classic');

  /**
   * Carga la identidad pública del host actual.
   *
   * Si la API falla no se pinta el tema por defecto como si fuera el real: eso
   * mostraría una marca equivocada. Se deja el error a la vista y la aplicación
   * enseña una pantalla de «sitio no disponible».
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

    // El chrome es de plataforma; la plantilla de la organización se aplica a un
    // ámbito propio (las páginas de evento), no al documento entero.
    applyTokensDePlataforma(branding.platform, this.documento);
    applyTokensDeOrganizacion(branding.organization, this.documento);

    this.documento.title = branding.platform.name;
    if (branding.platform.favicon_url) {
      this.fijarFavicon(branding.platform.favicon_url);
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
