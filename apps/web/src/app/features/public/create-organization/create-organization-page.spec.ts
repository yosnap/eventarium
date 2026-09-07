import { Component, provideZonelessChangeDetection, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it, vi } from 'vitest';

import { CreateOrganizationPage } from './create-organization-page';
import { AuthService } from '../../../core/auth/auth.service';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

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
      providers: [provideZonelessChangeDetection(), { provide: AuthService, useValue: auth }],
    })
      .overrideComponent(CreateOrganizationPage, {
        remove: { imports: [TurnstileWidget] },
        add: { imports: [TurnstileWidgetFalso] },
      })
      .compileComponents();
  }

  it('no tiene violaciones de accesibilidad', async () => {
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
});
