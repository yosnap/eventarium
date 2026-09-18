import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';
import { AccountMenu } from './account-menu';

describe('AccountMenu', () => {
  function configurar() {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    }).compileComponents();
  }

  function crear(email = 'persona@example.com', nuevaOrganizacion = false) {
    configurar();
    const fixture = TestBed.createComponent(AccountMenu);
    fixture.componentRef.setInput('email', email);
    fixture.componentRef.setInput('nuevaOrganizacion', nuevaOrganizacion);
    fixture.detectChanges();
    return fixture;
  }

  it('el disparador muestra el email', () => {
    const fixture = crear('alguien@ejemplo.com');
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;
    expect(disparador.textContent).toContain('alguien@ejemplo.com');
  });

  it('abre con click y ofrece "Mi cuenta" y "Cambiar de espacio de trabajo"', () => {
    const fixture = crear();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;

    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
    disparador.click();
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(false);

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).toContain('/dashboard/account');
    expect(enlaces).toContain('/espacio-de-trabajo');
  });

  it('sin `nuevaOrganizacion`, no ofrece "Nueva organización"', () => {
    const fixture = crear('persona@example.com', false);
    const raiz = fixture.nativeElement as HTMLElement;
    (raiz.querySelector('.disparador') as HTMLButtonElement).click();
    fixture.detectChanges();

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).not.toContain('/crear-organizacion');
  });

  it('con `nuevaOrganizacion`, ofrece "Nueva organización"', () => {
    const fixture = crear('persona@example.com', true);
    const raiz = fixture.nativeElement as HTMLElement;
    (raiz.querySelector('.disparador') as HTMLButtonElement).click();
    fixture.detectChanges();

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).toContain('/crear-organizacion');
  });

  it('"Cerrar sesión" emite el evento y cierra el menú', () => {
    const fixture = crear();
    const raiz = fixture.nativeElement as HTMLElement;
    const emitido = vi.fn();
    fixture.componentInstance.cerrarSesion.subscribe(emitido);

    (raiz.querySelector('.disparador') as HTMLButtonElement).click();
    fixture.detectChanges();
    const boton = Array.from(raiz.querySelectorAll('button[role="option"]')).find((b) =>
      b.textContent?.includes('Cerrar sesión'),
    ) as HTMLButtonElement;
    boton.click();
    fixture.detectChanges();

    expect(emitido).toHaveBeenCalled();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
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

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = crear();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
