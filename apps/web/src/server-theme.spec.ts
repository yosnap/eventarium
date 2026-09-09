import { afterEach, describe, expect, it, vi } from 'vitest';

import { pintarTemaEnHtml } from './server-theme';
import { NOMBRE_COOKIE_TEMA } from './app/core/theming/theme-cookie';

const HTML_BASE = '<!doctype html><html lang="es-ES"><head></head><body></body></html>';

describe('pintarTemaEnHtml (server.ts)', () => {
  it('con eventarium.tema=claro, el HTML servido lleva data-theme="light" en <html>', () => {
    const resultado = pintarTemaEnHtml(HTML_BASE, `${NOMBRE_COOKIE_TEMA}=claro`);
    expect(resultado).toContain('<html lang="es-ES" data-theme="light">');
  });

  it('sin cookie, devuelve el oscuro por defecto: no toca el HTML', () => {
    const resultado = pintarTemaEnHtml(HTML_BASE, undefined);
    expect(resultado).toBe(HTML_BASE);
    expect(resultado).not.toContain('data-theme');
  });

  it('con eventarium.tema=oscuro explícito, tampoco toca el HTML', () => {
    const resultado = pintarTemaEnHtml(HTML_BASE, `${NOMBRE_COOKIE_TEMA}=oscuro`);
    expect(resultado).toBe(HTML_BASE);
  });

  it('no depende de ningún script inline: el resultado no añade ninguna etiqueta <script>', () => {
    const resultado = pintarTemaEnHtml(HTML_BASE, `${NOMBRE_COOKIE_TEMA}=claro`);
    expect(resultado).not.toContain('<script>');
  });

  it('tolera atributos añadidos por el build (data-beasties-container del inlining de CSS crítico)', () => {
    const htmlConBeasties =
      '<!doctype html><html lang="es-ES" data-beasties-container><head></head><body></body></html>';
    const resultado = pintarTemaEnHtml(htmlConBeasties, `${NOMBRE_COOKIE_TEMA}=claro`);
    expect(resultado).toContain('data-theme="light"');
    expect(resultado).toContain('data-beasties-container');
    expect(resultado).toContain('lang="es-ES"');
  });

  it('no duplica data-theme si ya estuviera presente en el HTML renderizado', () => {
    const htmlConTemaPrevio =
      '<!doctype html><html lang="es-ES" data-theme="dark"><head></head><body></body></html>';
    const resultado = pintarTemaEnHtml(htmlConTemaPrevio, `${NOMBRE_COOKIE_TEMA}=claro`);
    expect(resultado).toContain('<html lang="es-ES" data-theme="light">');
    expect(resultado.match(/data-theme=/g)).toHaveLength(1);
  });

  describe('cuando no hay ninguna etiqueta <html> en el HTML renderizado', () => {
    const HTML_SIN_ETIQUETA = '<!doctype html><head></head><body></body>';

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('no falla: devuelve el HTML sin tocar en vez de romper el renderizado', () => {
      const resultado = pintarTemaEnHtml(HTML_SIN_ETIQUETA, `${NOMBRE_COOKIE_TEMA}=claro`);
      expect(resultado).toBe(HTML_SIN_ETIQUETA);
    });

    it('no falla en silencio: avisa por consola en desarrollo para que no pase inadvertido', () => {
      const avisos = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      pintarTemaEnHtml(HTML_SIN_ETIQUETA, `${NOMBRE_COOKIE_TEMA}=claro`);
      expect(avisos).toHaveBeenCalledTimes(1);
    });
  });
});
