import { JSDOM } from 'jsdom';
import { afterEach, describe, expect, it } from 'vitest';

import { applyTokens, brandingToStyleBlock } from './apply-tokens';
import { brandingDePrueba, plantillaDeTemaDePrueba } from '../../../testing/branding.fixture';

describe('brandingToStyleBlock', () => {
  it('genera dos reglas, :root primero y [data-theme="light"] después', () => {
    const bloque = brandingToStyleBlock(brandingDePrueba());
    const indiceRoot = bloque.indexOf(':root{');
    const indiceLight = bloque.indexOf('[data-theme="light"]{');

    expect(indiceRoot).toBeGreaterThanOrEqual(0);
    expect(indiceLight).toBeGreaterThan(indiceRoot);
    expect(bloque).toContain('--bg:#080808;');
    expect(bloque).toContain('--bg:#f5f5f5;');
  });

  it('ignora un nombre de token fuera de la lista blanca', () => {
    const branding = brandingDePrueba({
      theme: plantillaDeTemaDePrueba({
        tokens: {
          dark: { bg: '#080808', 'no-es-un-token': '#ff0000' },
          light: { bg: '#ffffff' },
        },
      }),
    });

    const bloque = brandingToStyleBlock(branding);

    expect(bloque).toContain('--bg:#080808;');
    expect(bloque).not.toContain('no-es-un-token');
  });

  it('descarta un valor que no sea hex de 6 dígitos ni oklch()', () => {
    const branding = brandingDePrueba({
      theme: plantillaDeTemaDePrueba({
        tokens: {
          dark: {
            bg: 'rgb(0 255 0)',
            fg: 'var(--fg)',
            accent: 'rebeccapurple',
            surface: '#000000',
          },
          light: { surface: '#ffffff' },
        },
      }),
    });

    const bloque = brandingToStyleBlock(branding);

    expect(bloque).not.toContain('--bg:');
    expect(bloque).not.toContain('--fg:');
    expect(bloque).not.toContain('--accent:');
    expect(bloque).toContain('--surface:#000000;');
  });

  it('acepta un valor oklch()', () => {
    const branding = brandingDePrueba({
      theme: plantillaDeTemaDePrueba({
        tokens: { dark: { accent: 'oklch(87.6% 0.229 152.4)' }, light: {} },
      }),
    });

    expect(brandingToStyleBlock(branding)).toContain('--accent:oklch(87.6% 0.229 152.4);');
  });

  it('no descarta un box-shadow compuesto con oklch() en shadow-md/shadow-lg', () => {
    const branding = brandingDePrueba({
      theme: plantillaDeTemaDePrueba({
        tokens: {
          dark: { 'shadow-md': '0 4px 12px oklch(0% 0 0 / .35)' },
          light: {},
        },
      }),
    });

    expect(brandingToStyleBlock(branding)).toContain(
      '--shadow-md:0 4px 12px oklch(0% 0 0 / .35);',
    );
  });

  it('sin plantilla (theme null), no genera ningún bloque', () => {
    expect(brandingToStyleBlock(brandingDePrueba({ theme: null }))).toBe('');
  });
});

describe('applyTokens', () => {
  afterEach(() => {
    document.getElementById('tema-organizacion')?.remove();
    document.documentElement.removeAttribute('data-theme');
  });

  it('inyecta un <style id="tema-organizacion"> en <head>', () => {
    applyTokens(brandingDePrueba(), document);

    const estilo = document.getElementById('tema-organizacion');
    expect(estilo).toBeTruthy();
    expect(estilo!.tagName).toBe('STYLE');
    expect(estilo!.textContent).toContain(':root{');
  });

  it('sin plantilla, no inyecta nada y no falla si ya no hay ninguna', () => {
    applyTokens(brandingDePrueba({ theme: null }), document);
    expect(document.getElementById('tema-organizacion')).toBeNull();
  });

  it('quita el bloque anterior si la plantilla nueva es null', () => {
    applyTokens(brandingDePrueba(), document);
    expect(document.getElementById('tema-organizacion')).toBeTruthy();

    applyTokens(brandingDePrueba({ theme: null }), document);
    expect(document.getElementById('tema-organizacion')).toBeNull();
  });

  it(
    'test de cascada: con plantilla aplicada y data-theme="light", el fondo resultante ' +
      'es el claro de la plantilla, no el oscuro de la plantilla ni el de la base',
    () => {
      // Documento jsdom aislado del global de la suite (evita cualquier interferencia
      // de otro fichero de test que también mute el `document` compartido): así la
      // prueba de cascada es determinista por sí misma, no por el orden de ejecución.
      const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>');
      const { document: doc, getComputedStyle: computado } = dom.window;

      const base = doc.createElement('style');
      base.textContent =
        ':root{--bg:#000000;}[data-theme="light"]{--bg:#ffffff;}';
      doc.head.appendChild(base);

      applyTokens(brandingDePrueba(), doc);

      const oscuroDeLaPlantilla = computado(doc.documentElement).getPropertyValue('--bg').trim();
      expect(oscuroDeLaPlantilla).toBe('#080808');
      expect(oscuroDeLaPlantilla).not.toBe('#000000');

      doc.documentElement.setAttribute('data-theme', 'light');
      const claroDeLaPlantilla = computado(doc.documentElement).getPropertyValue('--bg').trim();
      expect(claroDeLaPlantilla).toBe('#f5f5f5');
      expect(claroDeLaPlantilla).not.toBe(oscuroDeLaPlantilla);
      expect(claroDeLaPlantilla).not.toBe('#ffffff');
    },
  );
});
