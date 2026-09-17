import { HttpClient } from '@angular/common/http';
import { DOCUMENT, PLATFORM_ID, Injectable, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { CookieCategory } from './cookie-category';

/** Identificadores semi-públicos de los proveedores (endpoint público de la
 * fase 1 del plan de cookies: mismo nivel de exposición que el HTML). */
interface IdentificadoresDeAnalitica {
  readonly ga4_measurement_id: string | null;
  readonly meta_pixel_id: string | null;
  readonly cloudflare_analytics_token: string | null;
}

const IDENTIFICADORES_URL = '/tenant/analytics';

interface VentanaConGtag {
  dataLayer?: unknown[];
  gtag?: (...args: unknown[]) => void;
}

/** El stub de `fbq` de la receta oficial de Meta: función auto-referenciada
 * con cola, que reenvía a `callMethod` cuando `fbevents.js` aterriza. */
interface FbqStub {
  (...args: unknown[]): void;
  callMethod?: (...args: unknown[]) => void;
  queue: unknown[];
  version: string;
  loaded: boolean;
  push: unknown;
}

/**
 * Scripts reales de los proveedores de analítica externa (fase 4 del plan de
 * cookies `260916-2246-cookies-analitica-externa`), sustituyendo al
 * `DummyAnalyticsService` de demostración. Mismo punto de enganche: solo se
 * llama desde `CookieConsentService` con las categorías ya consentidas.
 *
 * Reglas:
 * - Un proveedor sin identificador configurado **no inyecta nada** — nunca
 *   un script roto apuntando a `undefined`.
 * - Mapeo de categorías, alineado con la pantalla de admin (fase 3):
 *   GA4 → `analytics`, Meta Pixel → `marketing`.
 * - Cloudflare Web Analytics también va bajo `analytics` (decisión
 *   conservadora del plan, hallazgo predict): su documentación oficial
 *   (developers.cloudflare.com/web-analytics/about/) afirma que «does not
 *   collect or use your visitors' personal data», pero no dice nada
 *   explícito sobre cookies ni identificadores, y en ePrivacy la ausencia
 *   de datos personales no exime del consentimiento — ante la ambigüedad,
 *   hacia más consentimiento, no menos.
 * - `Cloudflare Turnstile` sigue siendo un caso aparte: necesario, nunca
 *   pasa por aquí (ver `turnstile-widget.ts`).
 *
 * Nada de scripts inline: el stub de gtag y el de `fbq` se construyen por
 * TypeScript, así que una CSP restrictiva de la instalación no los rompe.
 */
@Injectable({ providedIn: 'root' })
export class ScriptsDeAnaliticaService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly documento = inject(DOCUMENT);
  private readonly esNavegador = isPlatformBrowser(inject(PLATFORM_ID));

  /** Una sola consulta de identificadores para los tres proveedores: el
   * banner activa varios a la vez y el endpoint público es el mismo. */
  private identificadores: Promise<IdentificadoresDeAnalitica | null> | null = null;

  activarSiConsentidas(categorias: readonly CookieCategory[]): void {
    if (!this.esNavegador) {
      return;
    }
    if (categorias.includes('analytics')) {
      void this.activarGa4();
      void this.activarCloudflare();
    }
    if (categorias.includes('marketing')) {
      void this.activarMetaPixel();
    }
  }

  private async activarGa4(): Promise<void> {
    const identificadores = await this.obtenerIdentificadores();
    const id = identificadores?.ga4_measurement_id;
    if (!id || this.documento.getElementById('ga4-analytics-script')) {
      return;
    }

    const ventana = window as unknown as VentanaConGtag;
    ventana.dataLayer = ventana.dataLayer ?? [];
    if (!ventana.gtag) {
      // Stub oficial de Google (`function gtag(){dataLayer.push(arguments)}`):
      // GTM interpreta el objeto `arguments` como la llamada; replicado tal
      // cual, sin script inline.
      /* eslint-disable prefer-rest-params -- la receta oficial usa el objeto arguments */
      ventana.gtag = function (): void {
        ventana.dataLayer?.push(arguments);
      };
      /* eslint-enable prefer-rest-params */
    }
    ventana.gtag('js', new Date());
    ventana.gtag('config', id);

    const script = this.documento.createElement('script');
    script.id = 'ga4-analytics-script';
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
    this.documento.head.appendChild(script);
  }

  private async activarMetaPixel(): Promise<void> {
    const identificadores = await this.obtenerIdentificadores();
    const id = identificadores?.meta_pixel_id;
    if (!id || this.documento.getElementById('meta-pixel-script')) {
      return;
    }

    const ventana = window as unknown as { fbq?: FbqStub; _fbq?: unknown };
    if (!ventana.fbq) {
      const fbq: FbqStub = function (...args: unknown[]): void {
        if (fbq.callMethod) {
          fbq.callMethod(...args);
        } else {
          fbq.queue.push(args);
        }
      };
      fbq.push = fbq;
      fbq.loaded = true;
      fbq.version = '2.0';
      fbq.queue = [];
      ventana.fbq = fbq;
      ventana._fbq = fbq;
    }
    ventana.fbq('init', id);
    ventana.fbq('track', 'PageView');

    const script = this.documento.createElement('script');
    script.id = 'meta-pixel-script';
    script.async = true;
    script.src = 'https://connect.facebook.net/en_US/fbevents.js';
    this.documento.head.appendChild(script);
  }

  private async activarCloudflare(): Promise<void> {
    const identificadores = await this.obtenerIdentificadores();
    const token = identificadores?.cloudflare_analytics_token;
    if (!token || this.documento.getElementById('cloudflare-analytics-script')) {
      return;
    }

    const script = this.documento.createElement('script');
    script.id = 'cloudflare-analytics-script';
    script.defer = true;
    script.src = 'https://static.cloudflareinsights.com/beacon.min.js';
    script.setAttribute('data-cf-beacon', JSON.stringify({ token }));
    this.documento.head.appendChild(script);
  }

  private obtenerIdentificadores(): Promise<IdentificadoresDeAnalitica | null> {
    // El fallo del endpoint (red, instalación sin fila) deja los tres
    // proveedores sin identificar: sin scripts, sin error ruidoso — el
    // banner ya hizo su trabajo y la navegación no depende de esto.
    this.identificadores ??= firstValueFrom(
      this.http.get<IdentificadoresDeAnalitica>(this.api.url(IDENTIFICADORES_URL)),
    ).catch(() => null);
    return this.identificadores;
  }
}
