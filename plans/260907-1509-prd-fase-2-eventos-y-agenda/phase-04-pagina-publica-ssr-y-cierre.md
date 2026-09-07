---
phase: 4
title: "Fase 4: Página pública del evento con SSR, cierre de fase"
status: pending
priority: P1
effort: "2-3d"
dependencies: [3]
---

# Fase 4: Página pública del evento con SSR, cierre de fase

## Overview

Lo que convierte todo lo anterior en algo visible al mundo: listado público de
eventos, página de detalle con agenda y OG tags, página de detalle de sesión tipo
charla (ponencia) y página de perfil de ponente — las cuatro con SSR real. Más el
cierre de la fase: documentación, accesibilidad y verificación de extremo a
extremo.

**Cambios de esta fase tras el red-team del plan** (ver `plan.md` → `## Red Team
Review`): el patrón de SSR con datos es el de `ThemingService`
(`serverForwardHeaders()` + `TransferState`), no el de `home-page.ts` (que no hace
ninguna petición HTTP); la página de sesión tiene endpoint propio, anidado bajo el
evento y filtrado por su estado de publicación; el prefijo público queda fijado a
`/public/...`, no como decisión abierta; los endpoints públicos y
`check-slug` llevan límite de peticiones; el 404 de un evento no público se
verifica por el código de estado HTTP real de la respuesta SSR, con un mecanismo
explícito para producirlo — no se asume que "sin contenido" ya es suficiente.

## Requirements

- Functional:
  - `GET /public/events`: eventos `published` + `public` de la organización
    actual (resuelta por host), sin autenticar.
  - `GET /public/events/{slug}`: detalle de un evento `published` + `public`; 404
    en cualquier otro caso (borrador, archivado, oculto, privado, o slug ajeno) —
    **el mismo 404** en todos los casos, para no filtrar por el código de estado
    si un evento existe pero no es visible.
  - `GET /public/events/{slug}/sessions/{session_id}`: detalle de una sesión,
    **anidado bajo el evento** — filtra por el `slug` del evento padre y exige
    que ese evento sea `published` + `public`, además de que la propia sesión
    pertenezca a él. Sin este anidamiento, un `id` de sesión (UUIDv7, ordenado
    temporalmente y por tanto con entropía reducida frente a un v4 dentro de una
    ventana de tiempo conocida) sería enumerable y filtraría agendas de eventos
    sin publicar.
  - `GET /public/speakers/{public_slug}`: perfil de ponente con fila en
    `speaker_public_profiles`; mismo 404 uniforme si no existe.
  - Los cuatro endpoints anteriores llevan `limit_per_ip`, mismo patrón que el
    resto de endpoints públicos del proyecto (`check-slug`,
    `resend-verification`…) — sin esto, cualquiera puede recorrer el directorio
    completo de ponentes o la agenda de un evento a máxima velocidad sin
    autenticarse.
  - `event-page.ts` (SSR): hero, descripción, lugar, agenda agrupada por día con
    sus sesiones y participantes, etiquetas OG (`og:title`, `og:description`,
    `og:image` con la portada).
  - `session-page.ts` (SSR): detalle de una sesión tipo charla — título, resumen,
    ponentes (enlazando a su perfil si es público), materiales (enlaces con
    `rel="noopener noreferrer"`), vídeo embebido según `video_platform`.
  - `speaker-page.ts` (SSR): la lista blanca de campos definida en la fase 3, más
    redes sociales, historial de sesiones agrupado por evento con enlace a cada
    evento.
  - Listado público de eventos en una ruta propia `/eventos`: página fija de esta
    fase, **sin** integrarse en el sistema de bloques del branding (ese sistema
    no existe todavía — `organization_branding` solo tiene `template_key` fijo,
    colores, tipografías y enlaces sociales; el "renderer de bloques" del PRD
    §4.1 es una pieza pendiente de una fase futura, no algo ya construido en la
    fase 1 que esta fase pudiera reabrir).
- Non-functional: SSR real, verificado con `X-Forwarded-Host` y sin ejecutar
  JavaScript en el cliente; el 404 de un evento no público se refleja en el
  código de estado HTTP de la respuesta SSR, no solo en el contenido renderizado;
  WCAG 2.1 AA.

## Architecture

