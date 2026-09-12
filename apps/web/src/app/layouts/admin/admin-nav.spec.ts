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

async function montar(plataforma: boolean) {
  configurar();
  const fixture = TestBed.createComponent(AdminNav);
  fixture.componentRef.setInput('plataforma', plataforma);
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

function enlacesDe(raiz: HTMLElement): (string | null)[] {
  return Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
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

  it('contabilidad aparece siempre, con o sin pagos habilitados', () => {
    expect(enlacesDeEvento('e1', false).some((e) => e.path.includes('contabilidad'))).toBe(true);
    expect(enlacesDeEvento('e1', true).some((e) => e.path.includes('contabilidad'))).toBe(true);
  });
});

describe('AdminNav — panel de organización', () => {
  it('pinta las secciones de la organización bajo /dashboard', async () => {
    const raiz = await montar(false);
    const enlaces = enlacesDe(raiz);

    expect(enlaces).toContain('/dashboard');
    expect(enlaces).toContain('/dashboard/events');
    expect(enlaces).toContain('/dashboard/roles');
  });

  it('no ofrece ningún enlace del panel de plataforma', async () => {
    // Ofrecerlos no solo sobra: manda a quien navega a un árbol donde el guard
    // lo va a rebotar.
    const raiz = await montar(false);
    const enlaces = enlacesDe(raiz);

    expect(enlaces).not.toContain('/admin');
    expect(enlaces).not.toContain('/admin/plantillas');
    expect(enlaces).not.toContain('/admin/suplantar');
  });

  it('sin evento activo: no pinta el grupo de evento', async () => {
    configurar();
    const fixture = TestBed.createComponent(AdminNav);
    fixture.componentRef.setInput('plataforma', false);
    fixture.componentRef.setInput('evento', null);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('#admin-nav-evento-titulo')).toBeNull();
  });

  it('con evento activo: pinta su nombre y la salida a eventos', async () => {
    configurar();
    const fixture = TestBed.createComponent(AdminNav);
    fixture.componentRef.setInput('plataforma', false);
    fixture.componentRef.setInput('evento', {
      id: 'e1',
      nombre: 'IA Week',
      cargando: false,
      aceptaPagos: false,
    });
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('#admin-nav-evento-titulo')?.textContent?.trim()).toBe('IA Week');
    const enlaces = enlacesDe(raiz);
    expect(enlaces).toContain('/dashboard/events');
    expect(enlaces).toContain('/dashboard/events/e1');
  });
});

describe('AdminNav — panel de plataforma', () => {
  it('pinta las secciones de la instalación bajo /admin', async () => {
    const raiz = await montar(true);
    const enlaces = enlacesDe(raiz);

    expect(enlaces).toContain('/admin');
    expect(enlaces).toContain('/admin/plantillas');
    expect(enlaces).toContain('/admin/identidad');
    expect(enlaces).toContain('/admin/legales');
    expect(enlaces).toContain('/admin/suplantar');
  });

  it('no ofrece ningún enlace del panel de organización', async () => {
    const raiz = await montar(true);
    const enlaces = enlacesDe(raiz);

    expect(enlaces).not.toContain('/dashboard');
    expect(enlaces).not.toContain('/dashboard/events');
  });

  it('no pinta el grupo de evento aunque haya uno activo', async () => {
    // En el panel de plataforma no se navega entre eventos de una organización.
    configurar();
    const fixture = TestBed.createComponent(AdminNav);
    fixture.componentRef.setInput('plataforma', true);
    fixture.componentRef.setInput('evento', {
      id: 'e1',
      nombre: 'IA Week',
      cargando: false,
      aceptaPagos: false,
    });
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('#admin-nav-evento-titulo')).toBeNull();
    expect(raiz.querySelector('#admin-nav-organizacion-titulo')).toBeNull();
  });

  it('el catálogo de componentes ya no cuelga de plataforma', async () => {
    // Es una herramienta de desarrollo, no administración de la instalación:
    // vive en el panel de organización y no debe exigir `is_superadmin`.
    const raiz = await montar(true);
    expect(enlacesDe(raiz)).not.toContain('/dashboard/estilo');
  });
});
