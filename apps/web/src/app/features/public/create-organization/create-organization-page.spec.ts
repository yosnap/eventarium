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

  it('no pide ningún identificador: el formulario solo lleva nombre, persona y Turnstile', async () => {
    configurar({ checkSlug: vi.fn().mockResolvedValue(true) });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();

    const etiquetas = Array.from(
      fixture.nativeElement.querySelectorAll('label') as NodeListOf<HTMLElement>,
    ).map((etiqueta) => etiqueta.textContent);
    expect(etiquetas.join('\n')).not.toContain('Identificador');
    expect(etiquetas.join('\n')).not.toContain('subdominio');
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

  it('al crear con éxito, genera el slug desde el nombre y activa la sesión sin ningún host', async () => {
    const createOrganization = vi.fn().mockResolvedValue({
      id: 'org-nueva',
      slug: 'ia-week-valencia',
      access_token: 'token-org-nueva',
      expires_in: 900,
    });
    configurar({ checkSlug: vi.fn().mockResolvedValue(true), createOrganization });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();

    const campos = fixture.nativeElement.querySelectorAll('input');
    const [campoNombre, campoNombrePersona, campoApellidos] = Array.from(
      campos,
    ) as HTMLInputElement[];
    for (const [campo, valor] of [
      [campoNombre, 'IA Week Valéncia'],
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

  it('si el slug generado colisiona, reintena en silencio con un sufijo', async () => {
    const createOrganization = vi.fn().mockResolvedValue({
      id: 'org-nueva',
      slug: 'ia-week-valencia-2',
      access_token: 'token-org-nueva',
      expires_in: 900,
    });
    // Solo el segundo candidato («…-2») está libre.
    const checkSlug = vi.fn().mockImplementation(async (slug: string) => slug.endsWith('-2'));
    configurar({ checkSlug, createOrganization });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();

    const campos = fixture.nativeElement.querySelectorAll('input');
    const [campoNombre, campoNombrePersona, campoApellidos] = Array.from(
      campos,
    ) as HTMLInputElement[];
    for (const [campo, valor] of [
      [campoNombre, 'IA Week Valencia'],
      [campoNombrePersona, 'Ana'],
      [campoApellidos, 'Pérez'],
    ] as const) {
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    }
    await fixture.whenStable();

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(checkSlug).toHaveBeenNthCalledWith(1, 'ia-week-valencia');
    expect(createOrganization).toHaveBeenCalledWith(
      expect.objectContaining({ slug: 'ia-week-valencia-2' }),
    );
  });

  it('si ningún intento está libre, muestra el error sin crear nada', async () => {
    const createOrganization = vi.fn();
    configurar({ checkSlug: vi.fn().mockResolvedValue(false), createOrganization });
    const fixture = TestBed.createComponent(CreateOrganizationPage);
    await fixture.whenStable();

    const campos = fixture.nativeElement.querySelectorAll('input');
    const [campoNombre, campoNombrePersona, campoApellidos] = Array.from(
      campos,
    ) as HTMLInputElement[];
    for (const [campo, valor] of [
      [campoNombre, 'IA Week Valencia'],
      [campoNombrePersona, 'Ana'],
      [campoApellidos, 'Pérez'],
    ] as const) {
      campo.value = valor;
      campo.dispatchEvent(new Event('input'));
    }
    await fixture.whenStable();

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await fixture.whenStable();

    expect(createOrganization).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('no está disponible');
  });
});
