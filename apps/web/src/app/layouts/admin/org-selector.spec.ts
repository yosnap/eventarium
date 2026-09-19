import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { OrgSelector } from './org-selector';

function organizaciones() {
  return [
    { organization_id: 'org-1', name: 'Acme' },
    { organization_id: 'org-2', name: 'IA Week' },
  ];
}

describe('OrgSelector', () => {
  let fixture: ComponentFixture<OrgSelector>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
    fixture = TestBed.createComponent(OrgSelector);
    fixture.componentRef.setInput('organizaciones', organizaciones());
    fixture.componentRef.setInput('activaId', 'org-1');
    fixture.detectChanges();
  });

  function disparador(): HTMLButtonElement {
    return fixture.nativeElement.querySelector('.disparador') as HTMLButtonElement;
  }

  function pulsar(key: string): void {
    disparador().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
  }

  /** El prefijo del id de opción incluye el contador de instancia del
   * componente; se lee del DOM en lugar de suponerlo. */
  function idDeOpcion(indice: number): string {
    return fixture.nativeElement.querySelectorAll('[role="option"]')[indice].id;
  }

  it('el menú está cerrado por defecto y abre con el botón marcando expandido', async () => {
    expect(disparador().getAttribute('aria-expanded')).toBe('false');
    disparador().click();
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-expanded')).toBe('true');
    expect(fixture.nativeElement.querySelector('[role="listbox"]').hidden).toBe(false);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('la organización activa está marcada como seleccionada', async () => {
    disparador().click();
    await fixture.whenStable();

    const activa = fixture.nativeElement.querySelector('[aria-selected="true"]') as HTMLElement;
    expect(activa).not.toBeNull();
    expect(activa.textContent).toContain('Acme');
  });

  it('cambiar a otra organización emite su id', () => {
    disparador().click();
    fixture.detectChanges();

    let emitida: string | null = null;
    fixture.componentInstance.cambiar.subscribe((id) => (emitida = id));
    (fixture.nativeElement.querySelector('button[role="option"]') as HTMLButtonElement).click();
    expect(emitida).toBe('org-2');
  });

  it('Escape cierra el menú', async () => {
    disparador().click();
    await fixture.whenStable();

    pulsar('Escape');
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-expanded')).toBe('false');
  });

  it('las flechas mueven la opción activa por aria-activedescendant, con vuelta', async () => {
    disparador().click();
    await fixture.whenStable();

    expect(disparador().getAttribute('aria-activedescendant')).toBe(idDeOpcion(0));

    pulsar('ArrowDown');
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-activedescendant')).toBe(idDeOpcion(1));

    // Última opción: «Nueva organización». Una más vuelve a la primera.
    pulsar('ArrowDown');
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-activedescendant')).toBe(idDeOpcion(2));

    pulsar('ArrowDown');
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-activedescendant')).toBe(idDeOpcion(0));

    pulsar('ArrowUp');
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-activedescendant')).toBe(idDeOpcion(2));
  });

  it('Enter activa la opción activa (cambiar de organización)', () => {
    disparador().click();
    fixture.detectChanges();

    let emitida: string | null = null;
    fixture.componentInstance.cambiar.subscribe((id) => (emitida = id));

    pulsar('ArrowDown');
    fixture.detectChanges();
    pulsar('Enter');
    expect(emitida).toBe('org-2');
  });

  it('Enter con la opción activa en «Nueva organización» navega al alta', async () => {
    const router = TestBed.inject(Router);
    const navegacion = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true as never);

    disparador().click();
    await fixture.whenStable();

    pulsar('End');
    await fixture.whenStable();
    pulsar('Enter');

    expect(navegacion).toHaveBeenCalled();
    // routerLink navega con un UrlTree; su string es la ruta destino.
    expect((navegacion.mock.calls[0][0] as unknown as { toString(): string }).toString()).toBe(
      '/crear-organizacion',
    );
  });

  it('Enter sobre el disparador cerrado abre el menú', async () => {
    pulsar('Enter');
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-expanded')).toBe('true');
  });

  it('ArrowDown sobre el disparador cerrado abre el menú con la primera opción activa', async () => {
    pulsar('ArrowDown');
    await fixture.whenStable();
    expect(disparador().getAttribute('aria-expanded')).toBe('true');
    expect(disparador().getAttribute('aria-activedescendant')).toBe(idDeOpcion(0));
  });
});
