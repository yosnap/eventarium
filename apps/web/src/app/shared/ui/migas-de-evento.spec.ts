import { describe, expect, it } from 'vitest';

import { migasDeEvento } from './migas-de-evento';

const publica = { slug: 'acme', name: 'Acme', page_public: true };
const privada = { ...publica, page_public: false };

describe('migasDeEvento', () => {
  it('en la ficha: Inicio › Organización › Evento, con el evento como texto', () => {
    const migas = migasDeEvento({
      inicio: 'Inicio',
      organizacion: publica,
      eventoSlug: 'iawic',
      eventoTitulo: 'IAWIC',
    });
    expect(migas.map((m) => m.label)).toEqual(['Inicio', 'Acme', 'IAWIC']);
    expect(migas[1].routerLink).toEqual(['/', 'acme']);
    expect(migas[2].routerLink).toBeUndefined();
  });

  it('la organización sin página pública no lleva enlace', () => {
    const migas = migasDeEvento({
      inicio: 'Inicio',
      organizacion: privada,
      eventoSlug: 'iawic',
      eventoTitulo: 'IAWIC',
    });
    expect(migas[1]).toEqual({ label: 'Acme', routerLink: undefined });
  });

  it('con cola, el evento pasa a ser un enlace y la cola lo sigue', () => {
    const migas = migasDeEvento({
      inicio: 'Inicio',
      organizacion: publica,
      eventoSlug: 'iawic',
      eventoTitulo: 'IAWIC',
      cola: [{ label: 'Programa' }],
    });
    expect(migas.map((m) => m.label)).toEqual(['Inicio', 'Acme', 'IAWIC', 'Programa']);
    expect(migas[2].routerLink).toEqual(['/', 'acme', 'iawic']);
  });
});
