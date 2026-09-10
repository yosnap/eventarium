import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import { AuthFrame } from './auth-frame';
import { ThemingService } from '../../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';

/** Anfitrión con contenido proyectado real, como usan las 10 pantallas sueltas. */
@Component({
  selector: 'app-anfitrion-marco',
  imports: [AuthFrame],
  template: `<app-auth-frame><h1>Contenido de la pantalla</h1></app-auth-frame>`,
})
class AnfitrionMarco {}

describe('AuthFrame', () => {
  function configurar(organizationName = 'Organización de prueba') {
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
        {
          provide: ThemingService,
          useValue: {
            branding: signal(null),
            error: signal(null),
            templateKey: signal('classic'),
            organizationName: signal(organizationName),
          },
        },
      ],
    });
  }

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('pinta exactamente un `main` con enlace de salto y conmutador de tema, sin violaciones', async () => {
    configurar();
    const fixture = TestBed.createComponent(AnfitrionMarco);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelectorAll('main').length).toBe(1);
    expect(raiz.querySelector('main#contenido')).not.toBeNull();
    expect(raiz.querySelector('.skip-link')).not.toBeNull();
    expect(raiz.querySelector('app-theme-toggle button')).not.toBeNull();
    expect(raiz.querySelector('h1')?.textContent).toBe('Contenido de la pantalla');
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('en tema claro conserva el mismo único `main` y sigue sin violaciones', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    configurar();
    const fixture = TestBed.createComponent(AnfitrionMarco);
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelectorAll('main').length).toBe(1);
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });

  it('con `titulo`, pinta un único `<h1>` oculto visualmente, con el texto pasado', async () => {
    configurar();
    const fixture = TestBed.createComponent(AuthFrame);
    fixture.componentRef.setInput('titulo', 'Inscripción al evento');
    await fixture.whenStable();
    const raiz = fixture.nativeElement as HTMLElement;

    const h1s = raiz.querySelectorAll('h1');
    expect(h1s.length).toBe(1);
    expect(h1s[0].textContent).toBe('Inscripción al evento');
    expect(h1s[0].classList).toContain('oculto-visual');
  });

  it('sin `titulo`, no pinta ningún `<h1>` propio', async () => {
    configurar();
    const fixture = TestBed.createComponent(AuthFrame);
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelector('h1')).toBeNull();
  });

  it('sin logotipo muestra el nombre de la organización como marca textual', async () => {
    configurar('Eventarium');
    const fixture = TestBed.createComponent(AnfitrionMarco);
    await fixture.whenStable();

    expect(fixture.nativeElement.textContent).toContain('Eventarium');
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
  });
});
