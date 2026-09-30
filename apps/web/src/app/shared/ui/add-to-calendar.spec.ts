import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../testing/axe';
import es from '../../../../public/assets/i18n/es-ES.json';
import type { EventoParaCalendario } from '../calendar/calendar-links';
import { AddToCalendar } from './add-to-calendar';

const EVENTO: EventoParaCalendario = {
  organization: { slug: 'acme' },
  slug: 'congreso',
  title: 'Congreso de IA',
  starts_at: '2026-10-01T07:00:00Z',
  ends_at: '2026-10-01T16:30:00Z',
  timezone: 'Europe/Madrid',
  location: 'Palacio de Congresos',
};

describe('AddToCalendar', () => {
  let fixture: ComponentFixture<AddToCalendar>;

  async function montar(evento: EventoParaCalendario = EVENTO): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [
        AddToCalendar,
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(AddToCalendar);
    fixture.componentRef.setInput('evento', evento);
    await fixture.whenStable();
  }

  function enlaces(): HTMLAnchorElement[] {
    return Array.from(fixture.nativeElement.querySelectorAll('a.opcion'));
  }

  beforeEach(async () => {
    await montar();
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
    vi.restoreAllMocks();
  });

  it('ofrece Google Calendar, Outlook y Apple Calendar', () => {
    const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(texto).toContain('Añade el evento a tu calendario');
    expect(texto).toContain('Google Calendar');
    expect(texto).toContain('Outlook');
    expect(texto).toContain('Apple Calendar');
  });

  it('Google y Outlook son enlaces externos con el evento ya rellenado', () => {
    const [google, outlook] = enlaces();

    expect(google!.href).toContain('https://calendar.google.com/calendar/render');
    expect(google!.href).toContain('dates=20261001T070000Z/20261001T163000Z');
    expect(outlook!.href).toContain('https://outlook.live.com/calendar/0/deeplink/compose');
    expect(outlook!.href).toContain('startdt=2026-10-01T07%3A00%3A00Z');
    for (const enlace of [google!, outlook!]) {
      expect(enlace.target).toBe('_blank');
      expect(enlace.rel).toContain('noopener');
      // El enlace de la ficha pública va dentro, para volver al evento desde el calendario.
      expect(decodeURIComponent(enlace.href)).toContain('/acme/congreso');
    }
  });

  it('avisa a las tecnologías de apoyo de que se abre una pestaña nueva y de que se descarga un .ics', () => {
    const [google] = enlaces();
    expect(google!.getAttribute('aria-label')).toBe(
      'Google Calendar (se abre en una pestaña nueva)',
    );
    const apple = fixture.nativeElement.querySelector('button.opcion') as HTMLButtonElement;
    expect(apple.getAttribute('aria-label')).toBe('Apple Calendar (descarga un archivo .ics)');
  });

  it('Apple Calendar descarga un .ics con el evento', async () => {
    let contenidoSubido = '';
    const crear = vi.fn((blob: Blob) => {
      void blob.text().then((texto) => (contenidoSubido = texto));
      return 'blob:prueba';
    });
    Object.defineProperty(URL, 'createObjectURL', { value: crear, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true });
    const clic = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    (fixture.nativeElement.querySelector('button.opcion') as HTMLButtonElement).click();
    await fixture.whenStable();
    await Promise.resolve(); // deja resolver Blob.text()

    expect(crear).toHaveBeenCalledOnce();
    expect(crear.mock.calls[0]![0].type).toContain('text/calendar');
    expect(clic).toHaveBeenCalledOnce();
    expect(contenidoSubido).toContain('BEGIN:VCALENDAR');
    expect(contenidoSubido).toContain('UID:congreso@eventarium');
    expect(contenidoSubido).toContain('SUMMARY:Congreso de IA');
    // El enlace temporal no se deja colgado en el documento.
    expect(document.body.querySelector('a[download]')).toBeNull();
  });

  it('sin lugar no rompe ninguno de los tres destinos', async () => {
    await montar({ ...EVENTO, location: null });
    const [google, outlook] = enlaces();
    expect(google!.href).not.toContain('location=');
    expect(outlook!.href).not.toContain('location=');
  });

  it('no tiene violaciones de accesibilidad en ninguno de los dos temas', async () => {
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    document.documentElement.setAttribute('data-theme', 'light');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
