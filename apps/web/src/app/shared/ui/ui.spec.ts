import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, Type, provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Alert } from './alert';
import { Button } from './button';
import { Card } from './card';
import { Chip } from './chip';
import { DataTable, type DataTableColumn } from './data-table';
import { DynamicField } from './dynamic-field';
import { ErrorSummary } from './error-summary';
import { Input } from './input';
import { Textarea } from './textarea';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';

/** Los dos temas del sistema; cada componente se prueba en ambos. */
const TEMAS = ['oscuro', 'claro'] as const;

function fijarTema(tema: (typeof TEMAS)[number]): void {
  if (tema === 'claro') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
}

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

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
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

  it('el campo dinámico de tipo texto usa un app-input', async () => {
    const fixture = await montar(DynamicField, {
      field: {
        key: 'cargo',
        label: 'Cargo',
        field_type: 'text',
        options: null,
        is_required: false,
      },
    });
    expect(fixture.nativeElement.querySelector('app-input')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el campo dinámico de tipo selector enlaza etiqueta y opciones', async () => {
    const fixture = await montar(DynamicField, {
      field: {
        key: 'talla',
        label: 'Talla',
        field_type: 'select',
        options: { choices: ['S', 'M', 'L'] },
        is_required: true,
      },
    });

    const boton = fixture.nativeElement.querySelector('.sel__btn') as HTMLButtonElement;
    const select = fixture.nativeElement.querySelector('select') as HTMLSelectElement;
    const etiqueta = fixture.nativeElement.querySelector('.rotulo') as HTMLElement;
    // El nombre accesible del botón debe incluir tanto la etiqueta como la opción
    // elegida (que vive en el propio botón): patrón APG de combobox de solo lectura.
    expect(boton.getAttribute('aria-labelledby')).toBe(`${etiqueta.id} ${boton.id}`);
    expect(select.querySelectorAll('option').length).toBe(4); // placeholder + 3 opciones
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el campo dinámico de tipo booleano usa una casilla', async () => {
    const fixture = await montar(DynamicField, {
      field: {
        key: 'activo',
        label: 'Activo',
        field_type: 'boolean',
        options: null,
        is_required: false,
      },
      value: true,
    });

    const casilla = fixture.nativeElement.querySelector(
      'input[type="checkbox"]',
    ) as HTMLInputElement;
    expect(casilla.checked).toBe(true);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el resumen de errores no aparece con un único error', async () => {
    const fixture = await montar(ErrorSummary, {
      errores: [{ campoId: 'campo-1', mensaje: 'Error único.' }],
    });
    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
  });

  it('el resumen de errores enlaza cada entrada a su campo con más de un error', async () => {
    const fixture = await montar(ErrorSummary, {
      errores: [
        { campoId: 'campo-1', mensaje: 'Primer error.' },
        { campoId: 'campo-2', mensaje: 'Segundo error.' },
      ],
      titulo: 'Corrige lo siguiente:',
    });

    const enlaces = Array.from(fixture.nativeElement.querySelectorAll('a')) as HTMLAnchorElement[];
    expect(enlaces.map((enlace) => enlace.getAttribute('href'))).toEqual(['#campo-1', '#campo-2']);
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  describe('Button: variantes, modificadores y compatibilidad', () => {
    /** Anfitrión con las entradas de `Button` enlazadas, para variarlas en el test. */
    @Component({
      selector: 'app-anfitrion-boton-variante',
      imports: [Button],
      template: `
        <app-button [variant]="variant" [bloque]="bloque" [compacto]="compacto" [disabled]="disabled">
          Guardar cambios
        </app-button>
      `,
    })
    class AnfitrionBotonVariante {
      variant: 'primario' | 'secundario' | 'terciario' | 'peligro' = 'primario';
      bloque = false;
      compacto = false;
      disabled = false;
    }

    it('las variantes existentes siguen compilando y renderizando (sin regresión de API)', async () => {
      for (const variant of ['primario', 'secundario', 'peligro'] as const) {
        const fixture = await montar(AnfitrionBotonVariante);
        fixture.componentInstance.variant = variant;
        fixture.changeDetectorRef.markForCheck();
        await fixture.whenStable();
        const boton = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
        expect(boton.className).toContain(variant);
      }
    });

    it('acepta la variante nueva "terciario" y los modificadores "bloque"/"compacto"', async () => {
      const fixture = await montar(AnfitrionBotonVariante);
      fixture.componentInstance.variant = 'terciario';
      fixture.componentInstance.bloque = true;
      fixture.componentInstance.compacto = true;
      fixture.changeDetectorRef.markForCheck();
      await fixture.whenStable();

      const boton = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
      expect(boton.className).toContain('terciario');
      expect(boton.className).toContain('bloque');
      expect(boton.className).toContain('compacto');
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    for (const tema of TEMAS) {
      it(`en tema ${tema}, cada variante y el estado desactivado no violan accesibilidad`, async () => {
        fijarTema(tema);
        for (const variant of ['primario', 'secundario', 'terciario', 'peligro'] as const) {
          const fixture = await montar(AnfitrionBotonVariante);
          fixture.componentInstance.variant = variant;
          fixture.componentInstance.disabled = true;
          fixture.changeDetectorRef.markForCheck();
          await fixture.whenStable();
          await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
        }
      });
    }
  });

  describe('Chip: tonos y refuerzo por texto', () => {
    /** Anfitrión con etiqueta como texto, igual que se usa en la aplicación real. */
    @Component({
      selector: 'app-anfitrion-chip',
      imports: [Chip],
      template: `<app-chip [tone]="tone">Confirmado</app-chip>`,
    })
    class AnfitrionChip {
      tone: 'neutro' | 'ok' | 'espera' | 'apagado' = 'ok';
    }

    it('expone su etiqueta como texto, no solo como clase de color', async () => {
      const fixture = await montar(AnfitrionChip);
      expect(fixture.nativeElement.textContent).toContain('Confirmado');
      expect(fixture.nativeElement.querySelector('span')).not.toBeNull();
      expect(fixture.nativeElement.querySelector('button')).toBeNull();
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    for (const tema of TEMAS) {
      it(`en tema ${tema}, cada tono no viola accesibilidad`, async () => {
        fijarTema(tema);
        for (const tone of ['neutro', 'ok', 'espera', 'apagado'] as const) {
          const fixture = await montar(AnfitrionChip);
          fixture.componentInstance.tone = tone;
          fixture.changeDetectorRef.markForCheck();
          await fixture.whenStable();
          await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
        }
      });
    }
  });

  describe('Card: ranura opcional de acciones', () => {
    /** Anfitrión con contenido y ranura de acciones proyectados, como en producción. */
    @Component({
      selector: 'app-anfitrion-card',
      imports: [Card],
      template: `
        <app-card [heading]="heading">
          <p>Contenido de la tarjeta.</p>
          @if (conAcciones) {
            <button acciones type="button">Acción</button>
          }
        </app-card>
      `,
    })
    class AnfitrionCard {
      heading = 'Resumen';
      conAcciones = false;
    }

    it('sin la ranura de acciones renderiza igual que antes', async () => {
      const fixture = await montar(AnfitrionCard);
      expect(fixture.nativeElement.querySelector('[acciones]')).toBeNull();
      expect(fixture.nativeElement.textContent).toContain('Contenido de la tarjeta.');
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    it('con la ranura de acciones rellena, proyecta su contenido junto al título', async () => {
      const fixture = await montar(AnfitrionCard);
      fixture.componentInstance.conAcciones = true;
      fixture.changeDetectorRef.markForCheck();
      await fixture.whenStable();

      expect(fixture.nativeElement.querySelector('[acciones]')).not.toBeNull();
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    for (const tema of TEMAS) {
      it(`en tema ${tema} no viola accesibilidad`, async () => {
        fijarTema(tema);
        const fixture = await montar(AnfitrionCard);
        await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
      });
    }
  });

  describe('DataTable: envoltorio accesible', () => {
    /** Anfitrión con filas de datos proyectadas, como se usará en la fase 5. */
    @Component({
      selector: 'app-anfitrion-tabla',
      imports: [DataTable],
      template: `
        <app-data-table caption="Inscripciones" [columnas]="columnas">
          <tr>
            <td>Ana García</td>
            <td class="numerica">2</td>
          </tr>
        </app-data-table>
      `,
    })
    class AnfitrionTabla {
      columnas: readonly DataTableColumn[] = [
        { key: 'nombre', label: 'Nombre' },
        { key: 'entradas', label: 'Entradas', numerica: true },
      ];
    }

    it('envuelve una tabla real con caption, th[scope=col] y contenedor accesible por teclado', async () => {
      const fixture = await montar(AnfitrionTabla);

      const contenedor = fixture.nativeElement.querySelector('[role="region"]') as HTMLElement;
      expect(contenedor).not.toBeNull();
      expect(contenedor.getAttribute('tabindex')).toBe('0');
      expect(contenedor.getAttribute('aria-label')).toBe('Inscripciones');

      const caption = fixture.nativeElement.querySelector('caption') as HTMLElement;
      expect(caption?.textContent?.trim()).toBe('Inscripciones');

      const cabeceras = Array.from(
        fixture.nativeElement.querySelectorAll('th'),
      ) as HTMLTableCellElement[];
      expect(cabeceras).toHaveLength(2);
      expect(cabeceras.every((th) => th.getAttribute('scope') === 'col')).toBe(true);
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });

    for (const tema of TEMAS) {
      it(`en tema ${tema} no viola accesibilidad`, async () => {
        fijarTema(tema);
        const fixture = await montar(AnfitrionTabla);
        await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
      });
    }
  });

  describe('cobertura por temas de los componentes existentes', () => {
    for (const tema of TEMAS) {
      it(`Alert, Input y Textarea no violan accesibilidad en tema ${tema}`, async () => {
        fijarTema(tema);

        const alerta = await montar(Alert, { tone: 'error', title: 'Error' });
        await esperarSinViolacionesDeAccesibilidad(alerta.nativeElement);

        const campo = await montar(Input, { label: 'Correo electrónico' });
        await esperarSinViolacionesDeAccesibilidad(campo.nativeElement);

        const area = await montar(Textarea, { label: 'Descripción' });
        await esperarSinViolacionesDeAccesibilidad(area.nativeElement);
      });
    }
  });
});
