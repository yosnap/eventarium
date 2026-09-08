---
phase: 3
title: "Fase 3: Legal, cookies y consentimientos"
status: completed
priority: P1
effort: "2-2.5d"
dependencies: [1]
---

# Fase 3: Legal, cookies y consentimientos

## Overview

Banner de cookies (Orejime), páginas legales generadas desde plantilla de
texto y editables, y el registro auditable de consentimiento de cookies.
Depende solo del modelo de datos de la fase 1 de trabajo, no del CRUD de
patrocinadores — puede implementarse en paralelo con la fase 2 de trabajo
si hiciera falta, aunque este plan las secuencia.

## Requirements

- Functional:
  - Integrar Orejime (default fijado en `docs/prd.md` §7 — "Orejime (Klaro
    accesible) — a confirmar frente a Klaro en la fase 5 según auditoría
    WCAG") en el shell público de Angular: categorías `necesarias`
    (siempre activa, sin opción de rechazar — son necesarias para que la
    web funcione, no rastreo), `analiticas`, `marketing`. Botones
    "Aceptar todo" / "Rechazar todo" / "Personalizar" con el mismo peso
    visual, ninguno preseleccionado ni destacado sobre el otro (WCAG +
    requisito explícito del PRD).
  - **Cloudflare Turnstile se clasifica como `necesaria`, nunca bloqueable
    por el banner.** Corrección de red-team: `apps/web/src/app/shared/ui/
    turnstile-widget.ts:31` ya carga
    `https://challenges.cloudflare.com/turnstile/v0/api.js` en el
    formulario público de inscripción (fase 3 del PRD) — no es un script
    hipotético "para cuando haya uno real", ya existe y es crítico para el
    flujo de negocio. Si el banner lo trata como no esencial y lo bloquea
    hasta consentimiento, quien rechace cookies no puede enviar el
    formulario de inscripción a un evento. La página de cookies generada
    en esta misma fase debe declararlo explícitamente (base legal: interés
    legítimo de seguridad/antibot).
  - Bloqueo real de scripts no esenciales hasta consentimiento: se prueba
    contra un script de ejemplo de categoría `analiticas`/`marketing`
    (para que el día que se añada uno real de verdad ya esté cubierto),
    **nunca contra Turnstile**, que debe seguir cargando decida lo que
    decida la persona en el banner.
  - `POST /public/cookie-consent`: guarda `cookie_consents` (organización,
    categorías, timestamp — **sin IP ni hash de IP**, ver Decisión #3 del
    plan). Sin autenticación, `limit_per_ip` igual que el resto de
    endpoints públicos.
  - Cuatro páginas públicas (`/legal/aviso-legal`, `/legal/privacidad`,
    `/legal/cookies`, `/legal/condiciones-de-inscripcion`): SSR, sirven el
    contenido editado de la organización o la plantilla por defecto si es
    `NULL`. **Plantillas de texto plano/Markdown restringido compuestas
    con f-strings de Python, sin motor de plantillas nuevo** (corrección
    de red-team: no hay Jinja2 en el proyecto — los emails de
    `app/core/tasks.py` son f-strings, no plantillas; introducir un motor
    nuevo para renderizar contenido que el propio requisito de abajo hace
    editable por el tenant abriría XSS si se escapa mal, o SSTI si el
    texto guardado se pasa como plantilla en vez de como variable).
    Rellenadas con `legal_name`, `contact_email`, `legal_address`,
    `tax_id`. <!-- Updated: Validation Session 1 - render de Markdown --> El
    Markdown se convierte a HTML en el frontend con `marked` (parseo) +
    `DOMPurify` (saneado, lista blanca explícita de etiquetas permitidas:
    párrafos, negrita/cursiva, listas, enlaces — nunca `<script>`,
    `<iframe>`, atributos `on*`), nunca `[innerHTML]` directo sobre el
    contenido guardado sin pasar antes por `DOMPurify.sanitize()`.
  - Panel de organización: pantalla para editar el contenido de las cuatro
    páginas legales (textarea largo por página, con botón "restaurar
    plantilla por defecto" que pone el campo a `NULL` de nuevo).
  - Enlaces a las cuatro páginas legales en el pie de página público
    (footer del shell de Angular), visibles en toda página pública.
- Non-functional: WCAG 2.1 AA en el banner (navegable por teclado, foco
  gestionado al abrir/cerrar, sin trampa de foco); páginas legales con SSR
  real (mismo patrón `ThemingService`/`X-Forwarded-Host` que el resto de
  páginas públicas de organización, no el patrón de página de evento que
  usa el slug del evento); un `<script>` guardado como contenido legal por
  un `owner`/`organizer` no se ejecuta nunca en la página pública.

## Implementation Steps

1. Backend: plantillas de texto/Markdown de las cuatro páginas legales
   (f-strings, sin motor de plantillas nuevo) + endpoint de lectura
   (público, resuelto por organización vía host) + endpoint de edición
   (panel, `organizations:write`).
2. Backend: `POST /public/cookie-consent` + repository de `cookie_consents`
   (sin campo de IP).
3. Frontend: comprobación rápida de accesibilidad de Orejime (default) —
   si falla, cambiar a Klaro antes de continuar. Integración en el shell
   público — banner, categorías (Turnstile clasificado como `necesaria`),
   bloqueo de un script de ejemplo no esencial, llamada a `cookie-consent`
   al decidir.
4. Frontend: añadir `marked` y `dompurify` a `apps/web`; cuatro páginas
   legales públicas (SSR, Markdown → `marked` → `DOMPurify` → HTML) +
   enlaces en el footer.
5. Frontend admin: pantalla de edición de contenido legal.
6. Revisión de accesibilidad (axe) del banner y las páginas nuevas; test
   explícito de que un `<script>` guardado en el contenido legal no se
   ejecuta al servirse.

## Success Criteria

- [x] El banner aparece en la primera visita, bloquea el script de ejemplo
      no esencial hasta decisión explícita, y "Aceptar todo"/"Rechazar
      todo" tienen el mismo peso visual (captura o test de snapshot que lo
      verifique, no solo revisión manual) — verificado con
      `cookie-banner.spec.ts` (comprueba que ninguno de los tres botones
      lleva la clase `primario` y que las tres comparten clase)