- `apps/api/app/modules/events/public_router.py` (**crear**): monta en
  `/public/events` y `/public/speakers` (prefijo fijado, no una decisión
  pendiente); usa `speakers_repository.py` y `events_repository.py` (fase 2/3),
  pasando explícitamente el filtro `published + public` en cada consulta — nunca
  confiando en que RLS ya lo hace. `require_turnstile` no aplica (son lecturas,
  no escrituras), pero sí `limit_per_ip` en los cuatro endpoints.
- `apps/web/src/app/core/seo/meta.service.ts` (**crear**): envuelve `Meta`/`Title`
  de `@angular/platform-browser` para fijar OG tags de forma consistente —
  primer uso de `Meta` en el proyecto, documentarlo en `docs/arquitectura.md`.
- `apps/web/src/app/features/public/events/event-page.ts`, `session-page.ts`,
  `speaker-page.ts` (**crear**): SSR con datos siguiendo el patrón real del
  proyecto — el de `ThemingService`
  (`apps/web/src/app/core/theming/theming.service.ts`), no el de `home-page.ts`
  (que solo espera un `import()` dinámico, sin ninguna petición HTTP). Cada
  página:
  1. Pide los datos con `ApiService.url()` + cabeceras de
     `ApiService.serverForwardHeaders()`, para que en SSR la petición lleve el
     `X-Forwarded-Host` real de la visita y no el `Host` interno del contenedor
     — sin esto, `get_current_organization` no resuelve ninguna organización (o,
     peor, en desarrollo cae al atajo `DEFAULT_ORGANIZATION_SLUG` y sirve datos
     de otra organización bajo el host de la primera).
  2. Guarda el resultado en `TransferState` con una clave propia por página, para
     que el cliente no repita la petición al hidratar.
  3. Si la API responde 404, la página establece un estado "no encontrado" que
     `apps/web/src/server.ts` traduce en el código de estado HTTP real de la
     respuesta SSR (no un 200 con un panel de error) — mismo mecanismo que hay
     que introducir de todas formas para la ruta comodín (`{ path: '**',
     redirectTo: '' }` hoy no distingue "no existe" de "raíz").
- Rutas nuevas en `app.routes.ts`: `/eventos`, `/eventos/:slug`,
  `/eventos/:slug/sesiones/:sessionId`, `/ponentes/:slug`.

## Related Code Files

