import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ModelosDelProveedorOut } from '../../../core/api/generated/models/modelos-del-proveedor-out';
import { ProveedorDelCatalogoOut } from '../../../core/api/generated/models/proveedor-del-catalogo-out';
import { PruebaDeConexionOut } from '../../../core/api/generated/models/prueba-de-conexion-out';

/** Lo que el formulario envía para probar una credencial sin guardarla. */
export interface PruebaDeConexion {
  provider: string;
  apiKey: string;
  apiBase?: string;
}

/**
 * El catálogo de proveedores y modelos, tal y como lo publica el backend.
 *
 * Tres llamadas, con papeles distintos:
 *
 * - `cargar()` (`GET /ai/catalog`) da la lista de **proveedores**, que es
 *   cerrada y solo cambia desplegando. Se cachea la promesa en curso: sin eso,
 *   cada ida y vuelta del router volvería a pedirla.
 * - `modelosDe()` (`GET /ai/catalog/{provider}/models`) pregunta al proveedor
 *   qué modelos tiene **ahora**. No se cachea aquí: ya lo hace el backend en
 *   Redis, y una segunda caché en el cliente solo añadiría una forma más de
 *   enseñar una lista vieja.
 * - `probar()` (`POST /ai/test-connection`) comprueba una clave que todavía no
 *   está guardada, y de paso devuelve los modelos que esa clave ve.
 *
 * No hay ninguna lista de proveedores ni de modelos escrita en el cliente.
 */
@Injectable({ providedIn: 'root' })
export class AiCatalogService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  private enCurso: Promise<readonly ProveedorDelCatalogoOut[]> | null = null;

  cargar(): Promise<readonly ProveedorDelCatalogoOut[]> {
    this.enCurso ??= firstValueFrom(
      this.http.get<ProveedorDelCatalogoOut[]>(this.api.url('/ai/catalog')),
    ).catch((error: unknown) => {
      // Un fallo no se cachea: la siguiente pantalla vuelve a intentarlo.
      this.enCurso = null;
      throw error;
    });
    return this.enCurso;
  }

  /**
   * Los modelos que el proveedor declara ahora mismo.
   *
   * Nunca rechaza por un fallo del proveedor: el backend degrada al catálogo
   * conocido y lo marca con `en_vivo: false` y un `motivo`, que es lo que el
   * formulario avisa. Solo rechaza si la petición en sí falla (sin sesión,
   * proveedor fuera del catálogo, límite de peticiones).
   */
  modelosDe(provider: string): Promise<ModelosDelProveedorOut> {
    return firstValueFrom(
      this.http.get<ModelosDelProveedorOut>(
        this.api.url(`/ai/catalog/${encodeURIComponent(provider)}/models`),
      ),
    );
  }

  /**
   * Prueba una credencial recién escrita. La clave viaja en el cuerpo porque
   * lo que se comprueba es justo la que todavía no se ha guardado.
   *
   * Igual que `modelosDe`, un `ok: false` es un resultado, no un rechazo.
   */
  probar(datos: PruebaDeConexion): Promise<PruebaDeConexionOut> {
    return firstValueFrom(
      this.http.post<PruebaDeConexionOut>(this.api.url('/ai/test-connection'), {
        provider: datos.provider,
        api_key: datos.apiKey,
        ...(datos.apiBase ? { api_base: datos.apiBase } : {}),
      }),
    );
  }
}
