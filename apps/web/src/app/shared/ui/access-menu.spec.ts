import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';
import { AccessMenu } from './access-menu';

describe('AccessMenu', () => {
  function crear() {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    }).compileComponents();
    const fixture = TestBed.createComponent(AccessMenu);
    fixture.detectChanges();
    return fixture;
  }

  it('abre con click y ofrece "Iniciar sesión" y "Crear cuenta"', () => {
    const fixture = crear();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;

    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
    disparador.click();
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(false);

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).toContain('/acceder');
    expect(enlaces).toContain('/registro');
  });

  it('Escape cierra el menú', () => {
    const fixture = crear();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;
    disparador.click();
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(false);

    disparador.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
  });

  it('clic fuera cierra el menú', () => {
    const fixture = crear();
    const raiz = fixture.nativeElement as HTMLElement;
    (raiz.querySelector('.disparador') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(false);

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
  });

  it('ArrowDown mueve la opción activa y Enter la activa', () => {
    const fixture = crear();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;
    disparador.click();
    fixture.detectChanges();

    disparador.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    fixture.detectChanges();
    expect(disparador.getAttribute('aria-activedescendant')).toContain('opcion-1');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = crear();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
