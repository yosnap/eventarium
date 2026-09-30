import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';
import { DatetimePicker } from './datetime-picker';

describe('DatetimePicker', () => {
  let fixture: ComponentFixture<DatetimePicker>;
  let botonFecha: HTMLButtonElement;
  let cajaHora: HTMLInputElement;
  let nativo: HTMLInputElement;

  async function montar(entradas: Record<string, unknown> = {}): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [
        DatetimePicker,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(DatetimePicker);
    fixture.componentRef.setInput('label', 'Fecha y hora de inicio');
    for (const [nombre, valor] of Object.entries(entradas)) {
      fixture.componentRef.setInput(nombre, valor);
    }
    await fixture.whenStable();
    botonFecha = fixture.nativeElement.querySelector('.dt__btn') as HTMLButtonElement;
    cajaHora = fixture.nativeElement.querySelector('#evento-inicio-hora') as HTMLInputElement;
    nativo = fixture.nativeElement.querySelector('.dt__native') as HTMLInputElement;
  }

  function panel(tipo: 'fecha' | 'hora'): HTMLElement | null {
    return fixture.nativeElement.querySelector(
      tipo === 'fecha' ? '#evento-inicio-panel-fecha' : '#evento-inicio-panel-hora',
    ) as HTMLElement | null;
  }

  async function abrir(tipo: 'fecha' | 'hora'): Promise<HTMLElement> {
    const disparador =
      tipo === 'fecha'
        ? botonFecha
        : (fixture.nativeElement.querySelector('.dt__hora-saltos') as HTMLButtonElement);
    disparador.click();
    await fixture.whenStable();
    return panel(tipo) as HTMLElement;
  }

  async function escribirHora(texto: string): Promise<void> {
    cajaHora.value = texto;
    cajaHora.dispatchEvent(new Event('input', { bubbles: true }));
    await fixture.whenStable();
  }

  function hoyIso(): string {
    const actual = new Date();
    return `${actual.getFullYear()}-${String(actual.getMonth() + 1).padStart(2, '0')}-${String(
      actual.getDate(),
    ).padStart(2, '0')}`;
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  beforeEach(async () => {
    await montar({ fieldId: 'evento-inicio' });
  });

  it('sin valor: la etiqueta queda dentro del campo de fecha y la caja de hora vacía', () => {
    const etiqueta = fixture.nativeElement.querySelector('label') as HTMLLabelElement;
    expect(etiqueta.getAttribute('for')).toBe('evento-inicio');
    expect(botonFecha.textContent?.trim()).toBe('');
    expect(cajaHora.value).toBe('');
    expect(cajaHora.placeholder).toBe('--:--');
    expect(nativo.value).toBe('');
  });

  it('formatea el valor inicial: fecha en un campo y HH:MM en la caja', async () => {
    await montar({ fieldId: 'evento-inicio', value: '2026-10-01T09:30' });
    expect(nativo.value).toBe('2026-10-01T09:30');
    expect(botonFecha.textContent).toContain('oct');
    expect(cajaHora.value).toBe('09:30');
    // Con valor, la etiqueta flota (patrón de Input).
    const campo = fixture.nativeElement.querySelector('.campo') as HTMLElement;
    expect(campo.className).toContain('flotando');
  });

  it('elegir un día fija la fecha (hora por defecto 09:00) y cierra el calendario', async () => {
    const calendario = await abrir('fecha');

    // El panel abre en el mes en curso: se navega hasta octubre de 2026 con
    // la flecha de «mes siguiente».
    const titulo = () => calendario.querySelector('.dt__titulo')?.textContent ?? '';
    for (let i = 0; i < 24 && !titulo().includes('octubre de 2026'); i++) {
      (calendario.querySelectorAll('.dt__flecha')[1] as HTMLButtonElement).click();
      await fixture.whenStable();
    }

    const dia = Array.from(calendario.querySelectorAll('.dt__dia')).find(
      (celda) => celda.getAttribute('aria-label')?.includes('1 de octubre') ?? false,
    ) as HTMLButtonElement;
    dia.click();
    await fixture.whenStable();

    expect(fixture.componentInstance.value()).toBe('2026-10-01T09:00');
    expect(nativo.value).toBe('2026-10-01T09:00');
    expect(panel('fecha')).toBeNull();
    expect(document.activeElement).toBe(botonFecha);
  });

  it('escribir «935» en la caja fija la 09:35 de hoy sin abrir nada', async () => {
    await escribirHora('935');
    expect(fixture.componentInstance.value()).toBe(`${hoyIso()}T09:35`);
    expect(cajaHora.value).toBe('935'); // sin reformatear mientras se escribe

    cajaHora.dispatchEvent(new Event('blur', { bubbles: true }));
    await fixture.whenStable();
    expect(cajaHora.value).toBe('09:35'); // canónico al desenfocar
  });

  it('las flechas en la caja mueven de 5 en 5 minutos (y RePág, de hora en hora)', async () => {
    await montar({ fieldId: 'evento-inicio', value: '2026-10-01T09:58' });
    cajaHora.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true }),
    );
    await fixture.whenStable();
    expect(fixture.componentInstance.value()).toBe('2026-10-01T10:03');

    cajaHora.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'PageDown', bubbles: true, cancelable: true }),
    );
    await fixture.whenStable();
    expect(fixture.componentInstance.value()).toBe('2026-10-01T09:03');
  });

  it('los saltos del panel ajustan la hora sin fecha previa (hoy 00:00 + 1 h)', async () => {
    const panelHora = await abrir('hora');
    const masUnaHora = Array.from(panelHora.querySelectorAll('.dt__salto')).find((b) =>
      b.textContent?.includes('+1 h'),
    ) as HTMLButtonElement;
    masUnaHora.click();
    await fixture.whenStable();

    expect(fixture.componentInstance.value()).toBe(`${hoyIso()}T01:00`);
    expect(panel('hora')).not.toBeNull(); // el panel sigue abierto para seguir ajustando
  });

  it('«Ahora» fija la hora vigente y «Listo» cierra devolviendo el foco a la caja', async () => {
    await montar({ fieldId: 'evento-inicio', value: '2026-10-01T09:30' });
    const panelHora = await abrir('hora');

    const antes = new Date();
    (panelHora.querySelector('.dt__atajo') as HTMLButtonElement).click();
    await fixture.whenStable();

    const valor = fixture.componentInstance.value();
    expect(valor).toMatch(/^2026-10-01T\d{2}:\d{2}$/);
    const horaActual = `${String(antes.getHours()).padStart(2, '0')}:${String(
      antes.getMinutes(),
    ).padStart(2, '0')}`;
    expect(valor.split('T')[1]).toBe(horaActual);

    (panelHora.querySelector('.dt__listo') as HTMLButtonElement).click();
    await fixture.whenStable();
    expect(panel('hora')).toBeNull();
    expect(document.activeElement).toBe(cajaHora);
  });

  it('Escape cierra el panel de hora y devuelve el foco a la caja', async () => {
    const panelHora = await abrir('hora');
    panelHora.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    );
    await fixture.whenStable();

    expect(panel('hora')).toBeNull();
    expect(document.activeElement).toBe(cajaHora);
  });

  it('escribir en el nativo oculto sincroniza ambos campos (mejora progresiva)', async () => {
    nativo.value = '2026-10-02T18:00';
    nativo.dispatchEvent(new Event('input'));
    await fixture.whenStable();

    expect(fixture.componentInstance.value()).toBe('2026-10-02T18:00');
    expect(cajaHora.value).toBe('18:00');
    expect(botonFecha.textContent).toContain('oct');
  });

  it('cerrado y con cada panel abierto no tiene violaciones de accesibilidad', async () => {
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    await abrir('fecha');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    botonFecha.click(); // cierra
    await fixture.whenStable();
    await abrir('hora');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  }, 20_000);
});
