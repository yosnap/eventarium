import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, it } from 'vitest';

import { CATEGORIAS, StyleGuidePage } from './style-guide-page';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

/**
 * A diferencia de la versión anterior de esta pantalla, el catálogo sí entra en la
 * suite de axe. Con las secciones en pestañas ya no hay una sola página con todo
 * montado a la vez, así que el recorrido axe da una vuelta por cada pestaña: entre
 * todas siguen viéndose todos los componentes de `shared/ui/`. Se comprueba en los
 * dos temas del sistema.
 */
describe('StyleGuidePage', () => {
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

  async function montar(): Promise<ComponentFixture<StyleGuidePage>> {
    const fixture = TestBed.createComponent(StyleGuidePage);
    await fixture.whenStable();
    return fixture;
  }

  for (const categoria of CATEGORIAS) {
    it(`la pestaña ${categoria} no viola accesibilidad`, async () => {
      const fixture = await montar();
      (fixture.componentInstance as unknown as { categoria: { set(v: string): void } }).categoria.set(
        categoria,
      );
      await fixture.whenStable();
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    });
  }
});
