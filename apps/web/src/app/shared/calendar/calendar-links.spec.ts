import { describe, expect, it } from 'vitest';

import {
  contenidoIcs,
  nombreFicheroIcs,
  urlGoogleCalendar,
  urlOutlook,
  type EventoParaCalendario,
} from './calendar-links';

const URL_EVENTO = 'https://eventarium.test/eventos/congreso';

const EVENTO: EventoParaCalendario = {
  slug: 'congreso',
  title: 'Congreso de IA',
  starts_at: '2026-10-01T07:00:00Z',
  ends_at: '2026-10-01T16:30:00Z',
  timezone: 'Europe/Madrid',
  location: 'Palacio de Congresos, Calle Mayor 1',
};

describe('urlGoogleCalendar', () => {
  it('lleva título, rango en UTC, detalles y lugar', () => {
    const url = new URL(urlGoogleCalendar(EVENTO, URL_EVENTO));

    expect(url.origin + url.pathname).toBe('https://calendar.google.com/calendar/render');
    expect(url.searchParams.get('action')).toBe('TEMPLATE');
    expect(url.searchParams.get('text')).toBe('Congreso de IA');
    // La barra del rango va sin codificar: codificada, Google no lo reconoce.
    expect(url.search).toContain('dates=20261001T070000Z/20261001T163000Z');
    expect(url.searchParams.get('details')).toBe(URL_EVENTO);
    expect(url.searchParams.get('location')).toBe('Palacio de Congresos, Calle Mayor 1');
  });

  it('omite el lugar cuando el evento no lo tiene', () => {
    const url = new URL(urlGoogleCalendar({ ...EVENTO, location: null }, URL_EVENTO));
    expect(url.searchParams.has('location')).toBe(false);
  });

  it('codifica los caracteres que romperían la URL', () => {
    const url = new URL(
      urlGoogleCalendar({ ...EVENTO, title: 'IA & Datos: ¿qué "cambia"?' }, URL_EVENTO),
    );
    expect(url.searchParams.get('text')).toBe('IA & Datos: ¿qué "cambia"?');
  });
});

describe('urlOutlook', () => {
  it('lleva asunto, inicio y fin en ISO UTC, cuerpo y lugar', () => {
    const url = new URL(urlOutlook(EVENTO, URL_EVENTO));

    expect(url.origin + url.pathname).toBe('https://outlook.live.com/calendar/0/deeplink/compose');
    expect(url.searchParams.get('path')).toBe('/calendar/action/compose');
    expect(url.searchParams.get('rru')).toBe('addevent');
    expect(url.searchParams.get('subject')).toBe('Congreso de IA');
    expect(url.searchParams.get('startdt')).toBe('2026-10-01T07:00:00Z');
    expect(url.searchParams.get('enddt')).toBe('2026-10-01T16:30:00Z');
    expect(url.searchParams.get('body')).toBe(URL_EVENTO);
    expect(url.searchParams.get('location')).toBe('Palacio de Congresos, Calle Mayor 1');
  });

  it('omite el lugar cuando el evento no lo tiene', () => {
    const url = new URL(urlOutlook({ ...EVENTO, location: null }, URL_EVENTO));
    expect(url.searchParams.has('location')).toBe(false);
  });
});

describe('contenidoIcs', () => {
  const AHORA = new Date('2026-09-29T10:00:00Z');

  it('genera un VCALENDAR con un único VEVENT y saltos de línea CRLF', () => {
    const ics = contenidoIcs(EVENTO, URL_EVENTO, AHORA);
    const lineas = ics.split('\r\n');

    expect(ics.endsWith('\r\n')).toBe(true);
    expect(ics).not.toMatch(/(?<!\r)\n/); // ningún LF suelto
    expect(lineas[0]).toBe('BEGIN:VCALENDAR');
    expect(lineas).toContain('VERSION:2.0');
    expect(lineas.filter((l) => l === 'BEGIN:VEVENT')).toHaveLength(1);
    expect(lineas).toContain('END:VEVENT');
    expect(lineas).toContain('END:VCALENDAR');
  });

  it('lleva UID estable, marca de creación y rango en UTC', () => {
    const lineas = contenidoIcs(EVENTO, URL_EVENTO, AHORA).split('\r\n');

    expect(lineas).toContain('UID:congreso@eventarium');
    expect(lineas).toContain('DTSTAMP:20260929T100000Z');
    expect(lineas).toContain('DTSTART:20261001T070000Z');
    expect(lineas).toContain('DTEND:20261001T163000Z');
    expect(lineas).toContain('SUMMARY:Congreso de IA');
    expect(lineas).toContain(`URL:${URL_EVENTO}`);
  });

  it('escapa comas, puntos y coma, barras y saltos de línea del texto', () => {
    const ics = contenidoIcs(
      { ...EVENTO, title: 'A, B; C \\ D\nE', location: 'Sala 1, planta 2' },
      URL_EVENTO,
      AHORA,
    );
    const lineas = ics.split('\r\n');

    expect(lineas).toContain('SUMMARY:A\\, B\\; C \\\\ D\\nE');
    expect(lineas).toContain('LOCATION:Sala 1\\, planta 2');
  });

  it('omite LOCATION cuando no hay lugar', () => {
    const ics = contenidoIcs({ ...EVENTO, location: null }, URL_EVENTO, AHORA);
    expect(ics).not.toContain('LOCATION');
  });

  it('pliega las líneas largas a 75 octetos sin partir caracteres multibyte', () => {
    const titulo = 'Jornada de inteligencia artificial y ñandúes ✨ '.repeat(6).trim();
    const ics = contenidoIcs({ ...EVENTO, title: titulo }, URL_EVENTO, AHORA);
    const codificador = new TextEncoder();

    for (const linea of ics.split('\r\n')) {
      expect(codificador.encode(linea).length).toBeLessThanOrEqual(75);
    }
    // Desplegar (quitar CRLF + espacio) devuelve el título íntegro: no se perdió ni se partió nada.
    const desplegado = ics.replace(/\r\n /g, '');
    expect(desplegado).toContain(`SUMMARY:${titulo}`);
  });
});

describe('nombreFicheroIcs', () => {
  it('usa el slug del evento', () => {
    expect(nombreFicheroIcs(EVENTO)).toBe('congreso.ics');
  });
});
