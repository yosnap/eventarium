import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

/** `valid`/`duplicate`/etc. — igual que `TicketScanResult` de la API (fase 4, fase 2). */
export type TicketScanResult =
  'valid' | 'duplicate' | 'expired' | 'invalid_signature' | 'revoked' | 'not_found' | 'manual';

export interface ScanInput {
  readonly token: string;
  readonly clientScanId: string;
  readonly clientScannedAt: string;
  readonly deviceLabel: string | null;
}

export interface TicketScanResultOut {
  readonly client_scan_id: string;
  readonly result: TicketScanResult;
  readonly ticket_id: string | null;
  readonly registration_id: string | null;
  readonly full_name: string | null;
  readonly email: string | null;
  readonly used_at: string | null;
  readonly used_by_event_member_id: string | null;
}

export interface TicketSearchItem {
  readonly ticket_id: string;
  readonly registration_id: string;
  readonly full_name: string;
  readonly email: string;
  readonly used_at: string | null;
}

interface RegistrationStatsResponse {
  readonly confirmed: number;
}

/**
 * Escaneo y check-in de entradas (fase 4 del PRD, fase 3 de trabajo).
 *
 * Mismo patrón que las llamadas autenticadas del panel de organizador
 * (`EventRegistrations`): `HttpClient` + `ApiService.url()` directos, sin
 * cabeceras propias — la sesión y el contexto de organización ya los
 * resuelven los interceptores globales.
 */
@Injectable({ providedIn: 'root' })
export class TicketsService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  private cuerpoDeEscaneo(escaneo: ScanInput): Record<string, unknown> {
    return {
      token: escaneo.token,
      client_scan_id: escaneo.clientScanId,
      client_scanned_at: escaneo.clientScannedAt,
      device_label: escaneo.deviceLabel,
    };
  }

  async scanBatch(eventId: string, escaneos: readonly ScanInput[]): Promise<TicketScanResultOut[]> {
    const resultado = await firstValueFrom(
      this.http.post<TicketScanResultOut[]>(this.api.url(`/events/${eventId}/tickets/scan/batch`), {
        scans: escaneos.map((escaneo) => this.cuerpoDeEscaneo(escaneo)),
      }),
    );
    return [...resultado];
  }

  async search(eventId: string, q: string): Promise<TicketSearchItem[]> {
    const resultado = await firstValueFrom(
      this.http.get<TicketSearchItem[]>(this.api.url(`/events/${eventId}/tickets/search`), {
        params: { q },
      }),
    );
    return [...resultado];
  }

  async checkInManual(eventId: string, ticketId: string): Promise<TicketScanResultOut> {
    return firstValueFrom(
      this.http.post<TicketScanResultOut>(
        this.api.url(`/events/${eventId}/tickets/${ticketId}/check-in-manual`),
        {},
      ),
    );
  }

  /**
   * Total de inscripciones `confirmed` del evento, para el denominador del
   * contador — reutiliza `/registrations/stats` (fase 3 del PRD) en vez de
   * duplicar el recuento en un endpoint propio.
   */
  async getConfirmedCount(eventId: string): Promise<number> {
    const stats = await firstValueFrom(
      this.http.get<RegistrationStatsResponse>(
        this.api.url(`/events/${eventId}/registrations/stats`),
      ),
    );
    return stats.confirmed;
  }
}
