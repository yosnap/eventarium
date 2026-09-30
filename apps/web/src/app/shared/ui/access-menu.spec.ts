import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';
import { AccessMenu } from './access-menu';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/** Vacía la cola de microtareas: el `loadCurrentUser()` del menú solo se
 *  encadena cuando el `refresh()` ya ha resuelto. */
function vaciarMicrotareas(): Promise<void> {
  return new Promise((resolver) => setTimeout(resolver));
}

describe('AccessMenu', () => {
  let http: HttpTestingController;

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
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  /** Crea el menú y deja resolver el refresh de carga (falla: sin cookie). */
  function crearInvitado() {
    const fixture = TestBed.createComponent(AccessMenu);
    fixture.detectChanges();
    http.expectOne('/api/v1/auth/refresh').flush(null, { status: 401, statusText: 'Unauthorized' });
    return fixture;
  }

  /** Crea el menú con una cookie viva: el refresh de carga renueva y el menú
   *  carga el usuario con `/users/me`, como tras una recarga de página. */
  async function crearConSesion() {
    const fixture = TestBed.createComponent(AccessMenu);
    fixture.detectChanges();
    http.expectOne('/api/v1/auth/refresh').flush({ access_token: 'token-1', expires_in: 900 });
    await vaciarMicrotareas();
    http
      .expectOne('/api/v1/users/me')
      .flush({ id: '1', email: 'ana@ejemplo.com', first_name: 'Ana', last_name: null, is_superadmin: false });
    await avanzar(fixture);
    return fixture;
  }

  it('sin sesión, ofrece "Iniciar sesión" y "Crear cuenta"', () => {
    const fixture = crearInvitado();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;

    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
    disparador.click();
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(false);

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).toContain('/acceder');
    expect(enlaces).toContain('/registro');
  });

  it('con sesión viva tras recargar, muestra la cuenta y no "Iniciar sesión"', async () => {
    const fixture = await crearConSesion();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;

    // El disparador muestra el nombre (el correo, solo si no lo hubiera).
    expect(disparador.textContent).toContain('Ana');
    disparador.click();
    fixture.detectChanges();

    const enlaces = Array.from(raiz.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(enlaces).toContain('/dashboard/account');
    expect(enlaces).not.toContain('/acceder');
    expect(raiz.textContent).toContain('Cerrar sesión');
  });

  it('"Cerrar sesión" revoca, vuelve a la UI de invitado y no navega', async () => {
    const fixture = await crearConSesion();
    const raiz = fixture.nativeElement as HTMLElement;
    (raiz.querySelector('.disparador') as HTMLButtonElement).click();
    fixture.detectChanges();

    const cerrar = Array.from(raiz.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Cerrar sesión'),
    ) as HTMLButtonElement;
    cerrar.click();
    http.expectOne('/api/v1/auth/logout').flush(null);
    await avanzar(fixture);

    // El menú reacciona a la sesión muerta y ofrece de nuevo iniciar sesión.
    expect(raiz.querySelector('.disparador')?.querySelector('svg')).not.toBeNull();
    expect(raiz.textContent).toContain('Iniciar sesión');
  });

  it('Escape cierra el menú', () => {
    const fixture = crearInvitado();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;
    disparador.click();
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(false);

    disparador.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
  });

  it('clic fuera cierra el menú', () => {
    const fixture = crearInvitado();
    const raiz = fixture.nativeElement as HTMLElement;
    (raiz.querySelector('.disparador') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(false);

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();
    expect(raiz.querySelector('ul')?.hasAttribute('hidden')).toBe(true);
  });

  it('ArrowDown mueve la opción activa y Enter la activa', () => {
    const fixture = crearInvitado();
    const raiz = fixture.nativeElement as HTMLElement;
    const disparador = raiz.querySelector('.disparador') as HTMLButtonElement;
    disparador.click();
    fixture.detectChanges();

    disparador.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    fixture.detectChanges();
    expect(disparador.getAttribute('aria-activedescendant')).toContain('opcion-1');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    const fixture = await crearConSesion();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
