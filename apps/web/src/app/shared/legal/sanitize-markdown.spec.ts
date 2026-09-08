import { describe, expect, it } from 'vitest';

import { markdownToSafeHtml } from './sanitize-markdown';

describe('markdownToSafeHtml', () => {
  it('convierte párrafos, negrita y listas', () => {
    const html = markdownToSafeHtml('**Hola**\n\n- uno\n- dos');
    expect(html).toContain('<strong>Hola</strong>');
    expect(html).toContain('<ul>');
    expect(html).toContain('<li>uno</li>');
  });

  it('convierte enlaces conservando solo el atributo href', () => {
    const html = markdownToSafeHtml('[AEPD](https://www.aepd.es)');
    expect(html).toContain('<a href="https://www.aepd.es">AEPD</a>');
  });

  it('elimina un <script> guardado como contenido legal', () => {
    const html = markdownToSafeHtml('Texto normal.\n\n<script>alert(1)</script>');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('alert(1)');
  });

  it('elimina atributos on* aunque vengan en una etiqueta permitida', () => {
    const html = markdownToSafeHtml('<p onclick="alert(1)">hola</p>');
    expect(html).not.toContain('onclick');
  });

  it('elimina un iframe incrustado', () => {
    const html = markdownToSafeHtml('<iframe src="https://malicioso.example"></iframe>');
    expect(html).not.toContain('<iframe');
  });

  it('no interpreta el Markdown de encabezados (fuera de la lista blanca)', () => {
    const html = markdownToSafeHtml('# Título');
    expect(html).not.toContain('<h1');
  });
});
