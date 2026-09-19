import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { computed, provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminShell } from './admin/admin-shell';
import { PanelScope } from './admin/panel-scope';
import { PublicShell } from './public/public-shell';
import { AuthService } from '../core/auth/auth.service';
import { ThemingService } from '../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../testing/axe';
import { brandingDePrueba } from '../../testing/branding.fixture';
import es from '../../../public/assets/i18n/es-ES.json';
import { themingDePrueba } from '../../testing/theming.fixture';

/**
 * Los shells contienen los landmarks, el enlace de salto y la navegación: son la parte
 * de la aplicación donde más fácil se cuela un fallo de accesibilidad estructural.
 */
describe('shells', () => {
  const theming = themingDePrueba();
  const branding = theming.estado;
  /** URL que ve el shell: decide por ella en qué panel está (`/admin` o `/dashboard`). */
  const url = signal('/dashboard');

  function configurarAuth(esSuperadmin: boolean) {
    return {
      currentUser: signal({
        id: '1',
        email: 'persona@example.com',
        first_name: 'Persona',
        last_name: 'De prueba',
        is_superadmin: esSuperadmin,
      }),
      isAuthenticated: signal(true),
      logout: vi.fn(),
      listMyOrganizations: vi.fn().mockResolvedValue([]),
      loadCurrentUser: vi.fn().mockResolvedValue(undefined),
      switchOrganization: vi.fn().mockResolvedValue(undefined),
    };
  }

  beforeEach(() => {
    localStorage.clear();
    url.set('/dashboard');

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
        // `PanelScope` decide, leyendo la URL, qué navegación pinta el shell. Se
        // sustituye aquí porque montar el árbol de rutas real arrastraría guards
        // y peticiones ajenas a estas pruebas; el doble expone lo mismo que el
        // servicio: una señal.
        {
          provide: PanelScope,
          useValue: { esPlataforma: computed(() => url().startsWith('/admin')) },
        },
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ThemingService,
          useValue: {
            branding: theming.estado.asReadonly(),
            error: signal(null),
            plataforma: computed(() => theming.estado().platform),
            nombreDeMarca: computed(() => theming.estado().platform.name),
          },
        },
        {
          provide: AuthService,
          useValue: configurarAuth(false),
        },
      ],
    });
  });

  it('el shell público no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('.skip-link')).not.toBeNull();
    expect(raiz.querySelector('main#contenido')).not.toBeNull();
    expect(raiz.querySelector('header')).not.toBeNull();
    expect(raiz.querySelector('footer')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('el shell público no tiene violaciones de accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    try {
      const fixture = TestBed.createComponent(PublicShell);
      await fixture.whenStable();
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });

  it('el shell de administración no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(AdminShell);
    await fixture.whenStable();

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelector('.skip-link')).not.toBeNull();
    expect(raiz.querySelector('main#contenido-admin')).not.toBeNull();
    // El panel de navegación colapsable es un `<nav>` real: un `aria-label` sobre un
    // `<div>` sin rol ARIA no lo anuncia como región de navegación.
    expect(raiz.querySelector('nav[aria-label]')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('"Preferencias de cookies" del pie reabre la ventana de personalización de cookies', async () => {
    localStorage.setItem(
      'cookie-consent',
      JSON.stringify({ categories: ['necessary'], version: 1, created_at: 'x' }),
    );
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;

    expect((raiz.querySelector('dialog') as HTMLDialogElement).hasAttribute('open')).toBe(false);
    const gestionar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Preferencias de cookies'),
    );
    expect(gestionar).toBeTruthy();
    gestionar?.dispatchEvent(new Event('click'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect((raiz.querySelector('dialog') as HTMLDialogElement).hasAttribute('open')).toBe(true);
  });

  it('el shell público muestra el logotipo de la plataforma con texto alternativo', async () => {
    branding.set(brandingDePrueba({ platform: { logo_url: 'https://ejemplo.com/logo.png' } }));
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();

    const logo = fixture.nativeElement.querySelector('img') as HTMLImageElement;
    expect(logo.alt).toBe('Eventarium');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  describe('navegación del panel de administración', () => {
    it('el panel de organización agrupa sus enlaces en la región de organización', async () => {
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      // Solo Organización: las secciones de un evento viven en sus propias
      // pestañas (`EventShell`), no aquí. Nunca Plataforma: ese panel es otro
      // árbol de ruta.
      const navs = Array.from(raiz.querySelectorAll('nav[aria-labelledby]'));
      expect(navs.length).toBe(1);
      for (const nav of navs) {
        const idEncabezado = nav.getAttribute('aria-labelledby');
        expect(idEncabezado).toBeTruthy();
        const encabezado = raiz.querySelector(`#${idEncabezado}`);
        expect(encabezado?.tagName).toBe('H2');
        expect(encabezado?.textContent?.trim().length).toBeGreaterThan(0);
      }
    });

    it('el panel de plataforma solo agrupa las secciones de la instalación', async () => {
      url.set('/admin');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const navs = Array.from(raiz.querySelectorAll('nav[aria-labelledby]'));
      expect(navs.length).toBe(1);
      expect(raiz.querySelector('#admin-nav-plataforma-titulo')).not.toBeNull();
      expect(raiz.querySelector('#admin-nav-organizacion-titulo')).toBeNull();
    });

    it('el panel de organización siempre ofrece dar de alta otra organización, aunque solo tenga una', async () => {
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      // El alta vive dentro del menú del selector (oculto hasta abrirlo,
      // pero presente en el DOM).
      const enlace = Array.from(raiz.querySelectorAll('a')).find(
        (a) => a.getAttribute('href') === '/crear-organizacion',
      );
      expect(enlace).toBeTruthy();
    });

    it('el panel de plataforma no ofrece el selector de organización', async () => {
      url.set('/admin');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const enlace = Array.from(raiz.querySelectorAll('a')).find(
        (a) => a.getAttribute('href') === '/crear-organizacion',
      );
      expect(enlace).toBeFalsy();
    });

    it('el menú de cuenta muestra el email y ofrece "Cambiar de espacio de trabajo"', async () => {
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const disparador = Array.from(raiz.querySelectorAll('button')).find((b) =>
        b.classList.contains('disparador'),
      );
      expect(disparador).toBeTruthy();
      expect(disparador?.textContent).toContain('persona@example.com');
      disparador?.click();
      await fixture.whenStable();

      const enlaceCambiar = Array.from(raiz.querySelectorAll('a')).find(
        (a) => a.getAttribute('href') === '/espacio-de-trabajo',
      );
      expect(enlaceCambiar).toBeTruthy();
      expect(enlaceCambiar?.textContent).toContain('Cambiar de espacio de trabajo');
    });

    it('el menú de cuenta ofrece "Mi cuenta" y "Cerrar sesión"', async () => {
      const logout = vi.fn().mockResolvedValue(undefined);
      TestBed.overrideProvider(AuthService, {
        useValue: { ...configurarAuth(false), logout },
      });
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;
      const router = TestBed.inject(Router);
      const navegar = vi.spyOn(router, 'navigate').mockResolvedValue(true);

      const disparador = Array.from(raiz.querySelectorAll('button')).find((b) =>
        b.classList.contains('disparador'),
      );
      disparador?.click();
      await fixture.whenStable();

      const enlaceCuenta = Array.from(raiz.querySelectorAll('a')).find(
        (a) => a.getAttribute('href') === '/dashboard/account',
      );
      expect(enlaceCuenta).toBeTruthy();

      const botonCerrarSesion = Array.from(
        raiz.querySelectorAll('button[role="option"]') as NodeListOf<HTMLButtonElement>,
      ).find((b) => b.textContent?.includes('Cerrar sesión'));
      expect(botonCerrarSesion).toBeTruthy();
      botonCerrarSesion?.click();
      await fixture.whenStable();

      expect(logout).toHaveBeenCalled();
      expect(navegar).toHaveBeenCalledWith(['/acceder']);
    });

    it('la cabecera del panel de organización muestra su nombre, no el de la instalación', async () => {
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      expect(raiz.querySelector('.marca')?.textContent).toContain('Panel de la organización');
    });

    it('la cabecera del panel de plataforma se identifica como la instalación', async () => {
      url.set('/admin');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      expect(raiz.querySelector('.marca')?.textContent).toContain('Administración de Eventarium');
    });

    it('"/dashboard/account" no está en la barra lateral y sigue accesible desde la cabecera', async () => {
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const cabecera = raiz.querySelector('header');
      const panel = raiz.querySelector('.panel-navegacion');
      expect(
        Array.from(cabecera?.querySelectorAll('a') ?? []).some(
          (a) => a.getAttribute('href') === '/dashboard/account',
        ),
      ).toBe(true);
      expect(
        Array.from(panel?.querySelectorAll('a') ?? []).some(
          (a) => a.getAttribute('href') === '/dashboard/account',
        ),
      ).toBe(false);
    });

    it('el catálogo de componentes no aparece en el panel de organización', async () => {
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const enlace = Array.from(raiz.querySelectorAll('a')).find(
        (a) =>
          a.getAttribute('href') === '/admin/estilo' ||
          a.getAttribute('href') === '/dashboard/estilo',
      );
      expect(enlace).toBeFalsy();
    });

    it('el catálogo de componentes aparece en el panel de plataforma', async () => {
      // soloSuperadmin: el beforeEach de este describe monta con esSuperadmin
      // false por defecto; este enlace concreto necesita superadmin de verdad.
      TestBed.overrideProvider(AuthService, { useValue: configurarAuth(true) });
      url.set('/admin');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const enlace = Array.from(raiz.querySelectorAll('a')).find(
        (a) => a.getAttribute('href') === '/admin/estilo',
      );
      expect(enlace).toBeTruthy();
    });

    it('la navegación móvil abre, mueve el foco dentro, cierra con Esc y devuelve el foco', async () => {
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const boton = raiz.querySelector('.boton-navegacion') as HTMLButtonElement;
      expect(boton.getAttribute('aria-expanded')).toBe('false');

      boton.click();
      await fixture.whenStable();
      fixture.detectChanges();

      expect(boton.getAttribute('aria-expanded')).toBe('true');
      const panel = raiz.querySelector('.panel-navegacion') as HTMLElement;
      const primerEnlace = panel.querySelector('a') as HTMLElement;
      expect(document.activeElement).toBe(primerEnlace);

      panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await fixture.whenStable();
      fixture.detectChanges();

      expect(boton.getAttribute('aria-expanded')).toBe('false');
      expect(document.activeElement).toBe(boton);
    });
  });
});
