import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { themingDePrueba } from '../../../../testing/theming.fixture';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { WorkspaceSelectorPage } from './workspace-selector-page';

describe('WorkspaceSelectorPage', () => {
  function configurar(auth: Partial<AuthService>) {
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
        { provide: AuthService, useValue: auth },
        { provide: ThemingService, useValue: themingDePrueba() },
      ],
    }).compileComponents();
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  function authDePrueba(sobrescribir: Partial<AuthService> = {}): Partial<AuthService> {
    return {
      loadCurrentUser: vi.fn().mockResolvedValue({ is_superadmin: false }),
      listMyOrganizations: vi.fn().mockResolvedValue([
        { organization_id: 'o1', slug: 'acme', name: 'Acme', role_name: 'Propietario' },
        { organization_id: 'o2', slug: 'otra', name: 'Otra organización', role_name: 'Editor' },
      ]),
      switchOrganization: vi.fn().mockResolvedValue(undefined),
      logout: vi.fn().mockResolvedValue(undefined),
      ...sobrescribir,
    };
  }

  it('muestra una tarjeta por organización, con su rol', async () => {
    configurar(authDePrueba() as Partial<AuthService>);
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const texto = raiz.textContent ?? '';
    expect(texto).toContain('Acme');
    expect(texto).toContain('Propietario');
    expect(texto).toContain('Otra organización');
    expect(texto).toContain('Editor');
  });

  it('sin rol de plataforma, no muestra la tarjeta "Admin Eventarium"', async () => {
    configurar(authDePrueba() as Partial<AuthService>);
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).not.toContain('Admin Eventarium');
  });

  it('con rol de plataforma, muestra la tarjeta "Admin Eventarium" incluso tras recargar (loadCurrentUser resuelto)', async () => {
    configurar(
      authDePrueba({
        loadCurrentUser: vi.fn().mockResolvedValue({ is_superadmin: true }),
      }) as Partial<AuthService>,
    );
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('Admin Eventarium');
  });

  it('elegir una organización cambia de organización activa y recarga a /dashboard', async () => {
    const switchOrganization = vi.fn().mockResolvedValue(undefined);
    configurar(authDePrueba({ switchOrganization }) as Partial<AuthService>);
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const ubicacionOriginal = Object.getOwnPropertyDescriptor(window, 'location')!;
    const asignacionDeUrl = vi.fn();
    Object.defineProperty(window, 'location', {
      value: {
        ...window.location,
        set href(url: string) {
          asignacionDeUrl(url);
        },
      },
      writable: true,
      configurable: true,
    });

    try {
      const boton = Array.from(raiz.querySelectorAll('button')).find((b) =>
        b.textContent?.includes('Acme'),
      );
      boton?.click();
      await fixture.whenStable();

      expect(switchOrganization).toHaveBeenCalledWith('o1');
      expect(asignacionDeUrl).toHaveBeenCalledWith('/dashboard');
    } finally {
      Object.defineProperty(window, 'location', ubicacionOriginal);
    }
  });

  it('elegir "Admin Eventarium" navega directo a /admin sin llamar a switchOrganization', async () => {
    const switchOrganization = vi.fn().mockResolvedValue(undefined);
    configurar(
      authDePrueba({
        loadCurrentUser: vi.fn().mockResolvedValue({ is_superadmin: true }),
        switchOrganization,
      }) as Partial<AuthService>,
    );
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const ubicacionOriginal = Object.getOwnPropertyDescriptor(window, 'location')!;
    const asignacionDeUrl = vi.fn();
    Object.defineProperty(window, 'location', {
      value: {
        ...window.location,
        set href(url: string) {
          asignacionDeUrl(url);
        },
      },
      writable: true,
      configurable: true,
    });

    try {
      const boton = Array.from(raiz.querySelectorAll('button')).find((b) =>
        b.textContent?.includes('Admin Eventarium'),
      );
      boton?.click();
      await fixture.whenStable();

      expect(switchOrganization).not.toHaveBeenCalled();
      expect(asignacionDeUrl).toHaveBeenCalledWith('/admin');
    } finally {
      Object.defineProperty(window, 'location', ubicacionOriginal);
    }
  });

  it('un organization_id ajeno rechazado por el backend se muestra como error sin navegar', async () => {
    const switchOrganization = vi
      .fn()
      .mockRejectedValue(new ApiError(403, 'No perteneces a esta organización.', null));
    configurar(authDePrueba({ switchOrganization }) as Partial<AuthService>);
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const ubicacionOriginal = Object.getOwnPropertyDescriptor(window, 'location')!;
    const asignacionDeUrl = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { ...window.location, set href(url: string) { asignacionDeUrl(url); } },
      writable: true,
      configurable: true,
    });

    try {
      const boton = Array.from(raiz.querySelectorAll('button')).find((b) =>
        b.textContent?.includes('Acme'),
      );
      boton?.click();
      await fixture.whenStable();

      expect(asignacionDeUrl).not.toHaveBeenCalled();
      expect(raiz.textContent).toContain('No perteneces a esta organización.');
    } finally {
      Object.defineProperty(window, 'location', ubicacionOriginal);
    }
  });

  it('doble click en dos tarjetas distintas no dispara dos acciones concurrentes', async () => {
    const switchOrganization = vi.fn().mockImplementation(() => new Promise<void>(() => undefined));
    configurar(
      authDePrueba({
        loadCurrentUser: vi.fn().mockResolvedValue({ is_superadmin: true }),
        switchOrganization,
      }) as Partial<AuthService>,
    );
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const botonOrganizacion = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Acme'),
    );
    const botonPlataforma = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Admin Eventarium'),
    );
    botonOrganizacion?.click();
    await fixture.whenStable();
    botonPlataforma?.click();
    await fixture.whenStable();

    expect(switchOrganization).toHaveBeenCalledTimes(1);
    expect(botonPlataforma?.disabled).toBe(true);
  });

  it('logout navega a /acceder', async () => {
    const logout = vi.fn().mockResolvedValue(undefined);
    configurar(authDePrueba({ logout }) as Partial<AuthService>);
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;
    const router = TestBed.inject(Router);
    const navegar = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const botonCerrarSesion = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Cerrar sesión'),
    );
    botonCerrarSesion?.click();
    await fixture.whenStable();

    expect(logout).toHaveBeenCalled();
    expect(navegar).toHaveBeenCalledWith(['/acceder']);
  });

  it('no tiene violaciones de accesibilidad', async () => {
    configurar(authDePrueba() as Partial<AuthService>);
    const fixture = TestBed.createComponent(WorkspaceSelectorPage);
    await fixture.whenStable();

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
