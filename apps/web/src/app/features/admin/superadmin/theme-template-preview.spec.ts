import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import { ThemeTemplatePreview } from './theme-template-preview';
import es from '../../../../../public/assets/i18n/es-ES.json';

const TOKENS_DE_PRUEBA = {
  dark: { bg: '#080808', fg: '#f0f0f0', accent: '#00ff87' },
  light: { bg: '#ffffff', fg: '#111111', accent: '#006644' },
};

describe('ThemeTemplatePreview', () => {
  async function montar(): Promise<ComponentFixture<ThemeTemplatePreview>> {
    TestBed.configureTestingModule({
      imports: [
        ThemeTemplatePreview,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
    const fixture = TestBed.createComponent(ThemeTemplatePreview);
    fixture.componentRef.setInput('tokens', TOKENS_DE_PRUEBA);
    fixture.componentRef.setInput('modo', 'dark');
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  // Regresión: al componente le faltaba `imports: [TranslocoDirective]` en el
  // decorador -el símbolo se importaba en TypeScript pero nunca se declaraba
  // como directiva standalone-, así que `*transloco` no creaba su vista y la
  // miniatura quedaba vacía (`<!--container-->`) sin ningún error en consola
  // ni fallo en el resto de specs, que no comprueban su contenido.
  it('pinta la ficha con los tokens y las variables del modo elegido', async () => {
    const fixture = await montar();
    const anfitrion: HTMLElement = fixture.nativeElement.querySelector('.escena');
    expect(anfitrion).not.toBeNull();
    expect(anfitrion.style.getPropertyValue('--t-bg')).toBe(TOKENS_DE_PRUEBA.dark.bg);
    expect(anfitrion.style.getPropertyValue('--t-accent')).toBe(TOKENS_DE_PRUEBA.dark.accent);
    expect(
      fixture.nativeElement.querySelector('.ficha-titulo').textContent.trim().length,
    ).toBeGreaterThan(0);
  });
});
