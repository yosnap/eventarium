import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ScriptsDeAnaliticaService } from './scripts-analitica.service';

const IDENTIFICADORES_URL = '/api/v1/tenant/analytics';

const IDS_COMPLETOS = {
  ga4_measurement_id: 'G-TEST123',
  meta_pixel_id: '1234567890',
  cloudflare_analytics_token: 'tok-publico',
  gtm_container_id: null as string | null,
};

function scriptPorId(id: string): HTMLScriptElement | null {
  return document.getElementById(id) as HTMLScriptElement | null;
}

describe('ScriptsDeAnaliticaService', () => {
  let http: HttpTestingController;
  let servicio: ScriptsDeAnaliticaService;

  beforeEach(() => {
    for (const id of ['ga4-analytics-script', 'gtm-script', 'meta-pixel-script', 'cloudflare-analytics-script']) {
      document.getElementById(id)?.remove();
    }
    delete (window as unknown as { dataLayer?: unknown[] }).dataLayer;
    delete (window as unknown as { fbq?: unknown; _fbq?: unknown }).fbq;
    delete (window as unknown as { fbq?: unknown; _fbq?: unknown })._fbq;

    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
    servicio = TestBed.inject(ScriptsDeAnaliticaService);
  });

  afterEach(() => {
    http.verify();
  });

  it('sin categorías consentidas no consulta identificadores ni inyecta nada', () => {
    servicio.activarSiConsentidas(['necessary']);
    expect(scriptPorId('ga4-analytics-script')).toBeNull();
    // Sin petición de identificadores: no hay nada que activar.
  });

  it('analytics con GA4 configurado inyecta el script de gtag y su configuración', async () => {
    servicio.activarSiConsentidas(['necessary', 'analytics']);

    http.expectOne(IDENTIFICADORES_URL).flush(IDS_COMPLETOS);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    const script = scriptPorId('ga4-analytics-script');
    expect(script).not.toBeNull();
    expect(script?.src).toContain('googletagmanager.com/gtag/js?id=G-TEST123');
    const capa = (window as unknown as { dataLayer?: unknown[] }).dataLayer ?? [];
    expect(capa.length).toBeGreaterThanOrEqual(2);

    // La misma activación dos veces: un solo script (guard por id) y los
    // identificadores ya cacheados (una sola petición en todo el test).
    servicio.activarSiConsentidas(['necessary', 'analytics']);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(document.querySelectorAll('#ga4-analytics-script').length).toBe(1);
  });

  it('analytics con contenedor de GTM inyecta gtm.js y omite el gtag directo', async () => {
    servicio.activarSiConsentidas(['necessary', 'analytics']);

    http.expectOne(IDENTIFICADORES_URL).flush({
      ...IDS_COMPLETOS,
      gtm_container_id: 'GTM-TEST9',
    });
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    const script = scriptPorId('gtm-script');
    expect(script).not.toBeNull();
    expect(script?.src).toContain('googletagmanager.com/gtm.js?id=GTM-TEST9');
    expect(script?.src).toContain('l=dataLayer');
    expect(scriptPorId('ga4-analytics-script')).toBeNull();
    const capa = (window as unknown as { dataLayer?: unknown[] }).dataLayer ?? [];
    expect(capa.length).toBeGreaterThanOrEqual(1);
  });

  it('marketing con píxel configurado inyecta fbevents y prepara el stub de fbq', async () => {
    servicio.activarSiConsentidas(['necessary', 'marketing']);

    http.expectOne(IDENTIFICADORES_URL).flush(IDS_COMPLETOS);
    await Promise.resolve();
    await Promise.resolve();

    const script = scriptPorId('meta-pixel-script');
    expect(script).not.toBeNull();
    expect(script?.src).toContain('connect.facebook.net/en_US/fbevents.js');
    const fbq = (window as unknown as { fbq?: { version?: string; queue?: unknown[] } }).fbq;
    expect(fbq?.version).toBe('2.0');
    expect(Array.isArray(fbq?.queue)).toBe(true);
  });

  it('analytics con token de Cloudflare inyecta el beacon con su data-cf-beacon', async () => {
    servicio.activarSiConsentidas(['analytics']);

    http.expectOne(IDENTIFICADORES_URL).flush(IDS_COMPLETOS);
    await Promise.resolve();
    await Promise.resolve();

    const script = scriptPorId('cloudflare-analytics-script');
    expect(script).not.toBeNull();
    expect(script?.src).toContain('static.cloudflareinsights.com/beacon.min.js');
    expect(script?.getAttribute('data-cf-beacon')).toContain('tok-publico');
  });

  it('sin identificadores configurados no inyecta ningún script roto', async () => {
    servicio.activarSiConsentidas(['necessary', 'analytics', 'marketing']);

    http.expectOne(IDENTIFICADORES_URL).flush({
      ga4_measurement_id: null,
      meta_pixel_id: null,
      cloudflare_analytics_token: null,
    });
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(scriptPorId('ga4-analytics-script')).toBeNull();
    expect(scriptPorId('meta-pixel-script')).toBeNull();
    expect(scriptPorId('cloudflare-analytics-script')).toBeNull();
  });

  it('si la consulta de identificadores falla, no inyecta nada y no rompe', async () => {
    servicio.activarSiConsentidas(['necessary', 'analytics', 'marketing']);

    http.expectOne(IDENTIFICADORES_URL).flush(null, { status: 500, statusText: 'Error' });
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(scriptPorId('ga4-analytics-script')).toBeNull();
    expect(scriptPorId('meta-pixel-script')).toBeNull();
    expect(scriptPorId('cloudflare-analytics-script')).toBeNull();
  });
});
