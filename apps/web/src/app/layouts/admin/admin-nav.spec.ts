import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { AuthService } from '../../core/auth/auth.service';
import { AdminNav, enlacesDeEvento } from './admin-nav';

/** Solo lo que `AdminNav` lee de `AuthService`: quien monta el panel de
 * plataforma en un test es superadmin por defecto (mismo supuesto que ya
 * garantiza el guard real del panel, `personalPlataformaGuard`) — así los enlaces
 * `soloSuperadmin` siguen apareciendo salvo que un test concreto diga lo
 * contrario. */
function configurar(esSuperadmin = true) {
  TestBed.configureTestingModule({
    imports: [
      TranslocoTestingModule.forRoot({
        langs: { 'es-ES': es },
        translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
      }),
    ],
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      {
        provide: AuthService,
        useValue: { currentUser: signal({ is_superadmin: esSuperadmin }) },
      },
    ],
  });
}

async function montar(plataforma: boolean, esSuperadmin = true) {
  configurar(esSuperadmin);
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

  it('no ofrece el catálogo de componentes: es de plataforma, no de organización', async () => {
    const raiz = await montar(false);
    expect(enlacesDe(raiz)).not.toContain('/admin/estilo');
    expect(enlacesDe(raiz)).not.toContain('/dashboard/estilo');
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
    expect(enlaces).toContain('/admin/analitica-externa');
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

  it('el catálogo de componentes cuelga de plataforma', async () => {
    // Es la caja de piezas de quien administra la instalación (landing,
    // plantillas que luego usan las organizaciones), no una sección de una
    // organización concreta.
    const raiz = await montar(true);
    expect(enlacesDe(raiz)).toContain('/admin/estilo');
  });

  it('sin superadmin: oculta los enlaces soloSuperadmin pero no usuarios ni suplantar', async () => {
    // `soporte` (rol aditivo, plan 260916-0810-usuarios-y-permisos-
    // plataforma) no debe ver plantillas/identidad/legales/estilo —el
    // backend se los rechazaría con 403—, pero sí el directorio de usuarios
    // y la suplantación, que sí aceptan su rol.
    const raiz = await montar(true, false);
    const enlaces = enlacesDe(raiz);
    expect(enlaces).not.toContain('/admin');
    expect(enlaces).not.toContain('/admin/plantillas');
    expect(enlaces).not.toContain('/admin/identidad');
    expect(enlaces).not.toContain('/admin/legales');
    expect(enlaces).not.toContain('/admin/estilo');
    expect(enlaces).toContain('/admin/usuarios');
    expect(enlaces).toContain('/admin/suplantar');
  });

  it('la analítica externa es visible también para soporte', async () => {
    // Fase 3 del plan de cookies: la pantalla es de lectura para todo el
    // personal de plataforma — sin `soloSuperadmin` en su entrada de nav.
    const raiz = await montar(true, false);
    expect(enlacesDe(raiz)).toContain('/admin/analitica-externa');
  });
});
