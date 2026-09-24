import { describe, expect, it, vi } from 'vitest';

const falso = { map: () => 'mapa' };

vi.mock('leaflet', () => ({ default: falso }));

describe('cargarLeaflet', () => {
  it('desenvuelve el `default` que deja la build de producción', async () => {
    const { cargarLeaflet } = await import('./leaflet-loader');
    expect(await cargarLeaflet()).toBe(falso);
  });
});
