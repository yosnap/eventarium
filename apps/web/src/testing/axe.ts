import axe, { type AxeResults, type RunOptions } from 'axe-core';
import { expect } from 'vitest';

/**
 * Reglas WCAG 2.1 nivel A y AA. Se fija el conjunto en lugar de usar el de por
 * defecto para que una actualización de axe no cambie en silencio lo que se exige.
 */
const OPCIONES: RunOptions = {
  runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
};

export async function analizarAccesibilidad(elemento: Element): Promise<AxeResults> {
  return axe.run(elemento, OPCIONES);
}

/**
 * Comprueba que no hay **ninguna** violación, del impacto que sea.
 *
 * No se filtra por severidad: una violación «menor» de axe sigue siendo una barrera
 * real para alguien, y el compromiso del proyecto es WCAG 2.1 AA completo.
 */
export async function esperarSinViolacionesDeAccesibilidad(elemento: Element): Promise<void> {
  const resultado = await analizarAccesibilidad(elemento);
  const detalle = resultado.violations
    .map((v) => `- [${v.impact ?? 'sin impacto'}] ${v.id}: ${v.help}`)
    .join('\n');
  expect(resultado.violations, `Violaciones de accesibilidad:\n${detalle}`).toEqual([]);
}
