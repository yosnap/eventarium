import 'fake-indexeddb/auto';

import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { OfflineScanQueueService, type QueuedScan } from './offline-scan-queue.service';

const ESCANEO: QueuedScan = {
  clientScanId: 'scan-1',
  token: 'token-de-prueba',
  clientScannedAt: '2026-09-08T10:00:00.000Z',
  deviceLabel: null,
};

describe('OfflineScanQueueService', () => {
  let servicio: OfflineScanQueueService;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    servicio = TestBed.inject(OfflineScanQueueService);
  });

  afterEach(async () => {
    for (const pendiente of await servicio.pending()) {
      await servicio.remove(pendiente.clientScanId);
    }
  });

  it('guarda un escaneo y lo devuelve en `pending`', async () => {
    await servicio.enqueue(ESCANEO);

    const pendientes = await servicio.pending();

    expect(pendientes).toEqual([ESCANEO]);
  });

  it('quita un escaneo de la cola tras sincronizarlo', async () => {
    await servicio.enqueue(ESCANEO);

    await servicio.remove(ESCANEO.clientScanId);

    expect(await servicio.pending()).toEqual([]);
  });

  it('guardar el mismo `clientScanId` dos veces no duplica la entrada', async () => {
    await servicio.enqueue(ESCANEO);
    await servicio.enqueue({ ...ESCANEO, deviceLabel: 'segundo intento' });

    const pendientes = await servicio.pending();

    expect(pendientes).toHaveLength(1);
    expect(pendientes[0].deviceLabel).toBe('segundo intento');
  });
});
