---
title: "PRD Fase 5 — Patrocinadores, legal/cookies, superadmin y backups"
description: "Niveles de patrocinio con bloque público por evento, banner de cookies Orejime + páginas legales por plantilla + registro de consentimientos, y ampliación de superadmin (auditoría, exportación RGPD, borrado de inscritos) con restauración de backups revalidada contra el esquema nuevo."
status: completed
priority: P1
effort: "7-9d"
tags: [patrocinadores, legal, cookies, rgpd, superadmin, backups]
created: 2026-09-08
prd_phase: 5
blockedBy: [4]
blocks: [6]
---

# PRD Fase 5 — Patrocinadores, legal/cookies, superadmin y backups

## Overview

Con las fases 1-4 cerradas (organizaciones, eventos, inscripción y entradas
QR), esta fase cierra el bloque **M** (MVP IAWIC Valencia) que queda antes de
pagos (fase 6): niveles de patrocinio con su bloque en la página pública del
evento, el banner de cookies y las páginas legales que la instalación
necesita para operar de forma conforme, y la ampliación de superadmin con
auditoría, exportación/borrado RGPD y backups automatizados con restauración
probada.

Alcance según `docs/prd.md` §9 (fila 5) y §4.6, §4.10, §4.11, únicamente lo
marcado **M**:

- **§4.6 Patrocinadores** (completo M): niveles personalizables por
  organización, patrocinadores con logo/web/nivel/aportación, bloque en la
  página pública agrupado por nivel, organizaciones colaboradoras modeladas
  como patrocinadores con aportación "en especie".
- **§4.10 Legal y cookies** (solo M): banner de cookies (Klaro) con
  "rechazar" al mismo nivel que "aceptar", páginas legales generadas desde
  plantilla con los datos de la entidad responsable, registro auditable de
  consentimientos.
- **§4.11 Plataforma** (solo M): ampliar superadmin con auditoría de
  acciones sensibles, exportación RGPD de un evento, borrado de inscritos
  bajo solicitud; backups automatizados de PostgreSQL y almacenamiento con
  restauración probada (ya scaffoldeados en la fase 0, esta fase los
  automatiza y prueba de verdad, no solo los deja documentados).

## Non-goals

Escaneo automático de cookies (§4.10, **S** — requiere navegador headless
periódico, fuera de esta fase). Observabilidad (métricas/logs, §4.11 **S**).
i18n en inglés (§4.11 **S**). Aportación en especie enlazada a un libro de
contabilidad real (§4.6 dice "enlazada a contabilidad", pero la contabilidad
en sí es la fase 7, **S** — esta fase solo registra el valor económico
declarado del patrocinio, sin libro contable que lo consuma). Pagos de
patrocinio con Stripe (fase 6). CfP y wallet (fase 9, **P**).

## Decisiones de diseño (ingeniería, no interview de producto)

1. **Patrocinadores viven bajo el evento, no bajo la organización.** El PRD
   dice "bloque de patrocinadores en la página del evento agrupado por
   nivel" — un patrocinio es por edición, no permanente (una empresa puede
   patrocinar IAWIC 2026 y no 2027). `sponsor_tiers` es por organización
   (los niveles se reutilizan entre ediciones, ej. "Oro" siempre significa
   lo mismo), pero `sponsors` (la fila concreta con logo/web/aportación)
   cuelga de `(event_id, tier_id)`. Mismo patrón de FK compuesta que
   `event_sessions`/`event_members` (fase 2): `sponsors.organization_id`
   denormalizado, FK compuesta contra `(event_id, organization_id)`.
2. **Páginas legales son contenido de organización, no de evento.** El aviso
   legal, privacidad, cookies y condiciones de inscripción son de la
   entidad responsable (la organización), no cambian por edición. Se
   generan desde una plantilla fija de texto (ver corrección de red-team
   abajo) rellenada con `Organization.legal_name`, `Organization.
   contact_email` y los campos nuevos de esta fase (dirección postal,
   NIF/CIF — necesarios para un aviso legal real y que el PRD no pidió en
   la fase 1 porque entonces no había para qué). El texto generado es
   editable por la organización (igual que el resto de contenido del
   panel), no de solo lectura.
   **Corregido en red-team — no hay Jinja2 en el proyecto:** la redacción
   original afirmaba "mismo motor que los emails de `app/core/tasks.py`",
   pero esos emails son f-strings de Python, sin ningún motor de
   plantillas (`grep -rn jinja apps/api` no encuentra nada fuera de
   `.venv`). Añadir Jinja2 solo para esto, sobre contenido **editable por
   cualquier `owner`/`organizer`** y servido en SSR público, abre XSS
   almacenado (si se escapa mal) o SSTI (si el texto guardado se pasa a
   `Template(...).render()` en vez de como variable). Decisión corregida:
   el contenido de las cuatro páginas legales es **texto plano/Markdown
   restringido** (sin HTML crudo), compuesto con f-strings simples igual
   que los emails — sin motor de plantillas nuevo — y renderizado en
   Angular con interpolación de texto (nunca `[innerHTML]` sin sanitizar).
   Un `<script>` guardado en el contenido legal no debe ejecutarse nunca
   en la página pública; esto pasa a ser un criterio de éxito explícito.