- [x] Cloudflare Turnstile sigue cargando y el formulario público de
      inscripción sigue pudiendo enviarse aunque se rechacen todas las
      categorías no esenciales del banner — test explícito. **Con matiz:**
      verificado por aislamiento arquitectónico (`CookieConsentService` no
      referencia Turnstile en ningún punto, comprobado en
      `cookie-banner.spec.ts`) y por inspección de `turnstile-widget.ts`
      (su renderizado depende solo de `environment.turnstileEnabled`, sin
      ninguna dependencia de consentimiento); no se ha ejecutado un test de
      navegador real con Turnstile cargando de verdad (`TURNSTILE_ENABLED`
      está desactivado en desarrollo, igual que en las fases anteriores del
      PRD — ver `docs/accesibilidad.md`, sección Turnstile de la fase 1)
- [x] Cada decisión (aceptar/rechazar/personalizar) queda en
      `cookie_consents` sin `user_id`, sin email y **sin ningún campo de
      IP o su hash** (test explícito sobre las columnas de la fila, no
      solo sobre `user_id`/email) — `test_legal_pages_y_cookie_consent.py`
- [x] Las cuatro páginas legales resuelven con el contenido de plantilla
      por defecto (con los datos reales de una organización de prueba) si
      no se ha editado nada — verificado con test y manualmente contra la
      API de desarrollo con datos reales
- [x] Editar el contenido de una página legal desde el panel y comprobar
      que la página pública sirve el texto editado, no la plantilla
- [x] Un `<script>alert(1)</script>` guardado como contenido de una página
      legal no se ejecuta al visitar la página pública — test explícito,
      no solo revisión visual (backend: `test_un_script_guardado_no_se_
      ejecuta_al_servirse`; frontend: `legal-page.spec.ts`, comprueba que
      no aparece `<script>` real en el DOM)
- [x] "Restaurar plantilla por defecto" vuelve a servir la plantilla,
      verificado tras editar y restaurar
- [x] Los cuatro enlaces legales están en el footer de toda página pública
- [x] La página de `/legal/cookies` declara explícitamente Turnstile como
      script necesario, con su base legal
- [x] Cero violaciones de axe en el banner y las páginas legales nuevas

## Decisión confirmada — banner propio en vez de Orejime/Klaro

**Desviación aceptada por el usuario (2026-09-08), tras revisión explícita:**
en vez de integrar Orejime o Klaro, se construyó un componente `CookieBanner`
de primera parte (sin dependencia de terceros para el banner en sí).
Justificación del agente, validada por el usuario: Orejime existe
específicamente para corregir problemas de accesibilidad de Klaro, y un
componente propio permite verificar los criterios WCAG reales con tests
directos (foco gestionado, sin trampa de foco, mismo peso visual de los tres
botones) en vez de confiar en el comportamiento de una librería externa no
auditada por este equipo. Documentado también en `docs/accesibilidad.md`.
Esto sustituye la mitigación de riesgo original de abajo (que asumía
integrar una de las dos librerías) — se deja el texto original por
trazabilidad histórica.

## Risk & Rollback

- Riesgo (histórico, superado por la decisión de arriba): `docs/prd.md` deja
  pendiente "a confirmar frente a Klaro en la fase 5 según auditoría WCAG"
  — implementar sin hacer esa comprobación puede significar reescribir la
  integración si Orejime falla en la práctica. Mitigación original: la
  comprobación de accesibilidad de Orejime es el primer paso de
  implementación de esta fase de trabajo, antes de integrar nada más — si
  falla, cambiar a Klaro antes de escribir el resto de la
  fase, no después.
- Riesgo: clasificar mal Turnstile (como no esencial, o sin declararlo en
  la página de cookies) rompe el flujo de negocio más importante del
  proyecto (inscripción a un evento) para cualquiera que rechace cookies.
  Mitigación: es un criterio de éxito explícito con test, no solo una nota
  en Requirements.
- Rollback: el banner y las páginas legales no dependen de ninguna otra
  fase de trabajo de este plan; deshabilitar el banner (dejar de
  cargarlo) es un cambio de una línea si aparece un bloqueo real el día
  del evento, aunque incumpliría el requisito legal — no es una opción
  real de producción, solo de emergencia técnica puntual.
