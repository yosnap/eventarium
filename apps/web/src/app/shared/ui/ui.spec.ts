import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, Type, provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import { Alert } from './alert';
import { Button } from './button';
import { Card } from './card';
import { Input } from './input';
import { Textarea } from './textarea';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';

/**
 * Anfitrión que proyecta texto en el botón, como se usa en la aplicación real. Un
 * botón vacío no tendría nombre accesible, y probarlo así no diría nada útil.
 */
@Component({
  selector: 'app-anfitrion-boton',
  imports: [Button],
  template: `<app-button>Guardar cambios</app-button>`,
})
class AnfitrionBoton {}

describe('componentes compartidos', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
  });

  /**
   * Monta un componente. Las entradas obligatorias se fijan antes de la primera
   * detección de cambios: si no, Angular falla al evaluar la plantilla.
   */
  async function montar<T>(
    componente: Type<T>,
    entradas: Record<string, unknown> = {},
  ): Promise<ComponentFixture<T>> {
    const fixture = TestBed.createComponent(componente);
    for (const [nombre, valor] of Object.entries(entradas)) {
      fixture.componentRef.setInput(nombre, valor);
    }
    await fixture.whenStable();
    return fixture;
  }

  it('el botón con texto no tiene violaciones de accesibilidad', async () => {
    const fixture = await montar(AnfitrionBoton);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el botón marca aria-busy mientras carga', async () => {
    const fixture = await montar(Button);
    fixture.componentRef.setInput('loading', true);
    await fixture.whenStable();

    const boton = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(boton.getAttribute('aria-busy')).toBe('true');
    expect(boton.disabled).toBe(true);
  });

  it('la alerta de error usa role="alert" y el resto role="status"', async () => {
    const fixture = await montar(Alert);
    fixture.componentRef.setInput('tone', 'error');
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();

    fixture.componentRef.setInput('tone', 'info');
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('[role="status"]')).not.toBeNull();
  });

  it('la tarjeta con título es una región etiquetada y accesible', async () => {
    const fixture = await montar(Card);
    fixture.componentRef.setInput('heading', 'Resumen');
    await fixture.whenStable();

    const seccion = fixture.nativeElement.querySelector('section') as HTMLElement;
    const idTitulo = seccion.getAttribute('aria-labelledby');
    expect(idTitulo).toBeTruthy();
    expect(fixture.nativeElement.querySelector(`#${idTitulo}`)?.textContent).toContain('Resumen');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el campo enlaza etiqueta y mensaje de error', async () => {
    const fixture = await montar(Input, {
      label: 'Correo electrónico',
      error: 'Escribe tu correo.',
    });

    const campo = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    const etiqueta = fixture.nativeElement.querySelector('label') as HTMLLabelElement;
    expect(etiqueta.getAttribute('for')).toBe(campo.id);
    expect(campo.getAttribute('aria-invalid')).toBe('true');

    const idError = campo.getAttribute('aria-describedby');
    expect(fixture.nativeElement.querySelector(`#${idError}`)?.textContent).toContain(
      'Escribe tu correo.',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el campo de contraseña alterna a texto plano con el botón de mostrar', async () => {
    const fixture = await montar(Input, { label: 'Contraseña', type: 'password' });

    const campo = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    const boton = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(campo.type).toBe('password');
    const etiquetaOculto = boton.getAttribute('aria-label');

    boton.click();
    await fixture.whenStable();
    expect(campo.type).toBe('text');
    // La etiqueta cambia entre «mostrar» y «ocultar»: el texto exacto depende de que
    // las traducciones ya estén cargadas en el momento de la comprobación, algo que
    // este test no controla; comprobar que cambia es la aserción robusta.
    expect(boton.getAttribute('aria-label')).not.toBe(etiquetaOculto);

    boton.click();
    await fixture.whenStable();
    expect(campo.type).toBe('password');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el campo muestra la ayuda solo mientras no hay error', async () => {
    const fixture = await montar(Input, { label: 'Contraseña', hint: 'Mínimo 8 caracteres.' });

    const campo = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(fixture.nativeElement.textContent).toContain('Mínimo 8 caracteres.');
    expect(campo.getAttribute('aria-describedby')).toBeTruthy();

    fixture.componentRef.setInput('error', 'Contraseña demasiado corta.');
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).not.toContain('Mínimo 8 caracteres.');
    expect(fixture.nativeElement.textContent).toContain('Contraseña demasiado corta.');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el área de texto enlaza etiqueta y mensaje de error', async () => {
    const fixture = await montar(Textarea, {
      label: 'Descripción',
      error: 'Escribe una descripción.',
    });

    const campo = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
    const etiqueta = fixture.nativeElement.querySelector('label') as HTMLLabelElement;
    expect(etiqueta.getAttribute('for')).toBe(campo.id);
    expect(campo.getAttribute('aria-invalid')).toBe('true');

    const idError = campo.getAttribute('aria-describedby');
    expect(fixture.nativeElement.querySelector(`#${idError}`)?.textContent).toContain(
      'Escribe una descripción.',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
