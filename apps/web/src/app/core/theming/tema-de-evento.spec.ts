import { Component, provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { plantillaDeTemaDePrueba } from '../../../testing/branding.fixture';
import { temaDeEvento } from './tema-de-evento';

@Component({ selector: 'app-pagina-de-evento', template: '' })
class PaginaDeEvento {
  readonly aplicarTema = temaDeEvento();
}

const ruta = { snapshot: { paramMap: convertToParamMap({ slug: 'evento-a' }) } };

function abrirPagina(slug: string): ComponentFixture<PaginaDeEvento> {
  ruta.snapshot.paramMap = convertToParamMap({ slug });
  return TestBed.createComponent(PaginaDeEvento);
}

const ambito = (): string | null => document.body.getAttribute('data-ambito');
const microtarea = (): Promise<void> => new Promise((resolve) => queueMicrotask(resolve));

describe('temaDeEvento', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: ActivatedRoute, useValue: ruta }],
    });
  });

  afterEach(() => {
    document.getElementById('tema-evento')?.remove();
    document.body.removeAttribute('data-ambito');
  });

  it('aplica la plantilla del evento al llegar los datos', () => {
    abrirPagina('evento-a').componentInstance.aplicarTema(plantillaDeTemaDePrueba());

    expect(ambito()).toBe('evento');
    expect(document.getElementById('tema-evento')?.textContent).toContain('[data-ambito="evento"]');
  });

  it('quita el ámbito al salir del evento para no dejarlo pegado en el resto del sitio', async () => {
    const ficha = abrirPagina('evento-a');
    ficha.componentInstance.aplicarTema(plantillaDeTemaDePrueba());

    ficha.destroy();
    await microtarea();

    expect(ambito()).toBeNull();
  });

  it('al pasar a otra página del mismo evento, el tema sigue puesto sin esperar a la API', async () => {
    const ficha = abrirPagina('evento-a');
    ficha.componentInstance.aplicarTema(plantillaDeTemaDePrueba());

    ficha.destroy();
    abrirPagina('evento-a');
    await microtarea();

    expect(ambito()).toBe('evento');
  });

  it('al pasar a otro evento no arrastra el tema del anterior', async () => {
    const ficha = abrirPagina('evento-a');
    ficha.componentInstance.aplicarTema(plantillaDeTemaDePrueba());

    ficha.destroy();
    abrirPagina('evento-b');
    await microtarea();

    expect(ambito()).toBeNull();
  });
});
