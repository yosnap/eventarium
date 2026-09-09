import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminShell } from './admin/admin-shell';
import { EventScope } from './admin/event-scope';
import { PublicShell } from './public/public-shell';
import { AuthService } from '../core/auth/auth.service';
import { ThemingService } from '../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../testing/axe';
import { brandingDePrueba } from '../../testing/branding.fixture';
import es from '../../../public/assets/i18n/es-ES.json';

/**
 * Los shells contienen los landmarks, el enlace de salto y la navegación: son la parte
 * de la aplicación donde más fácil se cuela un fallo de accesibilidad estructural.
 */
describe('shells', () => {
  const branding = signal(brandingDePrueba());
  const eventId = signal<string | null>(null);
  const falloCarga = signal(false);
  const nombreEvento = signal<string | null>(null);
  const cargandoEvento = signal(false);
  const registrationMode = signal<'free' | 'approval' | 'paid' | null>(null);

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
    };
  }

  beforeEach(() => {
    localStorage.clear();
    eventId.set(null);
    falloCarga.set(false);
    nombreEvento.set(null);
    cargandoEvento.set(false);
    registrationMode.set(null);

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
          provide: ThemingService,
          useValue: {
            branding,
            error: signal(null),
            templateKey: signal('classic'),
            organizationName: signal('Organización de prueba'),
          },
        },
        {
          provide: AuthService,
          useValue: configurarAuth(false),
        },
        {
          provide: EventScope,
          useValue: {
            eventId,
            falloCarga,
            nombreEvento,
            cargando: cargandoEvento,
            registrationMode,
          },
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

  it('"Gestionar cookies" del pie reabre el banner de cookies', async () => {
    localStorage.setItem(
      'cookie-consent',
      JSON.stringify({ categories: ['necessary'], version: 1, created_at: 'x' }),
    );
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('[role="region"]')).toBeNull();
    const gestionar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Gestionar cookies'),
    );
    expect(gestionar).toBeTruthy();
    gestionar?.dispatchEvent(new Event('click'));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(raiz.querySelector('[role="region"]')).not.toBeNull();
  });

  it('el shell público muestra el logotipo con texto alternativo cuando existe', async () => {
    branding.set(brandingDePrueba({ logo_url: 'https://ejemplo.com/logo.png' }));
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();

    const logo = fixture.nativeElement.querySelector('img') as HTMLImageElement;
    expect(logo.alt).toBe('Organización de prueba');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  describe('navegación del panel de administración', () => {
    it('agrupa los enlaces en tres regiones con nombre accesible propio', async () => {
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const navs = Array.from(raiz.querySelectorAll('nav[aria-labelledby]'));
      expect(navs.length).toBe(2); // Organización y Plataforma; el de evento no está activo
      for (const nav of navs) {
        const idEncabezado = nav.getAttribute('aria-labelledby');
        expect(idEncabezado).toBeTruthy();
        const encabezado = raiz.querySelector(`#${idEncabezado}`);
        expect(encabezado?.tagName).toBe('H2');
        expect(encabezado?.textContent?.trim().length).toBeGreaterThan(0);
      }
    });

    it('el grupo de evento no existe fuera del ámbito de un evento', async () => {
      eventId.set(null);
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      expect(raiz.querySelector('#admin-nav-evento-titulo')).toBeNull();
    });

    it('el grupo de evento aparece con el nombre del evento activo', async () => {
      eventId.set('e1');
      nombreEvento.set('IA Week in Cascais 2026');
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const encabezado = raiz.querySelector('#admin-nav-evento-titulo');
      expect(encabezado?.textContent?.trim()).toBe('IA Week in Cascais 2026');
      const volver = Array.from(raiz.querySelectorAll('a')).find((a) =>
        a.textContent?.includes('Volver a eventos'),
      );
      expect(volver).toBeTruthy();
    });

    it('mientras el nombre del evento carga, el encabezado muestra un texto de carga', async () => {
      eventId.set('e1');
      cargandoEvento.set(true);
      nombreEvento.set(null);
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const encabezado = raiz.querySelector('#admin-nav-evento-titulo');
      expect(encabezado?.textContent?.trim()).toBe('Cargando evento…');
    });

    it('si la carga del evento falla, la navegación conserva los dos grupos estables', async () => {
      eventId.set('e1');
      falloCarga.set(true);
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      expect(raiz.querySelector('#admin-nav-evento-titulo')).toBeNull();
      expect(raiz.querySelectorAll('nav[aria-labelledby]').length).toBe(2);
    });

    it('el enlace de superadministración solo aparece para is_superadmin', async () => {
      TestBed.overrideProvider(AuthService, { useValue: configurarAuth(true) });
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const enlace = Array.from(raiz.querySelectorAll('a')).find(
        (a) => a.getAttribute('href') === '/admin/superadmin',
      );
      expect(enlace).toBeTruthy();
    });

    it('"/admin/account" no está en la barra lateral y sigue accesible desde la cabecera', async () => {
      const fixture = TestBed.createComponent(AdminShell);
      await fixture.whenStable();
      const raiz = fixture.nativeElement as HTMLElement;

      const cabecera = raiz.querySelector('header');
      const panel = raiz.querySelector('.panel-navegacion');
      expect(
        Array.from(cabecera?.querySelectorAll('a') ?? []).some(
          (a) => a.getAttribute('href') === '/admin/account',
        ),
      ).toBe(true);
      expect(
        Array.from(panel?.querySelectorAll('a') ?? []).some(
          (a) => a.getAttribute('href') === '/admin/account',
        ),
      ).toBe(false);
    });

    it('el catálogo de componentes sigue accesible sin is_superadmin', async () => {
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
