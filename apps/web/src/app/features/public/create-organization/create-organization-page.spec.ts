import { Component, provideZonelessChangeDetection, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CreateOrganizationPage } from './create-organization-page';
import { AuthService } from '../../../core/auth/auth.service';
import { ThemingService } from '../../../core/theming/theming.service';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { themingDePrueba } from '../../../../testing/theming.fixture';

/** Mismo doble mínimo que `layouts/shells.spec.ts`: sin él, `AuthFrame`
 * inyectaría el `ThemingService` real, que necesita `HttpClient`. */

@Component({ selector: 'app-turnstile-widget', template: '' })
class TurnstileWidgetFalso {
  readonly resuelto = output<string>();
}

describe('CreateOrganizationPage', () => {
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
    })
      .overrideComponent(CreateOrganizationPage, {
        remove: { imports: [TurnstileWidget] },
        add: { imports: [TurnstileWidgetFalso] },
      })
      .compileComponents();
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    configurar({ checkSlug: vi.fn().mockResolvedValue(true) });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('no tiene violaciones de accesibilidad en tema claro', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    configurar({ checkSlug: vi.fn().mockResolvedValue(true) });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('sugiere el slug a partir del nombre hasta que se edita a mano', async () => {
    configurar({ checkSlug: vi.fn().mockResolvedValue(true) });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();

    const campos = fixture.nativeElement.querySelectorAll('input');
    const campoNombre = campos[0] as HTMLInputElement;
    const campoSlug = campos[1] as HTMLInputElement;

    campoNombre.value = 'IA Week Valéncia';
    campoNombre.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    expect(campoSlug.value).toBe('ia-week-valencia');

    campoSlug.value = 'mi-slug-manual';
    campoSlug.dispatchEvent(new Event('input'));
    campoNombre.value = 'Otro Nombre';
    campoNombre.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    // Tras editarlo a mano, ya no se sobrescribe al seguir cambiando el nombre.
    expect(campoSlug.value).toBe('mi-slug-manual');
  });

  it('exige todos los campos antes de enviar', async () => {
    const checkSlug = vi.fn().mockResolvedValue(true);
    const createOrganization = vi.fn();
    configurar({ checkSlug, createOrganization });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(createOrganization).not.toHaveBeenCalled();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('al crear con éxito, activa la sesión y recarga al panel sin ningún host', async () => {
    const createOrganization = vi.fn().mockResolvedValue({
      id: 'org-nueva',
      slug: 'ia-week-valencia',
      host: 'ia-week-valencia.example',
      access_token: 'token-org-nueva',
      expires_in: 900,
    });
    configurar({ checkSlug: vi.fn().mockResolvedValue(true), createOrganization });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();

    const campos = fixture.nativeElement.querySelectorAll('input');
    const [campoNombre, campoSlug, campoNombrePersona, campoApellidos] = Array.from(
      campos,
    ) as HTMLInputElement[];
    for (const [campo, valor] of [
      [campoNombre, 'IA Week Valéncia'],
      [campoSlug, 'ia-week-valencia'],
      [campoNombrePersona, 'Ana'],
      [campoApellidos, 'Pérez'],
    ] as const) {
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    }
    await fixture.whenStable();

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
      (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
        new Event('submit'),
      );
      await fixture.whenStable();

      expect(createOrganization).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'IA Week Valéncia', slug: 'ia-week-valencia' }),
      );
      expect(asignacionDeUrl).toHaveBeenCalledWith('/dashboard');
    } finally {
      Object.defineProperty(window, 'location', ubicacionOriginal);
    }
  });
});