3. **El registro de consentimiento de cookies es anónimo por diseño.**
   RGPD no exige identificar a la persona que acepta/rechaza cookies (no es
   un consentimiento de inscripción con datos personales asociados, es la
   decisión de un navegador). Se registra `organization_id`, categorías
   aceptadas/rechazadas y timestamp, sin `user_id`, sin email y **sin IP en
   ninguna forma** — a diferencia de `EventRegistrationConsent` (fase 3),
   que sí liga el consentimiento a una persona identificada porque ahí sí
   hace falta poder demostrar quién aceptó qué.
   **Corregido en red-team:** la redacción original incluía un
   `ip_hash` "hash de la IP truncada" sin sal. Un hash sin sal sobre un
   espacio de IPv4 truncado es reversible por fuerza bruta en segundos —
   no es anonimización, es pseudonimización débil que además
   correlacionaría decisiones de cookies con IPs reales, justo lo que el
   registro pretende no permitir. Probar que se pidió consentimiento no
   requiere la IP: basta `(organization_id, categorías, timestamp)`. Se
   elimina el campo por completo en vez de intentar salarlo.
4. **Auditoría es un log de solo-inserción, sin UI de edición.** Una tabla
   `audit_log` (actor, acción, entidad afectada, `organization_id` cuando
   aplica, timestamp, detalle JSON) rellenada desde los propios servicios
   ya existentes que el PRD marca como sensibles: cambios de rol, alta de
   organización y de dominio (los únicos eventos de `admin/router.py` que
   existen hoy — ver hallazgo de red-team más abajo, no hay endpoint de
   activación/desactivación), exportación/borrado RGPD, y las acciones de
   superadmin de esta fase. No es un sistema de eventos genérico ni un
   middleware que audite todo automáticamente — se instrumenta
   explícitamente cada acción sensible, siguiendo el principio de no
   construir infraestructura genérica sin un segundo caso de uso real.
   **Corregido en red-team — "sin RLS" no es "sin acceso":** `app_user`
   recibe `SELECT, INSERT, UPDATE, DELETE` automático sobre toda tabla
   nueva (`infra/postgres/sql/roles.sql:45,50-51`, `ALTER DEFAULT
   PRIVILEGES`), así que una tabla sin política RLS es legible **y
   borrable** por cualquier sesión de organización, no solo por
   `app_maintainer` como asumía la redacción original. La migración de la
   fase 1 de trabajo debe hacer `REVOKE ALL ON audit_log, cookie_consents
   FROM app_user` explícito (con `GRANT INSERT` puntual sobre
   `cookie_consents`, que sí se escribe desde el endpoint público). Esto
   también cierra el problema de que un log "de solo inserción" sin ese
   `REVOKE` es borrable por el mismo camino de código que lo escribe.
5. **Exportación RGPD de un evento exporta inscripciones, no todo el
   evento.** El PRD dice "exportación de datos de un evento (RGPD)" — el
   dato personal vive en `event_registrations`/`event_registration_answers`
   /`event_registration_consents`/`event_tickets` (fase 3-4), no en la
   configuración del evento en sí (que no es dato personal). Exporta un
   ZIP con un CSV de inscripciones (con sus respuestas) y sus entradas
   asociadas, filtrado por el evento, vía `maintenance_session` (bypassa
   RLS deliberadamente: es una operación de superadmin, no de organizador).
