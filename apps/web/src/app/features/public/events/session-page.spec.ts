import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { SessionPage } from './session-page';

function sesionDetalle() {
  return {
    id: 's1',
    session_type: 'talk',
    title: 'Charla de apertura',
    description: 'Una charla estupenda.',
    starts_at: '2026-10-01T09:00:00Z',
    ends_at: '2026-10-01T10:00:00Z',
    room: 'Sala A',
    video_platform: 'youtube',
    video_url: 'https://youtu.be/abc123',
    materials: [{ label: 'Diapositivas', url: 'https://ejemplo.com/slides.pdf' }],
    participants: [{ display_name: 'Ana Ponente', role_key: 'speaker', public_slug: 'ana' }],
    event_slug: 'iawic-2026',
    event_title: 'IA Week in Cascais 2026',
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('SessionPage', () => {
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
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('muestra la sesión, sus ponentes, materiales y el vídeo embebido', async () => {
    const fixture = TestBed.createComponent(SessionPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.componentRef.setInput('sessionId', 's1');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026/sessions/s1')
      .flush(sesionDetalle());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Charla de apertura');
    expect(texto).toContain('Ana Ponente');
    expect(texto).toContain('Diapositivas');
    const iframe = fixture.nativeElement.querySelector('iframe.video') as HTMLIFrameElement;
    expect(iframe.getAttribute('src')).toContain('youtube-nocookie.com/embed/abc123');
    expect(iframe.getAttribute('title')).toBeTruthy();
    // axe-core no puede analizar un `<iframe>` a un dominio real (youtube-nocookie.com)
    // dentro de jsdom — falla al intentar comunicarse con su `contentWindow`. Las
    // otras dos pruebas de esta página (sin iframe: enlace directo y 404) sí
    // verifican accesibilidad de extremo a extremo.
  });

  it('ofrece un enlace directo en vez de un iframe para la plataforma "other"', async () => {
    const fixture = TestBed.createComponent(SessionPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.componentRef.setInput('sessionId', 's2');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026/sessions/s2')
      .flush({
        ...sesionDetalle(),
        id: 's2',
        video_platform: 'other',
        video_url: 'https://ejemplo.com/video.mp4',
        participants: [],
        materials: [],
      });
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('iframe.video')).toBeNull();
    const enlace = fixture.nativeElement.querySelector('a[href="https://ejemplo.com/video.mp4"]');
    expect(enlace).not.toBeNull();
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('marca "no encontrado" cuando la sesión no existe', async () => {
    const fixture = TestBed.createComponent(SessionPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.componentRef.setInput('sessionId', 'no-existe');
    fixture.detectChanges();
    http
      .expectOne(
        (peticion) => peticion.url === '/api/v1/public/events/iawic-2026/sessions/no-existe',
      )
      .flush({ detail: 'La sesión no existe.' }, { status: 404, statusText: 'Not Found' });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('No hemos encontrado este evento');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
