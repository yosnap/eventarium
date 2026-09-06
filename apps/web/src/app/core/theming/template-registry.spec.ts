import { describe, expect, it } from 'vitest';

import { TEMPLATE_REGISTRY, resolveTemplate, templateExists } from './template-registry';

describe('registro de plantillas', () => {
  it('conoce las plantillas publicadas', () => {
    expect([...TEMPLATE_REGISTRY.keys()]).toEqual(['classic', 'minimal']);
    expect(templateExists('classic')).toBe(true);
    expect(templateExists('inexistente')).toBe(false);
  });

  it('carga cada plantilla de forma perezosa', async () => {
    const clasica = await resolveTemplate('classic')();
    const minima = await resolveTemplate('minimal')();

    expect(clasica).toBeDefined();
    expect(minima).toBeDefined();
    expect(clasica).not.toBe(minima);
  });

  it('cae en classic si la clave no existe o falta', async () => {
    const porDefecto = await resolveTemplate('inexistente')();
    const sinClave = await resolveTemplate(null)();
    const clasica = await resolveTemplate('classic')();

    expect(porDefecto).toBe(clasica);
    expect(sinClave).toBe(clasica);
  });
});