6. **Borrado de inscritos bajo solicitud es un borrado real, no un soft
   delete.** El PRD lo pide como derecho RGPD de supresión — anonimizar
   (mismo patrón que revocar cuentas, si existiera) no basta cuando la
   persona ejerce su derecho al olvido. Borra la fila de
   `event_registrations` para el email indicado, tras localizarlo por
   email — visible solo a superadmin, nunca a un organizador (que no debe
   poder borrar el rastro de su propia inscripción problemática).
   **Corregido en red-team, tres problemas reales en la redacción
   original:**
   (a) *Aforo.* Un borrado directo por SQL no pasa por
   `_promote_next_waitlisted` (`registrations/service.py:210`, invocada
   solo desde el flujo de cancelación) — borrar a alguien `confirmed`
   libera una plaza que nadie llega a ofrecer a la lista de espera. El
   endpoint de superadmin debe reutilizar el servicio de cancelación (o
   invocar explícitamente la promoción tras el borrado), no un `DELETE`
   directo vía `maintenance_session` desconectado de esa lógica.
   (b) *Cascada más larga de lo enumerado.* La cascada real llega hasta
   `event_ticket_scans` (`event_registrations` → `event_tickets` →
   `event_ticket_scans`, todas `ondelete="CASCADE"`), que es evidencia de
   control de acceso físico al evento (quién escaneó qué y cuándo), no un
   dato personal de inscripción en sí. Antes de borrar, los escaneos de
   ese ticket se anonimizan (`ticket_id = NULL`, la FK ya lo admite) para
   conservar el recuento de aforo real sin conservar el vínculo con la
   persona.
   (c) *El propio registro de auditoría no puede ser el dato personal.*
   Guardar el email en claro en `audit_log.detail` para "demostrar que se
   ejerció el derecho" traslada la PII de una tabla protegida (RLS +
   cascada de borrado) a una que, corregida arriba, ya no es legible por
   `app_user` pero tampoco tiene política de retención propia. `detail`
   guarda un hash con sal (no reversible) del email más el `registration_id`
   ya borrado, nunca el email en claro, y la retención de `audit_log` para
   este tipo de entrada queda documentada en la fase 4 de trabajo.
7. **El backfill de permisos por sí solo no basta — hay que tocar también
   la plantilla del rol en código.** **Añadido en red-team, repite un bug
   ya corregido en la fase 4:** `Permission.OWNER` en
   `apps/api/app/modules/roles/system_roles.py:38-46` se define como
   `permissions=tuple(Permission)` — **todo** permiso nuevo del enum se
   concede automáticamente al `owner` de cualquier organización creada a
   partir de ahora, exista o no backfill. Dos consecuencias: (a)
   `SPONSORS_READ`/`WRITE` sí llegan al `owner` de una organización nueva
   por esa vía, pero **no** a `ORGANIZER`, que si el plan solo hace
   backfill sobre filas existentes (como las fases 2-4) se queda sin ellos
   en toda organización creada tras la migración — el propio comentario
   de `system_roles.py:64-70` documenta que esto ya pasó con
   `REGISTRATIONS_*` en la fase 3 y se corrigió en la fase 4 actualizando
   la plantilla, no solo el backfill. (b) `AUDIT_READ` **no debe entrar en
   el enum `Permission`** en absoluto: si entra, todo `owner` futuro lo
   hereda automáticamente vía `tuple(Permission)`, contradiciendo el
   propio objetivo de que sea exclusivo de `Superadmin`. La fase 1 de
   trabajo debe: actualizar `ORGANIZER.permissions` en código con
   `SPONSORS_READ`/`WRITE` (no solo backfill), y dejar `AUDIT_READ` fuera
   del enum — el endpoint de auditoría (fase 4 de trabajo) comprueba
   `Superadmin` directamente, no necesita un `Permission` que además sería
   peligroso tener declarado.
