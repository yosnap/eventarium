import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminShell } from './admin/admin-shell';
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

  beforeEach(() => {
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
          useValue: {
            currentUser: signal({
              id: '1',
              email: 'persona@example.com',
              first_name: 'Persona',
              last_name: 'De prueba',
              is_superadmin: false,
            }),
            isAuthenticated: signal(true),
            logout: vi.fn(),
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
    expect(raiz.querySelector('nav[aria-label]')).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('el shell público muestra el logotipo con texto alternativo cuando existe', async () => {
    branding.set(brandingDePrueba({ logo_url: 'https://ejemplo.com/logo.png' }));
    const fixture = TestBed.createComponent(PublicShell);
    await fixture.whenStable();

    const logo = fixture.nativeElement.querySelector('img') as HTMLImageElement;
    expect(logo.alt).toBe('Organización de prueba');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
