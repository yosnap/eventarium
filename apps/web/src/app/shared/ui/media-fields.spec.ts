import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { MediaFields } from './media-fields';

describe('MediaFields', () => {
  let fixture: ComponentFixture<MediaFields>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        MediaFields,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(MediaFields);
    fixture.componentRef.setInput('aceptados', 'image/png');
  });

  it('sin biblioteca (caso por defecto de los dos consumidores actuales), solo muestra Subir y URL', async () => {
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelectorAll('[role="tab"]').length).toBe(2);
    expect(raiz.textContent).not.toContain('Biblioteca');
  });

  it('con biblioteca no vacía, muestra las tres pestañas', async () => {
    fixture.componentRef.setInput('biblioteca', [
      { url: 'https://ejemplo.test/a.png', etiqueta: 'A' },
    ]);
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.querySelectorAll('[role="tab"]').length).toBe(3);
  });

  it('con permitirUrl=false, oculta la pestaña "Desde URL"', async () => {
    fixture.componentRef.setInput('permitirUrl', false);
    fixture.componentRef.setInput('biblioteca', [
      { url: 'https://ejemplo.test/a.png', etiqueta: 'A' },
    ]);
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    // Sin backend que persista una URL elegida, ofrecer la pestaña perdía el
    // cambio en silencio al guardar (hallazgo de red-team).
    expect(raiz.textContent).not.toContain('Desde URL');
    expect(raiz.querySelectorAll('[role="tab"]').length).toBe(2);
  });

  it('con permitirUrl=false y sin biblioteca, oculta el tablist entero (solo queda Subir)', async () => {
    fixture.componentRef.setInput('permitirUrl', false);
    await fixture.whenStable();
    fixture.detectChanges();
    const raiz = fixture.nativeElement as HTMLElement;
    // Con una sola pestaña siempre activa, el tablist no aporta nada — es
    // justo el caso de los dos consumidores actuales (branding, identidad de
    // plataforma), que solo suben fichero.
    expect(raiz.querySelector('[role="tablist"]')).toBeNull();
    expect(raiz.querySelector('.dropzone')).not.toBeNull();
  });
});
