import { provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import { ShareLinks } from './share-links';

const URL_EVENTO = 'https://eventarium.org/eventos/ia-week-2026';
const TITULO = 'IA Week & amigos';

describe('ShareLinks', () => {
  let fixture: ComponentFixture<ShareLinks>;
  let raiz: HTMLElement;

  const hrefDe = (etiqueta: string): string | null =>
    raiz.querySelector(`[aria-label="${etiqueta}"]`)?.getAttribute('href') ?? null;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        ShareLinks,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    }).compileComponents();
    fixture = TestBed.createComponent(ShareLinks);
    fixture.componentRef.setInput('url', URL_EVENTO);
    fixture.componentRef.setInput('titulo', TITULO);
    fixture.detectChanges();
    await fixture.whenStable();
    raiz = fixture.nativeElement;
  });

  it('enlaza a cada red con la URL y el título codificados', () => {
    const url = encodeURIComponent(URL_EVENTO);
    expect(hrefDe('Compartir en X')).toBe(
      `https://x.com/intent/post?text=${encodeURIComponent(TITULO)}&url=${url}`,
    );
    expect(hrefDe('Compartir en LinkedIn')).toContain(`url=${url}`);
    expect(hrefDe('Compartir en Facebook')).toContain(`u=${url}`);
    expect(hrefDe('Compartir en WhatsApp')).toContain(encodeURIComponent(URL_EVENTO));
    expect(hrefDe('Compartir en Telegram')).toContain(`url=${url}`);
    expect(hrefDe('Compartir en Bluesky')).toContain(encodeURIComponent(URL_EVENTO));
  });

  it('abre las redes en otra pestaña sin pasarles la página de origen', () => {
    const externos = raiz.querySelectorAll('a[target="_blank"]');
    expect(externos.length).toBe(6);
    externos.forEach((a) => expect(a.getAttribute('rel')).toBe('noopener noreferrer'));
  });

  it('prepara el correo con el título de asunto y el enlace en el cuerpo', () => {
    expect(hrefDe('Enviar por correo')).toBe(
      `mailto:?subject=${encodeURIComponent(TITULO)}&body=${encodeURIComponent(URL_EVENTO)}`,
    );
  });

  it('copia el enlace y lo anuncia', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    raiz.querySelector<HTMLButtonElement>('[aria-label="Copiar enlace"]')!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(writeText).toHaveBeenCalledWith(URL_EVENTO);
    expect(raiz.querySelector('[aria-live="polite"]')?.textContent).toContain('Enlace copiado');
  });

  it('no tiene violaciones de accesibilidad', async () => {
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });
});
