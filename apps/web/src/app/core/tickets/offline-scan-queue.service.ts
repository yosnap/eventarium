import { Injectable, PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';

/** Un escaneo pendiente de sincronizar, tal como se guarda en IndexedDB. */
export interface QueuedScan {
  readonly clientScanId: string;
  readonly token: string;
  readonly clientScannedAt: string;
  readonly deviceLabel: string | null;
}

const NOMBRE_BASE_DE_DATOS = 'ia-week-check-in';
const VERSION_BASE_DE_DATOS = 1;
const ALMACEN = 'scan-queue';

/**
 * Cola offline de escaneos pendientes de sincronizar (fase 4 del PRD, fase 3
 * de trabajo).
 *
 * IndexedDB, no `localStorage` (decisión #11 del plan): volumen esperado
 * (cientos de escaneos en una jornada) y necesidad de consulta estructurada
 * (borrar por `clientScanId` sin releer y reescribir todo el almacén).
 *
 * No hace nada en SSR: `indexedDB` no existe en el servidor, y esta cola
 * solo tiene sentido en el navegador donde corre la app de escaneo.
 */
@Injectable({ providedIn: 'root' })
export class OfflineScanQueueService {
  private readonly esNavegador = isPlatformBrowser(inject(PLATFORM_ID));
  private conexion: Promise<IDBDatabase> | null = null;

  private abrir(): Promise<IDBDatabase> {
    if (!this.esNavegador) {
      return Promise.reject(new Error('IndexedDB no está disponible fuera del navegador.'));
    }
    this.conexion ??= new Promise((resolve, reject) => {
      const peticion = indexedDB.open(NOMBRE_BASE_DE_DATOS, VERSION_BASE_DE_DATOS);
      peticion.onupgradeneeded = () => {
        if (!peticion.result.objectStoreNames.contains(ALMACEN)) {
          peticion.result.createObjectStore(ALMACEN, { keyPath: 'clientScanId' });
        }
      };
      peticion.onsuccess = () => resolve(peticion.result);
      peticion.onerror = () => reject(peticion.error ?? new Error('No se pudo abrir IndexedDB.'));
    });
    return this.conexion;
  }

  async enqueue(escaneo: QueuedScan): Promise<void> {
    if (!this.esNavegador) {
      return;
    }
    const db = await this.abrir();
    await new Promise<void>((resolve, reject) => {
      const transaccion = db.transaction(ALMACEN, 'readwrite');
      transaccion.objectStore(ALMACEN).put(escaneo);
      transaccion.oncomplete = () => resolve();
      transaccion.onerror = () => reject(transaccion.error ?? new Error('No se pudo encolar.'));
    });
  }

  async pending(): Promise<QueuedScan[]> {
    if (!this.esNavegador) {
      return [];
    }
    const db = await this.abrir();
    return new Promise<QueuedScan[]>((resolve, reject) => {
      const transaccion = db.transaction(ALMACEN, 'readonly');
      const peticion = transaccion.objectStore(ALMACEN).getAll();
      peticion.onsuccess = () => resolve(peticion.result as QueuedScan[]);
      peticion.onerror = () => reject(peticion.error ?? new Error('No se pudo leer la cola.'));
    });
  }

  async remove(clientScanId: string): Promise<void> {
    if (!this.esNavegador) {
      return;
    }
    const db = await this.abrir();
    await new Promise<void>((resolve, reject) => {
      const transaccion = db.transaction(ALMACEN, 'readwrite');
      transaccion.objectStore(ALMACEN).delete(clientScanId);
      transaccion.oncomplete = () => resolve();
      transaccion.onerror = () =>
        reject(transaccion.error ?? new Error('No se pudo quitar de la cola.'));
    });
  }
}