- Create: `apps/api/app/modules/events/public_router.py`
- Modify: `apps/api/app/modules/events/repository.py` (filtro de publicación
  parametrizado, reutilizado por administración y por lo público)
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_events_public.py`
- Create: `apps/web/src/app/core/seo/meta.service.ts`
- Create: `apps/web/src/app/features/public/events/event-page.ts`,
  `session-page.ts`, `speaker-page.ts` (+ `.spec.ts`)
- Modify: `apps/web/src/app/app.routes.ts`, `apps/web/src/server.ts`
- Modify: `docs/arquitectura.md`, `docs/modelo-de-datos.md`, `docs/accesibilidad.md`

## Implementation Steps

1. Router público de eventos, sesiones y ponentes, con el filtro de publicación
   explícito en cada consulta y `limit_per_ip` en los cuatro endpoints.
2. Mecanismo de 404 real en SSR: estado "no encontrado" en el componente de
   página → `server.ts` fija el código de estado de la respuesta antes de
   escribirla.
3. Servicio de `Meta`/OG tags reutilizable.
4. Página pública de evento: hero, agenda por día, participantes con enlace a su
   perfil si es público. Carga de datos con `serverForwardHeaders()` +
   `TransferState`.
5. Página pública de sesión/ponencia: detalle, materiales (enlaces con
   `rel="noopener noreferrer"`), vídeo embebido según `video_platform`
   (`youtube`/`vimeo`/`twitch`/`other` — para `other` un enlace directo en vez de
   un iframe genérico).
6. Página pública de ponente: lista blanca de campos, redes, historial agrupado
   por evento.
7. Rutas y navegación desde la home pública.
8. Tests backend: evento en borrador/oculto/privado → 404 en detalle y ausente en
   listado; sesión de un evento no publicado → 404 aunque se conozca su `id`;
   ponente sin perfil público → 404; aislamiento entre organizaciones en los
   cuatro endpoints públicos (lectura **y** que el filtro de publicación no
   dependa solo de RLS).
9. Tests frontend: axe en las tres pantallas nuevas; verificar que las etiquetas
   OG y el contenido del evento están presentes en el HTML servido con
   `X-Forwarded-Host` simulado, antes de cualquier hidratación en cliente.
10. **Cierre de fase**: recorrer el checklist de `Success Criteria` del
    `plan.md` completo; actualizar `docs/arquitectura.md` (patrón de páginas
    públicas SSR con datos vía `serverForwardHeaders()` + `TransferState`,
    servicio de OG tags, claves foráneas compuestas), `docs/modelo-de-datos.md`
    (las cinco tablas nuevas, incluida `speaker_public_profiles`),
    `docs/accesibilidad.md` (checklist de esta fase).
11. Verificación de extremo a extremo manual: crear un evento con agenda de
    varios días y tipos de sesión, asignar ponentes con roles distintos
    (incluida una persona con dos roles en la misma sesión), publicarlo, activar
    el perfil público de un ponente en autoservicio (no desde el panel de
    administración), y comprobar en el navegador (no solo con tests) que la
    página pública del evento, de una ponencia y del ponente se ven
    correctamente, con SSR real (deshabilitar JavaScript o inspeccionar el HTML
    servido antes de hidratar, y comprobar el código de estado 404 de un evento
    en borrador).
12. Regenerar `apps/api/openapi.json` + cliente TypeScript.

## Success Criteria

- [ ] Un evento en borrador o no público responde **404 real** (código de estado
      HTTP, no solo contenido vacío) en su página pública, sin distinguir por
      qué
- [ ] Una sesión de un evento no publicado da 404 aunque se conozca su `id`
      directamente
- [ ] La página de evento sirve HTML con el contenido ya renderizado sin necesitar
      JavaScript, verificado con una petición que fija `X-Forwarded-Host`
- [ ] Las etiquetas OG (`og:title`, `og:description`, `og:image`) están presentes
      y usan los datos reales del evento
- [ ] El vídeo se embebe según su plataforma; para "otro" se ofrece un enlace en
      vez de un iframe que podría no cargar
- [ ] El perfil de ponente muestra la lista blanca de campos (nunca
      `profile_data` completo) y el historial agrupado por evento, con enlaces a
      las páginas de los eventos correspondientes
- [ ] Dos organizaciones no pueden ver los eventos, sesiones ni ponentes públicos
      de la otra cambiando el host — verificado también contra el filtro de
      publicación, no solo contra RLS
- [ ] Los cuatro endpoints públicos tienen límite de peticiones por IP
- [ ] Cero violaciones de axe en las cuatro pantallas públicas nuevas
- [ ] `docs/` refleja el estado real del código
- [ ] Verificación de extremo a extremo ejecutada en el navegador y documentada,
      no solo declarada

## Risk Assessment

- Confiar en que RLS ya filtra por estado de publicación sería un error: RLS
  aísla por **organización**, no por si un evento está publicado — un borrador de
  la propia organización sigue siendo visible bajo RLS para cualquiera que
  resuelva el host correcto, así que el filtro de publicación tiene que ser
  explícito en cada consulta pública, cubierto por un test que lo pruebe
  directamente (crear un evento en borrador y comprobar que el endpoint público
  no lo devuelve, no solo que el de administración sí).
- Copiar el precedente equivocado de SSR (`home-page.ts`, que no pide datos)
  serviría las páginas públicas vacías en producción o, en desarrollo, con datos
  de la organización equivocada por el atajo de `DEFAULT_ORGANIZATION_SLUG` →
  seguir explícitamente el patrón de `ThemingService`
  (`serverForwardHeaders()` + `TransferState`), verificado con un test que fija
  `X-Forwarded-Host` y comprueba que el HTML servido trae el evento correcto.
- Dar códigos de error distintos según la razón de la ausencia (borrador vs
  oculto vs slug inexistente) permitiría a alguien enumerar qué eventos existen
  sin verlos → 404 uniforme en todos los casos, mismo patrón que ya usa el
  registro para no filtrar si un correo existe.
- Sin límite de peticiones, los endpoints públicos (y en especial el listado de
  ponentes) son un objetivo trivial de scraping masivo del directorio completo →
  `limit_per_ip` en los cuatro, mismo patrón que el resto del proyecto.
