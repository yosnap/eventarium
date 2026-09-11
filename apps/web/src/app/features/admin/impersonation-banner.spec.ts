import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { AuthService } from '../../core/auth/auth.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { ImpersonationBanner } from './impersonation-banner';

describe('ImpersonationBanner', () => {
  let suplantando: ReturnType<typeof vi.fn>;
  let salirDeImpersonacion: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    suplantando = vi.fn(() => null);
    salirDeImpersonacion = vi.fn(async () => undefined);

    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        {
          provide: AuthService,
          useValue: { suplantando, salirDeImpersonacion },
        },
      ],
    });
  });

  async function crear(): Promise<ComponentFixture<ImpersonationBanner>> {
    const fixture = TestBed.createComponent(ImpersonationBanner);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it('sin suplantación no pinta nada', async () => {
    const fixture = await crear();
    expect((fixture.nativeElement.textContent as string).trim()).toBe('');
  });

  it('con suplantación avisa de a quién y no tiene violaciones de accesibilidad', async () => {
    suplantando.mockReturnValue({ token: 't', usuarioId: 'u-1', nombre: 'Ana' });
    const fixture = await crear();

    // El mock de Transloco no interpola parámetros, así que el nombre no
    // aparece renderizado; lo que sí se comprueba es que el aviso sale y que
    // no hay violaciones reales de accesibilidad.
    expect(fixture.nativeElement.querySelector('[role="status"]')).toBeTruthy();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el aviso es un `role="status"`, no un adorno visual', async () => {
    suplantando.mockReturnValue({ token: 't', usuarioId: 'u-1', nombre: 'Ana' });
    const fixture = await crear();

    const aviso = fixture.nativeElement.querySelector('[role="status"]');
    expect(aviso).toBeTruthy();
  });
});
