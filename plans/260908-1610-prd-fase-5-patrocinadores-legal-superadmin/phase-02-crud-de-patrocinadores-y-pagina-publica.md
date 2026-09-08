---
phase: 2
title: "Fase 2: CRUD de patrocinadores y bloque público"
status: completed
priority: P1
effort: "2-2.5d"
dependencies: [1]
---

# Fase 2: CRUD de patrocinadores y bloque público

## Overview

Backend y frontend de administración para niveles y patrocinadores, más el
bloque agrupado por nivel en la página pública del evento (SSR, mismo patrón
que el resto de bloques públicos de la fase 2 del PRD).

## Requirements

- Functional:
  - `GET/POST/PATCH/DELETE /organizations/{id}/sponsor-tiers` — CRUD de
    niveles, reordenables (`display_order`).
  - `GET/POST/PATCH/DELETE /events/{event_id}/sponsors` — CRUD de
    patrocinadores del evento, con subida de logo (mismo patrón de
    comprobación por contenido que portada de evento/logotipo de branding).
  - Borrar un nivel con patrocinadores activos → 409 (no 500).
  - Panel de administración: pantalla de niveles (organización) y pantalla
    de patrocinadores dentro del evento (con selector de nivel).
  - Página pública del evento: bloque de patrocinadores agrupado por nivel
    y ordenado por `display_order`, solo con patrocinadores del evento
    `published`+`public` (un evento en borrador/oculto no expone
    patrocinadores igual que no expone su agenda).
  - Patrocinador "en especie" muestra su descripción de aportación en el
    panel (no en la página pública — el PRD no pide hacer pública la
    valoración económica de nadie).
- Non-functional: mismo estándar WCAG 2.1 AA (axe) que el resto de
  pantallas públicas; subida de logo reutiliza el helper ya existente de
  comprobación de tipo por contenido (no MIME declarado), sin duplicarlo.

## Implementation Steps

1. Backend: repository + service + router de `sponsor_tiers` (organización).
2. Backend: repository + service + router de `sponsors` (evento), con
   subida/borrado de logo (borrado diferido a después del commit, mismo
   patrón que portada de evento — hallazgo #13 del red-team de la fase 2).
3. Frontend admin: pantalla de niveles + pantalla de patrocinadores del
   evento.
4. Frontend público: bloque de patrocinadores en la página del evento
   (componente nuevo, reutilizando el patrón SSR de `ThemingService`/
   `serverForwardHeaders` si necesita datos propios, o recibiéndolos ya
   resueltos desde el componente padre de la página del evento si no).
5. `openapi.json` + cliente TypeScript regenerados.

## Success Criteria

- [x] Un `owner`/`organizer` crea 3 niveles, los reordena, y el orden se
      refleja en el panel y en la página pública — verificado con
      `test_crear_reordenar_y_listar_niveles` (backend) y
      `sponsor-tiers-page.spec.ts` (reordenación admin) +
      `event-page.spec.ts` (orden en el bloque público)
- [x] Añadir un patrocinador monetario y uno en especie a un evento, ambos
      con logo subido, y verificar que el bloque público los agrupa
      correctamente por nivel — verificado con
      `test_bloque_publico_agrupa_por_nivel_muestra_el_logo_y_oculta_aportacion`,
      que sube un logo real contra el almacén de objetos y comprueba la
      agrupación pública
- [x] Un evento en borrador u oculto no expone su bloque de patrocinadores
      en ninguna ruta pública (test explícito, mismo patrón que fase 2) —
      `test_evento_en_borrador_no_expone_su_bloque_de_patrocinadores`
- [x] Borrar un nivel con patrocinadores activos da 409 con mensaje claro
      en el panel, no un error genérico —
      `test_borrar_nivel_con_patrocinadores_da_409_con_mensaje_claro`
- [x] Cero violaciones de axe en las pantallas nuevas (panel + bloque
      público) — `sponsor-tiers-page.spec.ts`, `event-sponsors.spec.ts`,
      `event-page.spec.ts` (bloque público con patrocinadores), todos con
      `esperarSinViolacionesDeAccesibilidad`; suite completa de `apps/web`
      en verde (139 tests)
- [x] `openapi.json` y el cliente TypeScript generado están al día (CI
      falla si no) — regenerados con `make api-types`, sin diff pendiente
      tras la regeneración

## Risk & Rollback

- Riesgo: acoplar el bloque público de patrocinadores directamente al
  componente de la página del evento puede inflarlo — si al implementarlo
  ya hay tres bloques similares (agenda, ponentes, patrocinadores)
  compitiendo por el mismo patrón de carga de datos, extraer un composable
  compartido en ese momento, no antes.
- Rollback: patrocinadores y niveles son puramente aditivos sobre la
  página pública del evento (un bloque más, sin tocar los existentes);
  desactivar el bloque en el frontend sin tocar el backend es reversible
  en un solo commit si aparece un problema visual el día del evento.
