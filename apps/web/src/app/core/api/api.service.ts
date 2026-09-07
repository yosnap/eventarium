import { HttpHeaders } from '@angular/common/http';
import { Injectable, PLATFORM_ID, REQUEST, inject } from '@angular/core';
import { isPlatformServer } from '@angular/common';

import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly plataforma = inject(PLATFORM_ID);
  private readonly peticion = inject(REQUEST, { optional: true });

  readonly isServer = isPlatformServer(this.plataforma);

  /**
   * URL de un endpoint.
   *
   * En el navegador es relativa para que la petición viaje al mismo host y arrastre la
   * cookie. En SSR hay que apuntar a la API por su nombre de red interna.
   */
  url(path: string): string {
    const ruta = `${environment.apiPath}${path.startsWith('/') ? path : `/${path}`}`;
    return this.isServer ? `${environment.serverApiBaseUrl}${ruta}` : ruta;
  }

  /**
   * Cabeceras que SSR debe reenviar a la API.
   *
   * El servidor de Angular llama a la API con su propio `Host` interno, que no
   * identifica a ninguna organización. `X-Forwarded-Host` lleva el host original de la
   * persona que visita la web; la API solo lo acepta desde una IP de confianza.
   */
  serverForwardHeaders(): HttpHeaders {
    let cabeceras = new HttpHeaders();
    if (!this.isServer || !this.peticion) {
      return cabeceras;
    }

    const original = this.peticion.headers.get('x-forwarded-host') ?? this.hostDeLaUrl();
    if (original) {
      cabeceras = cabeceras.set('X-Forwarded-Host', original);
    }
    const protocolo = this.peticion.headers.get('x-forwarded-proto');
    if (protocolo) {
      cabeceras = cabeceras.set('X-Forwarded-Proto', protocolo);
    }
    return cabeceras;
  }

  /**
   * Nombre de host actual, sin puerto: lo usa el embed de Twitch, que exige
   * declarar en `parent` el dominio que lo aloja (si no coincide, Twitch se
   * niega a cargar el reproductor, tanto en SSR como ya hidratado en el
   * navegador).
   */
  currentHost(): string {
    if (this.isServer) {
      return this.hostDeLaUrl()?.split(':')[0] ?? 'localhost';
    }
    return typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  }

  private hostDeLaUrl(): string | null {
    const host = this.peticion?.headers.get('host');
    if (host) {
      return host;
    }
    try {
      return this.peticion ? new URL(this.peticion.url).host : null;
    } catch {
      return null;
    }
  }
}
