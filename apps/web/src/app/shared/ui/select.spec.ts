import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Select, type SelectOption } from './select';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';

const OPCIONES: readonly SelectOption[] = [
  { value: 'valencia', label: 'Valencia' },
  { value: 'barcelona', label: 'Barcelona' },
  { value: 'online', label: 'Online' },
];

/** Los dos temas del sistema; cada comprobación de axe se repite en ambos. */
const TEMAS = ['oscuro', 'claro'] as const;

function fijarTema(tema: (typeof TEMAS)[number]): void {
  if (tema === 'claro') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}

describe('Select', () => {
  let fixture: ComponentFixture<Select>;
  let boton: HTMLButtonElement;
  let lista: HTMLUListElement;
  let nativo: HTMLSelectElement;

  // jsdom no implementa Element.scrollIntoView; se mockea para poder comprobar que
  // se llama al desplazar la opción activa por teclado (bug alto n.º 4).
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }

  async function montar(entradas: Record<string, unknown> = {}): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [Select],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(Select);
    fixture.componentRef.setInput('label', 'Ciudad');
    fixture.componentRef.setInput('options', OPCIONES);
    for (const [nombre, valor] of Object.entries(entradas)) {
      fixture.componentRef.setInput(nombre, valor);
    }
    await fixture.whenStable();
    boton = fixture.nativeElement.querySelector('.sel__btn') as HTMLButtonElement;
    lista = fixture.nativeElement.querySelector('.sel__list') as HTMLUListElement;
    nativo = fixture.nativeElement.querySelector('select') as HTMLSelectElement;
  }

  function opciones(): HTMLLIElement[] {
    return Array.from(lista.querySelectorAll('.sel__o'));
  }

  function pulsar(tecla: string): void {
    boton.dispatchEvent(new KeyboardEvent('keydown', { key: tecla, bubbles: true, cancelable: true }));
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  beforeEach(async () => {
    await montar({ placeholder: 'Cualquier ciudad' });
  });

  it('muestra el placeholder en el botón cuando no hay valor elegido', () => {
    expect(boton.textContent?.trim()).toBe('Cualquier ciudad');
    expect(boton.getAttribute('aria-haspopup')).toBe('listbox');
    expect(boton.getAttribute('aria-expanded')).toBe('false');
  });

  it('el <select> nativo interno mantiene el valor sincronizado en todo momento', async () => {
    expect(nativo.value).toBe('');

    fixture.componentRef.setInput('value', 'barcelona');
    await fixture.whenStable();
    expect(nativo.value).toBe('barcelona');
    expect(boton.textContent?.trim()).toBe('Barcelona');

    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('Enter');
    await fixture.whenStable();
    // Se compara contra un valor conocido (no contra sí mismo): tras dos ArrowDown
    // desde «Barcelona» (activa antes de abrir, por el valor vigente) se llega a
    // «Online», y Enter la confirma.
    expect(nativo.value).toBe('online');
    expect(fixture.componentInstance.value()).toBe('online');
  });

  it('sincroniza el <select> nativo con el valor inicial ya en el primer render', async () => {
    await montar({ placeholder: 'Cualquier ciudad', value: 'barcelona' });
    expect(nativo.value).toBe('barcelona');
    expect(boton.textContent?.trim()).toBe('Barcelona');
  });

  it('el nombre accesible del botón incluye la etiqueta y la opción elegida', async () => {
    fixture.componentRef.setInput('value', 'barcelona');
    await fixture.whenStable();

    const etiqueta = fixture.nativeElement.querySelector('.rotulo') as HTMLElement;
    const idsReferenciados = boton.getAttribute('aria-labelledby')?.split(' ') ?? [];
    expect(idsReferenciados).toEqual([etiqueta.id, boton.id]);
    // El nombre accesible completo (etiqueta + opción elegida) sale de concatenar
    // el texto de ambos elementos referenciados, tal y como lo resolvería un
    // lector de pantalla.
    expect(`${etiqueta.textContent} ${boton.textContent}`.trim()).toContain('Ciudad');
    expect(`${etiqueta.textContent} ${boton.textContent}`.trim()).toContain('Barcelona');
  });

  it('el id externo (fieldId) apunta al botón enfocable, no al <select> nativo oculto', async () => {
    await montar({ placeholder: 'Cualquier ciudad', fieldId: 'ciudad-miembro' });
    expect(boton.id).toBe('ciudad-miembro');
    expect(nativo.id).not.toBe('ciudad-miembro');
    // El id externo debe resolver, vía document.getElementById, al elemento que
    // de verdad puede recibir el foco (como haría un enlace de app-error-summary).
    const destino = document.getElementById('ciudad-miembro');
    expect(destino).toBe(boton);
  });

  it('desplaza la opción activa a la vista al navegar con flechas más allá del alto visible', async () => {
    const muchasOpciones: SelectOption[] = Array.from({ length: 20 }, (_, i) => ({
      value: `o${i}`,
      label: `Opción ${i}`,
    }));
    await montar({ options: muchasOpciones });

    const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView');
    for (const opcion of muchasOpciones) {
      void opcion; // solo interesa repetir ArrowDown tantas veces como opciones hay
      pulsar('ArrowDown');
      await fixture.whenStable();
    }

    expect(scrollSpy).toHaveBeenCalled();
    const ultimaLlamada = scrollSpy.mock.calls.at(-1)?.[0];
    expect(ultimaLlamada).toMatchObject({ block: 'nearest' });
    scrollSpy.mockRestore();
  });

  it('al reabrir tras Escape, la opción activa vuelve a corresponder al valor vigente', async () => {
    fixture.componentRef.setInput('value', 'valencia');
    await fixture.whenStable();

    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('Escape');
    await fixture.whenStable();

    pulsar('ArrowDown');
    await fixture.whenStable();
    const activaId = boton.getAttribute('aria-activedescendant');
    const opcionActiva = opciones().find((li) => li.id === activaId);
    expect(opcionActiva?.textContent?.trim()).toBe('Valencia');
  });

  it('la búsqueda por letra reconoce vocales acentuadas y la ñ', async () => {
    await montar({
      options: [
        { value: 'a', label: 'Ávila' },
        { value: 'b', label: 'Ñora' },
      ],
    });
    pulsar('Á');
    await fixture.whenStable();
    const activaA = boton.getAttribute('aria-activedescendant');
    expect(opciones().find((li) => li.id === activaA)?.textContent?.trim()).toBe('Ávila');

    // Se remonta para partir de un buffer de búsqueda limpio (el buffer de la letra
    // anterior solo caduca tras PAUSA_BUSQUEDA_MS de inactividad real).
    await montar({
      options: [
        { value: 'a', label: 'Ávila' },
        { value: 'b', label: 'Ñora' },
      ],
    });
    pulsar('Ñ');
    await fixture.whenStable();
    const activaB = boton.getAttribute('aria-activedescendant');
    expect(opciones().find((li) => li.id === activaB)?.textContent?.trim()).toBe('Ñora');
  });

  it('ArrowDown abre la lista y, con la lista abierta, mueve la opción activa', async () => {
    pulsar('ArrowDown');
    await fixture.whenStable();
    expect(boton.getAttribute('aria-expanded')).toBe('true');
    expect(lista.hidden).toBe(false);

    const activaAntes = boton.getAttribute('aria-activedescendant');
    pulsar('ArrowDown');
    await fixture.whenStable();
    const activaDespues = boton.getAttribute('aria-activedescendant');
    expect(activaDespues).not.toBe(activaAntes);
    // La primera opción real es «Valencia» (índice 1: el índice 0 es el placeholder,
    // deshabilitado); la segunda pulsación avanza a «Barcelona» (índice 2).
    expect(opciones()[1].id).toBe(activaAntes);
    expect(opciones()[2].id).toBe(activaDespues);
  });

  it('Home y End saltan a la primera y última opción', async () => {
    pulsar('ArrowDown');
    await fixture.whenStable();

    pulsar('End');
    await fixture.whenStable();
    expect(boton.getAttribute('aria-activedescendant')).toBe(opciones().at(-1)?.id);

    pulsar('Home');
    await fixture.whenStable();
    // La primera opción de la lista es el placeholder (deshabilitado): Home debe
    // saltar a la primera opción real seleccionable, no a la deshabilitada.
    expect(boton.getAttribute('aria-activedescendant')).toBe(opciones()[1].id);
  });

  it('una letra busca la siguiente opción cuyo texto empieza por ella', async () => {
    pulsar('b');
    await fixture.whenStable();
    expect(boton.getAttribute('aria-expanded')).toBe('true');
    const activa = boton.getAttribute('aria-activedescendant');
    const opcionActiva = opciones().find((li) => li.id === activa);
    expect(opcionActiva?.textContent?.trim()).toBe('Barcelona');
  });

  it('Intro elige la opción activa y cierra la lista', async () => {
    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('Enter');
    await fixture.whenStable();

    expect(boton.getAttribute('aria-expanded')).toBe('false');
    expect(fixture.componentInstance.value()).toBe('online');
    expect(boton.textContent?.trim()).toBe('Online');
  });

  it('Escape cierra sin cambiar el valor y devuelve el foco al botón', async () => {
    fixture.componentRef.setInput('value', 'valencia');
    await fixture.whenStable();

    pulsar('ArrowDown');
    await fixture.whenStable();
    pulsar('ArrowDown');
    await fixture.whenStable();
    boton.focus();
    pulsar('Escape');
    await fixture.whenStable();

    expect(boton.getAttribute('aria-expanded')).toBe('false');
    expect(fixture.componentInstance.value()).toBe('valencia');
    expect(document.activeElement).toBe(boton);
  });

  it('se abre hacia arriba cuando no cabe hacia abajo', async () => {
    const rectOriginal = boton.getBoundingClientRect.bind(boton);
    boton.getBoundingClientRect = () =>
      ({ ...rectOriginal(), bottom: 700, top: 650 }) as DOMRect;
    const alturaOriginal = window.innerHeight;
    Object.defineProperty(window, 'innerHeight', { value: 720, configurable: true });

    boton.click();
    await fixture.whenStable();

    const contenedorSel = fixture.nativeElement.querySelector('.sel') as HTMLElement;
    expect(contenedorSel.className).toContain('sel--up');

    Object.defineProperty(window, 'innerHeight', { value: alturaOriginal, configurable: true });
  });

  it('no violaciones de accesibilidad, cerrado y abierto, en ambos temas', async () => {
    for (const tema of TEMAS) {
      fijarTema(tema);
      await montar({ placeholder: 'Cualquier ciudad' });
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);

      boton.click();
      await fixture.whenStable();
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    }
  });
});
