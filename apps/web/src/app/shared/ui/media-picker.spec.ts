import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { MediaPicker } from './media-picker';

describe('MediaPicker', () => {
  let fixture: ComponentFixture<MediaPicker>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        MediaPicker,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(MediaPicker);
    fixture.componentRef.setInput('etiqueta', 'Logotipo');
    fixture.componentRef.setInput('aceptados', 'image/png');
    fixture.componentRef.setInput('url', 'https://ejemplo.test/logo.png');
  });

  it('con imagen ya elegida, muestra "Cambiar" y "Quitar" por defecto', async () => {
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('Cambiar');
    expect(raiz.textContent).toContain('Quitar');
  });

  it('con permitirQuitar=false, oculta "Quitar" (sin borrado real en el servidor detrás)', async () => {
    fixture.componentRef.setInput('permitirQuitar', false);
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    // Sin endpoint de borrado, "Quitar" solo limpiaba la previsualización
    // local y la imagen reaparecía al recargar (hallazgo de red-team).
    expect(raiz.textContent).toContain('Cambiar');
    expect(raiz.textContent).not.toContain('Quitar');
  });
});
