import { describe, expect, it } from 'vitest';

import { fuentesDelHtml, precargarFuentes } from './server-fuentes';

describe('precarga de fuentes en el SSR', () => {
  it('precarga las familias del tema que ya va en el HTML', () => {
    const html =
      '<head><style id="tema-plataforma">:root{--font-body:Inter;--font-display:Oswald;}</style></head>';
    expect(fuentesDelHtml(html)).toEqual([
      '/assets/fonts/inter/inter-400.woff2',
      '/assets/fonts/oswald/oswald-500.woff2',
    ]);
  });

  it('sin tema, las fuentes por defecto', () => {
    expect(fuentesDelHtml('<head></head>')).toEqual([
      '/assets/fonts/bebas-neue/bebas-neue-400.woff2',
      '/assets/fonts/dm-sans/dm-sans-400.woff2',
    ]);
  });

  it('ignora familias que no son de la plataforma', () => {
    expect(fuentesDelHtml('<style>:root{--font-body:Comic Sans;}</style>')).toContain(
      '/assets/fonts/dm-sans/dm-sans-400.woff2',
    );
  });

  it('inserta los enlaces en el head una sola vez', () => {
    const una = precargarFuentes('<html><head><title>x</title></head><body></body></html>');
    expect(una).toContain(
      '<link rel="preload" href="/assets/fonts/dm-sans/dm-sans-400.woff2" as="font" type="font/woff2" crossorigin></head>',
    );
    expect(precargarFuentes(una)).toBe(una);
  });
});
