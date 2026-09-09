import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { JSDOM } from 'jsdom';
import { describe, expect, it } from 'vitest';

/**
 * Puerta previa a todo lo demás (entregable 0 de la fase de fundamentos): si esto no
 * está en verde, ningún test posterior sobre «los dos temas» comprueba nada real. Ver
 * `setup-styles.ts` y `apps/web/angular.json` (target `test`, `setupFiles`).
 */
describe('infraestructura de estilos en el entorno de test', () => {
  it('la hoja de estilo real está cargada: --bg tiene valor en :root', () => {
    const valor = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
    expect(valor).not.toBe('');
  });

  it('--bg cambia con data-theme="light"', () => {
    // Documento jsdom aislado, no el `document` global compartido por toda la suite:
    // verificado que, tras alternar `data-theme` sobre el documento global ya
    // computado por decenas de tests anteriores, `getComputedStyle` puede devolver un
    // valor de `--bg` obsoleto (comprobado con las reglas CSSOM reales: las dos
    // existen, con valores distintos, y aun así la lectura no cambiaba) — una
    // limitación de caché de jsdom al recomputar tras mutar un atributo en un
    // documento con mucho histórico de estilos ya resueltos, no un fallo de la hoja.
    // Un documento recién creado no tiene ese histórico y computa de forma fiable.
    const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>');
    const { document: doc, getComputedStyle: computado } = dom.window;

    const estilo = doc.createElement('style');
    estilo.textContent = readFileSync(join(import.meta.dirname, '../styles/tokens.css'), 'utf-8');
    doc.head.appendChild(estilo);

    const oscuro = computado(doc.documentElement).getPropertyValue('--bg').trim();
    expect(oscuro).not.toBe('');

    doc.documentElement.setAttribute('data-theme', 'light');
    const claro = computado(doc.documentElement).getPropertyValue('--bg').trim();

    expect(claro).not.toBe('');
    expect(claro).not.toBe(oscuro);
  });
});
