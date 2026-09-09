import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { AdminNav, enlacesDeEvento } from './admin-nav';

function configurar() {
  TestBed.configureTestingModule({
    imports: [
      TranslocoTestingModule.forRoot({
        langs: { 'es-ES': es },
        translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
      }),
    ],
    providers: [provideZonelessChangeDetection(), provideRouter([])],
  });
}

describe('enlacesDeEvento', () => {
  it('sin pagos: no incluye entradas ni descuentos', () => {
    const enlaces = enlacesDeEvento('e1', false);
    expect(enlaces.some((e) => e.path.includes('entradas'))).toBe(false);
    expect(enlaces.some((e) => e.path.includes('descuentos'))).toBe(false);
    expect(enlaces.some((e) => e.path.includes('payments'))).toBe(false);
  });

  it('con pagos: incluye entradas, descuentos y pagos', () => {
    const enlaces = enlacesDeEvento('e1', true);
    expect(enlaces.some((e) => e.path.includes('entradas'))).toBe(true);
    expect(enlaces.some((e) => e.path.includes('descuentos'))).toBe(true);
    expect(enlaces.some((e) => e.path.includes('payments'))).toBe(true);
  });
});

describe('AdminNav', () => {
  it('sin is_superadmin: oculta superadministración y plantillas, pero no el catálogo', async () => {
    configurar();
    const fixture = TestBed.createComponent(AdminNav);
    fixture.componentRef.setInput('isSuperadmin', false);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).not.toContain('/admin/superadmin');
    expect(enlaces).not.toContain('/admin/superadmin/plantillas');
    expect(enlaces).toContain('/admin/estilo');
  });

  it('con is_superadmin: muestra superadministración y plantillas', async () => {
    configurar();
    const fixture = TestBed.createComponent(AdminNav);
    fixture.componentRef.setInput('isSuperadmin', true);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).toContain('/admin/superadmin');
    expect(enlaces).toContain('/admin/superadmin/plantillas');
  });

  it('sin evento activo: no pinta el grupo de evento', async () => {
    configurar();
    const fixture = TestBed.createComponent(AdminNav);
    fixture.componentRef.setInput('evento', null);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('#admin-nav-evento-titulo')).toBeNull();
  });

  it('con evento activo: pinta su nombre y la salida a eventos', async () => {
    configurar();
    const fixture = TestBed.createComponent(AdminNav);
    fixture.componentRef.setInput('evento', {
      id: 'e1',
      nombre: 'IA Week',
      cargando: false,
      aceptaPagos: false,
    });
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('#admin-nav-evento-titulo')?.textContent?.trim()).toBe('IA Week');
    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).toContain('/admin/events');
    expect(enlaces).toContain('/admin/events/e1');
  });
});