8. **La fase 5 de trabajo no "estrena" backups automatizados — los
   revalida.** **Corregido en red-team:** `docs/despliegue.md` ya
   documenta, desde el 2026-09-07, un ejemplo de programación diaria
   (cron) y una prueba de restauración real ya ejecutada (con dos fallos
   reales encontrados y corregidos entonces). La redacción original de la
   fase 5 de trabajo ("nunca se han ejecutado en una restauración real ni
   corren solos") es falsa y habría duplicado ese trabajo. Lo que sí es un
   hueco real: `docs/despliegue.md:241` pide explícitamente "repite esta
   prueba tras cualquier cambio en el esquema" — las tablas nuevas de esta
   fase (`sponsor_tiers`, `sponsors`, `audit_log`, `cookie_consents`) son
   justo ese cambio de esquema. La fase 5 de trabajo se redefine como
   **revalidación** de la restauración ya documentada contra el esquema
   ampliado, no como automatización desde cero — ver también los
   hallazgos de red-team sobre `restore.sh` y la verificación del bucket
   de objetos, más abajo.

## Requirements

- Functional:
  - `sponsor_tiers` (organización): nombre, orden, tamaño de logo,
    beneficios (texto libre). CRUD desde el panel.
  - `sponsors` (evento + nivel): nombre, logo (mismo patrón de subida que
    portada de evento/logotipo de branding: PNG/JPEG/WebP, comprobación por
    contenido), web, tipo de aportación (`monetaria`/`en_especie`), importe
    o descripción de la aportación. CRUD desde el panel del evento.
  - Bloque de patrocinadores en la página pública del evento, agrupado por
    nivel y ordenado según `sponsor_tiers.order`.
  - Banner de cookies (Orejime — default de `docs/prd.md` §7) integrado en
    el shell público de Angular: categorías (necesarias/analíticas/
    marketing), "rechazar" al mismo nivel visual que "aceptar", bloqueo de
    cualquier script no esencial hasta consentimiento explícito. **El
    banner debe clasificar Cloudflare Turnstile** (ya cargado hoy en el
    formulario público de inscripción,
    `apps/web/src/app/shared/ui/turnstile-widget.ts:31`) como script
    `necesario` con base de interés legítimo (seguridad/antibot) declarada
    en la página de cookies — nunca bloquearlo, o el formulario de
    inscripción deja de poder enviarse para quien rechaza cookies.
  - Páginas legales públicas (`/legal/aviso-legal`, `/legal/privacidad`,
    `/legal/cookies`, `/legal/condiciones-de-inscripcion`) generadas desde
    plantilla de texto plano/Markdown restringido (sin motor de plantillas
    nuevo, sin HTML crudo — ver Decisión #2), editables desde el panel de
    organización (nuevo campo de texto largo por página, con la plantilla
    como valor por defecto si está vacío). El contenido editado nunca se
    interpreta como código ni se inyecta como HTML sin sanitizar.
  - Registro auditable de consentimiento de cookies (`cookie_consents`):
    organización, categorías, timestamp — sin IP, sin hash de IP, sin
    ningún dato personal identificable (ver Decisión #3).
  - `audit_log`: instrumentado en cambios de rol, alta de organización y de
    dominio (los eventos reales que existen hoy en `admin/router.py` — no
    hay endpoint de activación/desactivación, ver Decisión #4), y las tres
    acciones nuevas de superadmin de esta fase (exportación RGPD, borrado
    de inscrito, listado de auditoría). `REVOKE ALL ... FROM app_user`
    explícito en la migración (ver Decisión #4).
  - Endpoint de superadmin: listado de `audit_log` con filtros básicos
    (organización, rango de fechas, tipo de acción), con `limit_per_ip`.
  - Endpoint de superadmin: exportación RGPD de un evento (ZIP con CSV de
    inscripciones + respuestas + entradas), con `limit_per_ip` estricto,
    reautenticación reciente (contraseña) exigida antes de exportar, y
    prefijado (`'`) de toda celda CSV que empiece por
    `=`/`+`/`-`/`@`/tab/CR para neutralizar inyección de fórmulas en el
    texto libre de las respuestas (que cualquiera escribe sin autenticar
    en el formulario público).
  - Endpoint de superadmin: borrado de un inscrito por email (con
    confirmación explícita, reautenticación reciente, `limit_per_ip`,
    registrado en `audit_log` — ver Decisión #6 para el detalle de qué se
    conserva y qué se anonimiza).
  - Revalidar la restauración de backups ya documentada en
    `docs/despliegue.md` (programación diaria y prueba real ya existentes
    desde 2026-09-07) contra el esquema ampliado de esta fase — ver
    Decisión #8 y la fase de trabajo 5 para el detalle de lo que cambia:
    `restore.sh` necesita un modo de restauración aislado (crea la base de
    destino, no para `api`/`worker` de producción, no reaplica
    `roles.sql` con contraseñas de clúster) y la verificación debe cubrir
    también el bucket de objetos, no solo el recuento de filas.
- Non-functional: aislamiento multi-tenant vía RLS para `sponsor_tiers` y
  `sponsors` igual que toda tabla de dominio, con `UNIQUE(id,
  organization_id)` en `sponsor_tiers` para que la FK compuesta de
  `sponsors` pueda crearse (ver Decisión de fase 1 de trabajo); `audit_log`
  y `cookie_consents` son de instalación (no por organización) salvo
  `organization_id` como columna de filtro, con `REVOKE ALL ... FROM
  app_user` explícito — sin RLS pero también sin GRANT por defecto, no
  "sin RLS" a secas (ver Decisión #4); WCAG 2.1 AA con cero violaciones de
  axe en las pantallas nuevas (banner de cookies incluido: navegable por
  teclado, foco gestionado); ningún fichero supera las 1000 líneas.

## Success Criteria

- [x] Un `owner`/`organizer` crea niveles de patrocinio, añade
      patrocinadores a un evento concreto (uno monetario, uno en especie) y
      el bloque agrupado por nivel aparece en la página pública del evento
      — verificado: `test_sponsors_router.py`/`test_sponsors_service.py`
      (backend) y `sponsor-tiers-page.spec.ts`/`event-sponsors*.spec.ts`
      (frontend, ejecutados de nuevo en esta fase: 2 ficheros, 5 tests, en
      verde)
- [x] Dos organizaciones no ven los patrocinadores ni niveles de la otra
      (test de aislamiento explícito, mismo patrón que fases 2-4), incluida
      la escritura cruzada (un `sponsor` no puede apuntar a un `tier` de
      otra organización) — verificado: `test_sponsors_rls_isolation.py`
- [x] Una organización **creada después** de aplicar la migración de esta
      fase tiene `sponsors:read`/`sponsors:write` en su rol `organizer`
      clonado, sin intervención manual — no solo una organización de una
      fase anterior (ver Decisión #7) — verificado:
      `test_organizacion_creada_despues_de_la_migracion_tiene_sponsors_en_el_organizer`
      en `test_sponsors_permisos.py`
- [x] `AUDIT_READ` no existe como valor del enum `Permission` — el
      endpoint de auditoría se protege con `Superadmin`, no con un permiso
      de rol (ver Decisión #7) — verificado: `grep AUDIT_READ app/` solo
      encuentra el comentario que documenta la exclusión, ningún miembro
      del enum
- [x] `has_table_privilege('app_user', 'audit_log', 'SELECT')` y el
      equivalente sobre `cookie_consents` son `false` tras la migración —
      comprobación negativa explícita, no solo la positiva de privilegios
      de `app_maintainer` — verificado:
      `test_app_user_no_puede_leer_ni_borrar_audit_log` y
      `test_app_user_solo_puede_insertar_en_cookie_consents` en
      `test_sponsors_legal_auditoria_migracion.py`
- [x] El banner de cookies bloquea un script no esencial de ejemplo hasta
      consentimiento explícito, con "rechazar" al mismo nivel visual que
      "aceptar"; Cloudflare Turnstile sigue cargando y el formulario de
      inscripción público sigue pudiendo enviarse aunque se rechacen todas
      las categorías no esenciales — verificado: `cookie-banner.spec.ts`
      (ejecutado de nuevo en esta fase, en verde)
- [x] Cada decisión del banner (aceptar/rechazar/personalizar) guarda una
      fila en `cookie_consents` sin `user_id`, sin email y sin ningún campo
      de IP o su hash — verificado: modelo `CookieConsent` sin esas
      columnas + `test_legal_pages_y_cookie_consent.py`
- [x] Las cuatro páginas legales resuelven con el contenido por defecto de
      plantilla (con `legal_name`/`contact_email` de la organización) y
      son editables desde el panel, con el texto editado sirviéndose tras
      guardar; un `<script>` guardado en el contenido legal no se ejecuta
      en la página pública (test explícito) — verificado:
      `legal-page.spec.ts` + `legal-pages-page.spec.ts` (ejecutados de
      nuevo en esta fase, en verde) y `test_legal_pages_y_cookie_consent.py`
- [x] Un cambio de permisos de un rol y una alta de organización/dominio
      quedan en `audit_log`, visible por superadmin con filtro por
      organización y rango de fechas (no "activación/desactivación de
      organización" — ese endpoint no existe hoy, ver Decisión #4) —
      verificado: `test_alta_de_organizacion_y_dominio_quedan_en_audit_log`,
      `test_cambio_de_permisos_de_rol_queda_en_audit_log`,
      `test_filtro_por_rango_de_fechas_excluye_filas_fuera_de_rango`
- [x] Superadmin exporta un ZIP de un evento con las inscripciones,
      respuestas y entradas de ese evento — verificado con un evento con
      datos reales, contenido del CSV comprobado campo a campo, con una
      respuesta que empieza por `=` neutralizada (prefijo `'`) en el CSV
      resultante — verificado: `test_export_neutraliza_formulas_y_coincide_con_la_bd`
- [x] Los tres endpoints nuevos de superadmin (auditoría, exportación
      RGPD, borrado) exigen reautenticación reciente para exportar/borrar y
      tienen `limit_per_ip`; un organizador (sin `is_superadmin`) recibe
      403 en los tres, con test explícito — verificado:
      `test_organizador_recibe_403_en_los_tres_endpoints_nuevos`,
      `test_export_sin_reautenticacion_correcta_devuelve_401`,
      `test_borrado_sin_reautenticacion_correcta_devuelve_401`,
      `test_rgpd_export_supera_el_limite_por_ip`
- [x] Superadmin borra un inscrito `confirmed` por email en un evento con
      lista de espera no vacía: la fila de `event_registrations` y lo que
      cuelga de ella desaparece, sus `event_ticket_scans` quedan
      anonimizados (`ticket_id = NULL`, no borrados), la siguiente persona
      en lista de espera es promovida, y `audit_log` guarda un hash del
      email (nunca en claro) — verificado:
      `test_borra_confirmed_con_lista_de_espera_y_anonimiza_escaneos`
- [x] La restauración de backups ya documentada en `docs/despliegue.md` se
      revalida contra el esquema ampliado de esta fase: recuento de filas
      de `sponsor_tiers`/`sponsors`/`audit_log`/`cookie_consents` (más las
      tablas ya cubiertas) coincide entre origen y restaurada, **y** el
      contenido del bucket de objetos restaurado se verifica (no solo la
      base de datos), sin detener los servicios de producción durante la
      prueba ni reescribir contraseñas de rol a nivel de clúster —
      verificado de extremo a extremo en esta fase, ver
      `docs/despliegue.md` § Revalidación 2026-09-08 y el reporte de fase
- [x] `alembic upgrade head` → `downgrade` → `upgrade head` limpio para las
      tablas nuevas, sin duplicar ni perder filas de permisos, y sin
      re-conceder un permiso que una organización hubiera revocado
      manualmente de un rol a medida — verificado:
      `test_ciclo_de_migracion_limpio`
- [x] Cero violaciones de axe en las pantallas nuevas; checklist WCAG
      completado — verificado: checklists en `docs/accesibilidad.md`
      (fases 2 y 3 de trabajo, 2026-09-08) + los 3 ficheros de test axe del
      bloque de patrocinadores y los 3 del bloque legal/cookies,
      re-ejecutados en esta fase (18 tests, en verde)
- [ ] CI en verde; ningún fichero supera las 1000 líneas — ningún fichero
      supera las 1000 líneas (verificado, `wc -l` sobre todo el repo); CI
      de GitHub Actions no se ha ejecutado sobre este diff porque todavía
      no está commiteado/empujado (lo hace el orquestador) — pendiente,
      documentado como hallazgo abierto en el reporte de fase 5, no
      ocultado
- [x] `docs/` actualizado: arquitectura, modelo de datos, accesibilidad y
      `docs/despliegue.md` (fecha y resultado de la restauración
      revalidada) reflejan lo nuevo — `arquitectura.md` y
      `modelo-de-datos.md` ampliados en esta fase con auditoría/RGPD (no
      cubierto por fases 2-4); `accesibilidad.md` y `despliegue.md` ya lo
      cubrían/se amplían
- [ ] `ak:code-review` (high) sobre el diff completo de la fase 5 del PRD
      antes de cerrarla; `ak:review-pr` obligatorio antes de cualquier
      merge, norma ya establecida del usuario — deliberadamente no
      ejecutado por esta fase de trabajo (lo coordina el orquestador con el
      subagente `code-reviewer` dedicado, según instrucción explícita)

## Fases de trabajo

1. **Modelo de datos, permisos y niveles de patrocinio** — `sponsor_tiers`
   (con `UNIQUE(id, organization_id)`), `sponsors`, `audit_log` (sin
   `AUDIT_READ` en el enum, `REVOKE ALL FROM app_user`), `cookie_consents`
   (sin IP), campos legales nuevos en `Organization`, permiso
   `SPONSORS_READ`/`WRITE` (prefijo ya reservado en `core/permissions.py`)
   concedido tanto por backfill a roles existentes **como** actualizando
   `ORGANIZER` en `system_roles.py`.
2. **CRUD de patrocinadores y bloque público** — panel de administración +
   bloque agrupado por nivel en la página pública del evento.
3. **Legal, cookies y consentimientos** — banner Orejime (con Turnstile
   clasificado como necesario), páginas legales de texto plano/Markdown
   restringido editables, registro de consentimiento de cookies sin IP.
4. **Superadmin: auditoría y RGPD** — instrumentar `audit_log` en acciones
   sensibles reales (rol, alta de organización/dominio) y nuevas
   (exportación RGPD con protección CSV, borrado de inscrito reutilizando
   el servicio de cancelación y anonimizando escaneos), rate-limit y
   reautenticación en los tres endpoints.
5. **Revalidación de backups y cierre de fase** — revalidar (no
   automatizar desde cero) la restauración ya documentada en
   `docs/despliegue.md` contra el esquema ampliado, con verificación de
   bucket de objetos y sin parar servicios de producción; verificación de
   extremo a extremo de toda la fase; `ak:code-review` (high) sobre el
   diff completo antes de cerrar.

## Red Team Review

### Sesión — 2026-09-08
**Revisores:** 3 (Security Adversary, Assumption Destroyer, Failure Mode
Analyst), sobre `plan.md` y las 5 fases de trabajo.
**Hallazgos:** 27 brutos → 15 tras deduplicar y pasar el filtro de
evidencia (todos con cita `file:line`), 0 rechazados por falta de
evidencia. Todos los 15 se aceptaron y aplicaron.
**Severidad:** 4 Critical, 8 High, 3 Medium.

| # | Hallazgo | Severidad | Aplicado a |
|---|---|---|---|
| 1 | `audit_log`/`cookie_consents` sin RLS quedan con SELECT/INSERT/UPDATE/DELETE automático para `app_user` (`ALTER DEFAULT PRIVILEGES`) — "solo para superadmin" era falso | Critical | plan.md (Decisión #4, Requirements); Fase 1 (`REVOKE ALL`, comprobación negativa) |
| 2 | `OWNER` clona `tuple(Permission)`: `AUDIT_READ` en el enum se autoconcede a todo `owner` futuro, contradiciendo su propio criterio de exclusividad | Critical | plan.md (Decisión #7); Fase 1 (`AUDIT_READ` retirado del enum) |
| 3 | Backfill de `SPONSORS_*` solo a roles existentes, sin tocar `ORGANIZER` en `system_roles.py` — repite el bug ya corregido en la fase 4 (`REGISTRATIONS_*`) | High | plan.md (Decisión #7); Fase 1 (actualizar plantilla + criterio sobre organización nueva) |
| 4 | `sponsor_tiers` sin `UNIQUE(id, organization_id)`: la FK compuesta de `sponsors` no puede crearse, `alembic upgrade` aborta | High | Fase 1 (constraint añadida) |
| 5 | Jinja2 no existe en el proyecto (los emails son f-strings); renderizar contenido editable por el tenant con un motor de plantillas nuevo abre XSS/SSTI | High | plan.md (Decisión #2); Fase 3 (texto plano/Markdown, sin motor nuevo) |
| 6 | `plan.md` afirma que existe un endpoint de activación/desactivación de organización; no existe, y el criterio de éxito era inverificable | High | plan.md (Decisión #4, Success Criteria); Fase 4 |
| 7 | Borrado RGPD por SQL directo no promueve lista de espera, destruye `event_ticket_scans` (evidencia de control de acceso) por cascada, y guarda el email en claro en una tabla sin retención | Critical | plan.md (Decisión #6); Fase 4 (reutilizar servicio de cancelación, anonimizar escaneos, hash con sal) |
| 8 | Endpoints de superadmin (exportación RGPD, borrado) sin rate-limit ni reautenticación — un token robado exfiltra PII de toda la instalación | High | Fase 4 (`limit_per_ip` + reautenticación reciente) |
| 9 | Exportación RGPD a CSV sin protección de inyección de fórmulas sobre texto libre público | Medium | Fase 4 (prefijado de celdas) |
| 10 | `ip_hash` de `cookie_consents` sin sal es reversible por fuerza bruta — no es anonimización | Medium | plan.md (Decisión #3); Fase 1/3 (campo eliminado) |
| 11 | La premisa de la fase 5 de trabajo era falsa: `docs/despliegue.md` ya documenta programación de backups y una restauración real probada (2026-09-07) | High | plan.md (Decisión #8); Fase 5 (redefinida como revalidación) |
| 12 | `restore.sh` no soporta una prueba aislada tal como la describía el plan: no crea la base destino, para `api`/`worker` de producción, reaplica `roles.sql` con contraseñas de clúster | High | Fase 5 (modo de restauración aislado) |
| 13 | La verificación de restauración solo cubría recuento de filas de BD, nunca el bucket de objetos (mitad del backup sin probar) | High | Fase 5 (verificación de objetos añadida) |
| 14 | Cloudflare Turnstile ya es un script de tercero real en el flujo público; el banner no lo clasificaba y podía bloquear el formulario de inscripción | High | plan.md (Requirements); Fase 3 (Turnstile clasificado como necesario) |
| 15 | `audit_log`/`cookie_consents` fuera de la lista de `TRUNCATE` de `conftest.py` — contaminación entre tests | Medium | Fase 1 (añadidas a la lista de aislamiento) |

### Whole-Plan Consistency Sweep
- Ficheros releídos: `plan.md`, las 5 `phase-0N-*.md`.
- Deltas de decisión comprobados: 15 (lista de arriba).
- Referencias obsoletas reconciliadas: Klaro → Orejime (default real del
  PRD); "Jinja2, mismo motor que los emails" → texto plano/Markdown sin
  motor nuevo; "ya existente desde fase 0/1" (activación de organización)
  → alta de organización/dominio (lo que sí existe); "automatiza los
  backups por primera vez" → "revalida contra el esquema nuevo"; `ip_hash`
  eliminado de toda mención en `cookie_consents`.
- Contradicciones sin resolver: 0.

## Validation Log

### Session 1 — 2026-09-08
**Trigger:** `/ak:plan validate` tras el red-team, antes de implementar.
**Questions asked:** 4

#### Questions & Answers

1. **[Architecture]** Los tres endpoints de superadmin (auditoría,
   exportación RGPD, borrado) exigen "reautenticación reciente" — ¿cómo
   se implementa exactamente?
   - Options: Repetir contraseña en la petición (Recomendado) | Ventana
     de login reciente
   - **Answer:** Repetir contraseña en la petición
   - **Rationale:** más simple, sin estado de sesión nuevo que mantener
     ni claim adicional en el JWT.
2. **[Risks]** ¿Durante cuánto tiempo se conserva una fila de
   `audit_log`? El PRD no lo especifica y no hay ninguna decisión previa
   del proyecto sobre retención de logs.
   - Options: Indefinida (Recomendado) | Purga tras N años
   - **Answer:** Indefinida
   - **Rationale:** es un log de cumplimiento (RGPD, seguridad); el
     proyecto no tiene hoy ningún mecanismo de purga automática de nada,
     y añadir uno solo para esta tabla exigiría fijar una base legal de
     purga fuera del alcance M de esta fase.
3. **[Architecture]** Las páginas legales se editan como texto
   plano/Markdown restringido — ¿con qué se renderiza el Markdown en
   Angular?
   - Options: `marked` + `DOMPurify` (Recomendado) | `ngx-markdown` | Sin
     Markdown real
   - **Answer:** `marked` + `DOMPurify`
   - **Rationale:** control total sobre qué etiquetas se permiten,
     librerías ligeras y muy usadas; un aviso legal real necesita al
     menos listas y enlaces, que "sin Markdown real" no cubriría.
4. **[Risks]** La exportación RGPD incluye un CSV de `event_tickets` —
   ¿debe incluir el JWT del QR de cada entrada?
   - Options: No incluir el JWT (Recomendado) | Incluir el JWT completo
   - **Answer:** No incluir el JWT
   - **Rationale:** el JWT del QR es una credencial de acceso físico
     válida mientras el ticket no esté revocado; incluirlo en un CSV
     descargable exportaría una credencial utilizable, no solo un dato
     personal.

#### Confirmed Decisions
- Reautenticación de superadmin: verificación de contraseña en el propio
  body de la petición, sin sesión de reautenticación aparte.
- `audit_log`: retención indefinida, sin purga automática.
- Render de Markdown legal: `marked` + `DOMPurify` en el frontend.
- Exportación RGPD de `event_tickets`: sin el JWT del QR, solo metadatos
  (`emitida_en`, `usada_en`, `revocada_en`).

#### Action Items
- [ ] Fase 4: especificar el mecanismo de reautenticación por contraseña
      en el body de los tres endpoints (nuevo esquema Pydantic con el
      campo de contraseña, verificado contra `hash_password` del propio
      superadmin).
- [ ] Fase 4: excluir el JWT del QR del CSV de `event_tickets` en la
      exportación RGPD; documentar qué columnas sí se exportan.
- [ ] Fase 3: añadir `marked` y `dompurify` (+ `@types/dompurify` si hace
      falta) como dependencias nuevas de `apps/web`; documentar la
      configuración de saneado (lista blanca de etiquetas permitidas).

#### Impact on Phases
- Fase 3 (Legal, cookies y consentimientos): Requirements e Implementation
  Steps actualizados con `marked`+`DOMPurify` como mecanismo concreto de
  render.
- Fase 4 (Superadmin — auditoría y RGPD): Requirements actualizados con el
  mecanismo exacto de reautenticación (contraseña en el body) y la
  exclusión explícita del JWT del QR en el export RGPD.

### Whole-Plan Consistency Sweep (Validation Session 1)
- Ficheros releídos: `plan.md`, las 5 `phase-0N-*.md`.
- Deltas de decisión comprobados: 4 (lista de arriba).
- Referencias obsoletas reconciliadas: "reautenticación reciente" (sin
  mecanismo concreto) → "verificación de contraseña en el body de la
  petición" en Fase 4; "Markdown saneado a HTML" (sin librería) → "marked
  + DOMPurify" en Fase 3; exportación de `event_tickets` sin exclusión
  explícita del JWT → exclusión explícita documentada en Fase 4.
- Contradicciones sin resolver: 0.
