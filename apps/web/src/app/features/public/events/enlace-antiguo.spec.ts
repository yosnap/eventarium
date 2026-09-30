import { describe, expect, it } from 'vitest';

import { coincideConEnlaceAntiguo } from './enlace-antiguo';

describe('coincideConEnlaceAntiguo', () => {
  it('reconoce /eventos/:slug y su cola, no el directorio /eventos', () => {
    const segmento = (path: string) => ({ path, parameters: {} }) as never;
    expect(coincideConEnlaceAntiguo([segmento('eventos')])).toBeNull();
    expect(coincideConEnlaceAntiguo([segmento('eventos'), segmento('x')])).not.toBeNull();
    expect(
      coincideConEnlaceAntiguo([segmento('eventos'), segmento('x'), segmento('programa')]),
    ).not.toBeNull();
    expect(coincideConEnlaceAntiguo([segmento('otra'), segmento('x')])).toBeNull();
    expect(coincideConEnlaceAntiguo([segmento('eventos'), segmento('../x')])).toBeNull();
  });
});
