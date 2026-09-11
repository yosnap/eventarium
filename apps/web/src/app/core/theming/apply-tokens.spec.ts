import { JSDOM } from 'jsdom';
import { afterEach, describe, expect, it } from 'vitest';

import {
  applyTokensDeOrganizacion,
  applyTokensDePlataforma,
  brandingToStyleBlock,
  SELECTOR_AMBITO_ORGANIZACION,
} from './apply-tokens';
import { organizacionDePruebaDeBranding, plantillaDeTemaDePrueba } from '../../../testing/branding.fixture';

describe('brandingToStyleBlock', () => {
  it('genera dos reglas, la base primero y el modo claro después', () => {
    const bloque = brandingToStyleBlock(plantillaDeTemaDePrueba(), ':root');
    const indiceBase = bloque.indexOf(':root{');
    const indiceLight = bloque.indexOf(':root[data-theme="light"]{');

    expect(indiceBase).toBeGreaterThanOrEqual(0);
    expect(indiceLight).toBeGreaterThan(indiceBase);
    expect(bloque).toContain('--bg:#080808;');
    expect(bloque).toContain('--bg:#f5f5f5;');
  });

  it('en un contenedor, el modo claro se expresa como descendiente', () => {
    const bloque = brandingToStyleBlock(plantillaDeTemaDePrueba(), SELECTOR_AMBITO_ORGANIZACION);
    expect(bloque).toContain(`${SELECTOR_AMBITO_ORGANIZACION}{`);
    expect(bloque).toContain(`[data-theme="light"] ${SELECTOR_AMBITO_ORGANIZACION}{`);
  });

  it('ignora un nombre de token fuera de la lista blanca', () => {
    const bloque = brandingToStyleBlock(
      plantillaDeTemaDePrueba({
        tokens: {
          dark: { bg: '#080808', 'no-es-un-token': '#ff0000' },
          light: { bg: '#ffffff' },
        },
      }),
      ':root',
    );

    expect(bloque).toContain('--bg:#080808;');
    expect(bloque).not.toContain('no-es-un-token');
  });

  it('descarta un valor que no sea hex de 6 dígitos ni oklch()', () => {
    const bloque = brandingToStyleBlock(
      plantillaDeTemaDePrueba({
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
      ':root',
    );

    expect(bloque).not.toContain('--bg:');
    expect(bloque).not.toContain('--fg:');
    expect(bloque).not.toContain('--accent:');
    expect(bloque).toContain('--surface:#000000;');
  });

  it('acepta un valor oklch()', () => {
    const bloque = brandingToStyleBlock(
      plantillaDeTemaDePrueba({
        tokens: { dark: { accent: 'oklch(87.6% 0.229 152.4)' }, light: {} },
      }),
      ':root',
    );

    expect(bloque).toContain('--accent:oklch(87.6% 0.229 152.4);');
  });

  it('no descarta un box-shadow compuesto con oklch() en shadow-md/shadow-lg', () => {
    const bloque = brandingToStyleBlock(
      plantillaDeTemaDePrueba({
        tokens: {
          dark: { 'shadow-md': '0 4px 12px oklch(0% 0 0 / .35)' },
          light: {},
        },
      }),
      ':root',
    );

    expect(bloque).toContain('--shadow-md:0 4px 12px oklch(0% 0 0 / .35);');
  });

  it('sin plantilla (theme null), no genera ningún bloque', () => {
    expect(brandingToStyleBlock(null, ':root')).toBe('');
  });
});

describe('applyTokens (dos alcances)', () => {
  afterEach(() => {
    document.getElementById('tema-plataforma')?.remove();
    document.getElementById('tema-organizacion')?.remove();
    document.documentElement.removeAttribute('data-theme');
  });

  it('la plataforma se aplica al documento entero', () => {
    applyTokensDePlataforma({ theme: plantillaDeTemaDePrueba() }, document);

    const estilo = document.getElementById('tema-plataforma');
    expect(estilo).toBeTruthy();
    expect(estilo!.textContent).toContain(':root{');
    expect(estilo!.textContent).toContain('--bg:#080808;');
  });

  it('la organización se aplica a su ámbito, no al documento', () => {
    applyTokensDeOrganizacion({ theme: plantillaDeTemaDePrueba() }, document);

    const estilo = document.getElementById('tema-organizacion');
    expect(estilo).toBeTruthy();
    expect(estilo!.textContent).toContain(SELECTOR_AMBITO_ORGANIZACION);
    // No debe tocar `:root`: eso pintaría el chrome entero con la marca de la
    // organización, que es justo lo que este cambio evita.
    expect(estilo!.textContent).not.toContain(':root{');
  });

  it('sin organización (host de plataforma), no inyecta plantilla de organización', () => {
    applyTokensDeOrganizacion(null, document);
    expect(document.getElementById('tema-organizacion')).toBeNull();
  });

  it('quita el bloque anterior si la plantilla nueva es null', () => {
    applyTokensDeOrganizacion({ theme: plantillaDeTemaDePrueba() }, document);
    expect(document.getElementById('tema-organizacion')).toBeTruthy();

    applyTokensDeOrganizacion({ theme: null }, document);
    expect(document.getElementById('tema-organizacion')).toBeNull();
  });

  it(
    'cascada: la plantilla de la organización solo afecta dentro de su ámbito',
    () => {
      // Documento jsdom aislado del global de la suite (evita interferencia de
      // otro fichero que también mute el `document` compartido).
      const dom = new JSDOM('<!doctype html><html><head></head><body><div id="ambito"></div></body></html>');
      const { document: doc, getComputedStyle: computado } = dom.window;

      // La plataforma pinta el documento; la organización, solo su contenedor.
      applyTokensDePlataforma(
        { theme: plantillaDeTemaDePrueba({ tokens: { dark: { bg: '#111111' }, light: { bg: '#eeeeee' } } }) },
        doc,
      );
      applyTokensDeOrganizacion(
        {
          theme: plantillaDeTemaDePrueba({
            tokens: { dark: { bg: '#080808' }, light: { bg: '#f5f5f5' } },
          }),
        },
        doc,
      );

      const ambito = doc.getElementById('ambito')!;
      ambito.setAttribute('data-ambito', 'organizacion');

      // Dentro del ámbito manda la plantilla de la organización…
      expect(computado(ambito).getPropertyValue('--bg').trim()).toBe('#080808');
      // …y fuera (el chrome) sigue mandando la de plataforma.
      expect(computado(doc.documentElement).getPropertyValue('--bg').trim()).toBe('#111111');
    },
  );
});

describe('contenido de la organización en el fixture', () => {
  it('expone los datos de la organización como un bloque propio', () => {
    const organizacion = organizacionDePruebaDeBranding();
    expect(organizacion.name).toBe('Organización de prueba');
    expect(organizacion.theme).not.toBeNull();
  });
});
