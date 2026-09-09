import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, it } from 'vitest';

import { StyleGuidePage } from './style-guide-page';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

/**
 * A diferencia de la versión anterior de esta pantalla, el catálogo sí entra en la
 * suite de axe: reúne todos los componentes de `shared/ui/` a la vez, así que es
 * donde antes se detecta una regresión de contraste o de estructura. Se comprueba en
 * los dos temas del sistema.
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

  it('el catálogo completo no viola accesibilidad en tema oscuro', async () => {
    const fixture = await montar();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el catálogo completo no viola accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const fixture = await montar();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
