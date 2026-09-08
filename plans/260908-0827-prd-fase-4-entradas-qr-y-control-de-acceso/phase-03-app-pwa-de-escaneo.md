---
phase: 3
title: "Fase 3: App PWA de escaneo (frontend)"
status: done
priority: P1
effort: "2-2.5d"
dependencies: [2]
---

# Fase 3: App PWA de escaneo (frontend)

## Overview

La herramienta que de verdad usa el voluntariado el día del evento: cámara
para escanear, resultado inmediato y legible, cola offline que no pierde
escaneos si se corta la conexión, y búsqueda manual como respaldo.

## Requirements

- Functional:
  - `@angular/service-worker` añadido al proyecto (`ng add`), `ngsw-config.json`
    con estrategia de caché para el shell de la app y las llamadas de
    `/tickets/*` en modo `freshness` (nunca servir un resultado de escaneo
    cacheado como si fuera nuevo).
  - `manifest.webmanifest` propio para esta ruta (nombre corto "Check-in",
    icono, `display: standalone`, `start_url` apuntando a
    `/admin/events/:id/check-in` con el id del evento activo si lo hay, o al
    selector de evento si no).
  - Página `/admin/events/:id/check-in`: vídeo de la cámara
    (`getUserMedia`), `BarcodeDetector` nativo si `window.BarcodeDetector`
    existe, si no una librería de respaldo (decidir en la implementación
    entre `@zxing/browser` y `jsQR` según tamaño de bundle y mantenimiento
    activo); al detectar un código, lo encola inmediatamente (óptimista: no
    espera respuesta del servidor para mostrar "procesando") y sigue
    escaneando.
  - Cola offline en IndexedDB: cada escaneo pendiente guarda
    `{client_scan_id, token, client_scanned_at, device_label}`; un
    `navigator.onLine`/evento `online` dispara la sincronización contra
    `scan/batch`; reintento con backoff simple si la sincronización falla
    (no un backoff exponencial complejo — la app ya reintenta al siguiente
    evento `online` o cada cierto intervalo corto mientras haya pendientes).
  - Resultado en pantalla: por cada escaneo, un estado visual con icono +
    texto (no solo color) para `valid`/`duplicate`/`revoked`/`expired`/
    `invalid_signature`/`not_found`, con nombre y email de la persona cuando
    la respuesta los incluya; mientras está en cola sin sincronizar, un
    estado "pendiente de confirmar" distinto de "válido".
  - Búsqueda manual integrada en la misma página (campo de texto, resultados
    de `GET .../tickets/search`, botón de check-in manual por resultado).
  - Contador visible: escaneados/total de inscripciones `confirmed` del
    evento, actualizado tras cada sincronización con éxito.
  - `RegistrationsService`/nuevo `TicketsService` (`apps/web/src/app/core/`)
    con los métodos que llaman a los endpoints de la fase 2, más las
    utilidades de cola IndexedDB (puede vivir en el mismo servicio o en uno
    dedicado `offline-scan-queue.service.ts` si crece — decidir al
    implementar según cuánto código tenga cada pieza, no antes).
- Non-functional:
  - Accesibilidad WCAG 2.1 AA: el resultado de un escaneo se anuncia con
    `aria-live`, los controles táctiles cumplen el tamaño mínimo ya usado en
    el resto del proyecto (`app-button`), y ningún estado se comunica solo
    por color.
  - La página funciona (sigue escaneando y encolando) con la app en segundo
    plano temporalmente o con la pantalla bloqueada según lo permita el
    navegador — sin implementar nada más allá de lo que la Web API de
    cámara ya ofrece; no se persigue un comportamiento "en segundo plano
    real" tipo app nativa, fuera de alcance de una PWA.

## Validation

- Test de componente: la cola offline guarda un escaneo cuando
  `navigator.onLine` es `false` y lo sincroniza al pasar a `true` (mock del
  evento `online` y de `TicketsService`).
- Test de componente: un resultado `duplicate` muestra quién y cuándo hizo el
  primer check-in, no solo "ya usado".
- Test de accesibilidad (axe) en la página de check-in y en el listado de
  resultados de búsqueda manual.
- Prueba manual en navegador real (Comet, mismo patrón que las fases
  anteriores): activar el modo avión a mitad de una tanda de escaneos,
  comprobar que se encolan, desactivarlo y comprobar que sincronizan solos
  sin duplicar ningún check-in ya contado.

## Risk & Rollback

- Riesgo: soporte de `BarcodeDetector` desigual entre navegadores/dispositivos
  del voluntariado (móviles personales, no un parque de dispositivos
  gestionado) — mitigado por la librería de respaldo de la decisión #10 del
  plan; si ninguna vía funciona en un dispositivo concreto, la búsqueda
  manual sigue disponible como respaldo real, no solo teórico.
- Riesgo: instalar la PWA exige HTTPS en producción (ya lo es, Caddy con
  certificado) y un manifest servido correctamente — verificar en el
  despliegue real antes de dar la fase por cerrada, no solo en `ng serve`.
- Rollback: la ruta y el service worker son aditivos; quitar la entrada del
  manifest de rutas no afecta al resto del panel de organizador.
