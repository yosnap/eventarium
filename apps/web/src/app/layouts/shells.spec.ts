import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Component, computed, provideZonelessChangeDetection, signal } from '@angular/core';
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
/** Ruta comodín para que `Router.navigateByUrl()` actualice `router.url` de
 * verdad en los tests que lo necesitan (sin rutas registradas, una
 * navegación sin coincidencia no llega a cambiarlo). */
@Component({ selector: 'app-ruta-de-prueba', template: '' })
class RutaDePrueba {}

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
      cierreFueDeliberado: signal(false),
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
        provideRouter([{ path: '**', component: RutaDePrueba }]),
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

  it('el menú de acceso del shell público lleva tanto a acceder como a crear cuenta', async () => {
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();
    fixture.detectChanges();

    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('app-access-menu button') as HTMLButtonElement;
    expect(disparador).not.toBeNull();
    disparador.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(raiz.querySelector('a[href="/acceder"]')).not.toBeNull();
    const registro = raiz.querySelector('a[href="/registro"]') as HTMLAnchorElement;
    expect(registro).not.toBeNull();
    expect(registro.textContent?.trim()).toBe('Crear cuenta');
  });

  it('sin logotipo, la marca del shell público lee "Eventarium" sin duplicar la inicial', async () => {
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();

    const raiz = fixture.nativeElement as HTMLElement;
    // Solo la cabecera: el pie lleva siempre el logo de Humanitek.
    expect(raiz.querySelector('header img')).toBeNull();
    // app-brand-mark ya pinta la "E" dentro de su caja: el texto no la repite,
    // pero juntos (caja + texto) siguen leyendo "Eventarium".
    expect(raiz.querySelector('app-brand-mark')?.textContent?.trim()).toBe('E');
    expect(raiz.querySelector('app-brand-lockup .resto')?.textContent).toBe('ventarium');
    // Para un lector de pantalla, el lockup es una sola imagen con el nombre entero.
    expect(raiz.querySelector('app-brand-lockup [role="img"]')?.getAttribute('aria-label')).toBe(
      'Eventarium',
    );
  });

  it('"Crear evento" del shell público lleva a crear un evento en el panel', async () => {
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();

    const enlace = (fixture.nativeElement as HTMLElement).querySelector(
      'header a.crear-evento',
    ) as HTMLAnchorElement;
    expect(enlace.textContent?.trim()).toBe('Crear evento');
    // Sin sesión, el guard del panel lo redirige a /acceder conservando el destino.
    expect(enlace.getAttribute('href')).toBe('/dashboard/events/nuevo');
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
      // `logout` limpia `isAuthenticated` como hace el servicio real
      // (`AuthService.clear()` en su `finally`): el efecto de sesión
      // caducada del shell es quien navega, no `cerrarSesion()`
      // directamente, así que el doble tiene que reflejar ese efecto
      // secundario para que el efecto llegue a dispararse.
      const auth = configurarAuth(false);
      const logout = vi.fn().mockImplementation(async () => {
        auth.cierreFueDeliberado.set(true);
        auth.isAuthenticated.set(false);
      });
      TestBed.overrideProvider(AuthService, { useValue: { ...auth, logout } });
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
      // Sin `redirigir`: un cierre de sesión deliberado no debe devolver al
      // panel al loguearse de nuevo.
      expect(navegar).toHaveBeenCalledWith(['/acceder']);
    });

    it('la sesión que muere en caliente (sin cerrar sesión a propósito) devuelve a /acceder con redirigir', async () => {
      const auth = configurarAuth(false);
      TestBed.overrideProvider(AuthService, { useValue: auth });
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const router = TestBed.inject(Router);

      // Navegación real (ruta comodín `RutaDePrueba`) a una URL concreta y
      // conocida, ANTES de espiar `navigate`: así `router.url` no depende
      // de lo que capture el propio espía, y la aserción de más abajo
      // compara contra un valor fijo, no contra sí misma.
      await router.navigateByUrl('/dashboard/eventos/123');
      expect(router.url).toBe('/dashboard/eventos/123');
      const navegar = vi.spyOn(router, 'navigate').mockResolvedValue(true);

      // Simula lo que hace `authInterceptor` cuando su único reintento de
      // refresh agota (cookie de refresco caducada, sesión cerrada en otra
      // pestaña…): el token cae a `null` sin que nadie haya pasado por
      // `cerrarSesion()`.
      auth.isAuthenticated.set(false);
      await fixture.whenStable();

      expect(navegar).toHaveBeenCalledWith(['/acceder'], {
        queryParams: { redirigir: '/dashboard/eventos/123' },
      });
    });

    it('la cabecera del panel lleva el mismo logotipo de la plataforma que la web pública', async () => {
      branding.set(brandingDePrueba());
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();

      const enlace = (fixture.nativeElement as HTMLElement).querySelector(
        'header a[href="/"]',
      ) as HTMLAnchorElement;
      expect(
        enlace.querySelector('app-brand-lockup [role="img"]')?.getAttribute('aria-label'),
      ).toBe('Eventarium');
    });

    it('junto al logo, la cabecera del panel de organización indica en qué panel se está', async () => {
      url.set('/dashboard');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      expect(raiz.querySelector('.contexto')?.textContent).toContain('Panel de la organización');
    });

    it('la cabecera del panel de plataforma se identifica como la instalación', async () => {
      url.set('/admin');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      expect(raiz.querySelector('.contexto')?.textContent).toContain(
        'Administración de Eventarium',
      );
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
