---
title: "PRD Fase 1 — Organizaciones y usuarios"
description: "Registro libre de organizadores con subdominio automático, panel de organización, branding editable, roles con campos de perfil, miembros y cuenta propia. Primera funcionalidad de negocio sobre los cimientos de la fase 0."
status: pending
priority: P1
effort: "8-12d"
tags: [registro, organizaciones, branding, roles, miembros, email]
created: 2026-09-07
prd_phase: 1
blockedBy: []
blocks: []
---

# PRD Fase 1 — Organizaciones y usuarios

## Nomenclatura

Este plan cubre la **fase 1 del PRD** (`docs/prd.md` §9). Dentro se subdivide en cinco
fases de trabajo numeradas 1-5, cada una con su versión menor y su rama.

Se adopta el prefijo `prd-fase-N` en el nombre del directorio porque la fase 0 generó
confusión: sus cinco fases internas se leían como fases del producto. **Fase del PRD** es
el producto; **fase de trabajo** es un tramo dentro de este plan.

## Overview

La fase 0 dejó los cimientos: multi-tenant con RLS, autenticación, almacenamiento,
tareas asíncronas, theming por organización y CI. El backend de organizaciones, roles y
miembros existe y está probado, pero **no hay interfaz que lo use** y **no hay forma de
darse de alta**: hoy solo un superadministrador crea organizaciones por CLI o API.

Esta fase convierte eso en un producto usable: cualquiera se registra, crea su
organización, obtiene su subdominio y administra su equipo desde el panel.

Fuentes: `docs/prd.md` §3-4 y §9 (fase 1), `docs/arquitectura.md`, y las decisiones de
producto tomadas el 2026-09-07 (ver «Decisiones nuevas»).

## Decisiones nuevas (no estaban en el PRD)

El PRD describe la inscripción de **asistentes**, no el alta de **organizadores**. Esto
se decidió el 2026-09-07 y se incorpora aquí:

| Decisión | Detalle |
|---|---|
| Registro libre | Cualquiera crea una cuenta y una organización desde la web, sin intervención del superadministrador |
| Un subdominio por organización | `mi-org.dominio-de-la-instalacion` registrado automáticamente al crear la organización |
| Dominio propio | Fuera de alcance: quien lo quiera hace fork y despliega su instalación (fase 8 del PRD para el caso general) |
| Proxy en producción | EasyPanel (Traefik). Caddy queda solo para desarrollo |

## Dependencia que adelanta trabajo

El registro necesita **verificar el correo**, y eso exige infraestructura de envío que el
PRD situaba en la fase 3. Se adelanta a la fase de trabajo 1 de este plan.

No es un adelanto gratuito: sin verificación, cualquiera crearía organizaciones con
correos ajenos y ocuparía subdominios. La alternativa —permitir crear sin verificar—
dejaría basura en la tabla de organizaciones y subdominios secuestrados, que es
justamente lo que el subdominio automático vuelve valioso para un atacante.

## Fases de trabajo

| # | Fase | Versión | Rama | Estado |
|---|---|---|---|---|
| 1 | [Correo y verificación](./phase-01-correo-y-verificacion.md) | 0.7.0 | `feat/0.7.0-correo-y-verificacion` | Done |
| 2 | [Registro y alta de organización](./phase-02-registro-y-alta-de-organizacion.md) | 0.8.0 | `feat/0.8.0-registro-y-alta-de-organizacion` | Pending |
| 3 | [Panel de organización y branding](./phase-03-panel-de-organizacion-y-branding.md) | 0.9.0 | `feat/0.9.0-panel-de-organizacion-y-branding` | Pending |
| 4 | [Roles, campos de perfil y miembros](./phase-04-roles-campos-y-miembros.md) | 0.10.0 | `feat/0.10.0-roles-campos-y-miembros` | Pending |
| 5 | [Cuenta propia, recuperación y cierre de fase](./phase-05-cuenta-propia-y-cierre.md) | 0.11.0 | `feat/0.11.0-cuenta-propia-y-cierre` | Pending |

Esfuerzo por fase de trabajo tras red-team + predict: 1 (2-2.5d, incluye páginas web e
índice del barrido), 2 (3.5-4d, incluye el servicio `scheduler` confirmado y la página
de creación de organización), 3 (2-2.5d), 4 (2.5-3d), 5 (3-3.5d, incluye recuperación
de contraseña, aviso al correo antiguo y la función `SECURITY DEFINER` del selector).

Dependencias: **estrictamente secuencial** 1 → 2 → 3 → 4 → 5. La 2 necesita el correo de
la 1; la 3, una organización creada por la 2; la 4, el panel de la 3.

## Protocolo de rama, revisión y merge

Se aplica a cada fase de trabajo, sin excepciones. El detalle vive en
[`CONTRIBUTING.md`](../../CONTRIBUTING.md); aquí queda el resumen operativo:

```
develop → feat/X.Y.0-nombre → (trabajo) → PR a develop → merge --no-ff
```

1. **Rama desde `develop`** actualizado, con el nombre de la tabla de arriba.
2. **Commits atómicos** en formato *Conventional Commits*, en español de España.
3. **Antes de abrir el PR**, en local y en verde:
   - `make lint` (ruff, mypy --strict, ESLint, Prettier)
   - `make test` (pytest contra servicios reales, Vitest con axe)
   - `make audit` (pip-audit, pnpm audit, gitleaks)
   - Si cambió la API: `make api-types` y el `openapi.json` incluido en el commit
4. **PR a `develop`** con: qué entra, por qué, y **cómo se ha verificado** — evidencia
   concreta, no «funciona». Si algo quedó sin verificar, se dice.
5. **Revisión antes del merge**: CI en verde en los tres jobs *y* revisión del diff con
   el checklist de PR de `CONTRIBUTING.md`. Un CI verde no sustituye a leer el cambio:
   en la fase 0, tres fallos reales (SSR degradado a cliente, worker que no arrancaba,
   restauración que rompía las migraciones) devolvían códigos de éxito.
6. **Merge `--no-ff`** a `develop` y actualización del estado de la fase en este plan.
7. **`main` solo por pull request**, nunca por push directo. La rama está protegida.

### Versionado

Cada fase de trabajo sube una **versión menor** en `apps/api/pyproject.toml` y
`apps/web/package.json`. Las correcciones sobre una versión ya publicada suben el patch.
El release a `main` con su tag `vX.Y.Z` se hace al cerrar cada fase o agrupando varias,
según convenga; el tag apunta siempre a un commit de `main`.

## Goals

| # | Goal | Prioridad |
|---|------|-----------|
| 1 | Cualquiera se registra, verifica su correo y crea su organización sin intervención manual | P1 |
| 2 | Cada organización queda servida en su propio subdominio desde el minuto uno | P1 |
| 3 | El panel permite editar organización, branding y plantilla, y ver el resultado | P1 |
| 4 | Los roles y sus campos de perfil se gestionan desde la interfaz, respetando las reglas anti-escalada | P1 |
| 5 | Se invita a personas al equipo y estas completan su perfil según su rol | P1 |
| 6 | Todo lo anterior cumple WCAG 2.1 AA y no rompe el aislamiento entre organizaciones | P1 |

## Non-goals

Eventos, sesiones y agenda (fase 2 del PRD); inscripciones (fase 3); entradas y QR
(fase 4); patrocinadores, pagos y contabilidad (fases 5-7); dominio propio por
organización (fase 8); inglés y otros idiomas (fase 8).

Tampoco entra la interfaz de superadministración: sigue siendo CLI y endpoints, como
en la fase 0.

## Success Criteria

- [ ] Una persona ajena al proyecto se registra, verifica el correo, crea su
      organización y llega a su panel sin ayuda ni intervención en base de datos
- [ ] La organización creada responde en su subdominio con su propio branding
- [ ] Un correo no verificado no puede crear organización (403)
- [ ] Una cuenta creada y nunca verificada recibe aviso a los 5 días y se borra a los 7,
      liberando el correo
- [ ] El router de autoservicio de organizaciones no importa `get_maintenance_db`
      (comprobación estática, igual que ya existe para `modules/admin`)
- [ ] Dos organizaciones creadas por personas distintas no se ven entre sí: los tests de
      aislamiento siguen en verde y se amplían a las tablas nuevas
- [ ] No se puede reclamar un subdominio ya usado ni uno de la lista de reservados, ni
      en la creación ni en la comprobación previa
- [ ] Registro y reenvío de verificación responden igual exista o no la cuenta
- [ ] Cambiar el correo exige la contraseña actual y un token propio, distinto del de
      verificación de alta
- [ ] Cambiar la contraseña exige la actual y revoca las demás sesiones
- [ ] Recuperar una contraseña olvidada funciona sin exponer si el correo existe
- [ ] El branding editado desde el panel se refleja en la web pública sin recompilar
- [ ] Un rol a medida con campos propios se crea, se asigna y sus campos se piden al dar
      de alta a alguien con ese rol
- [ ] Las reglas anti-escalada siguen cubiertas por tests y se aplican también en la UI
- [ ] Turnstile activo en producción y verificado en el registro, el reenvío de
      verificación, la creación de organización y la recuperación de contraseña; el
      arranque falla si la variable de desactivación está activa en producción
- [ ] Un miembro invitado sin correo verificado queda verificado al completar una
      recuperación de contraseña
- [ ] Cambiar el correo avisa a la dirección antigua antes de aplicarse
- [ ] Las páginas web de registro, verificación, creación de organización y
      recuperación de contraseña existen y completan el flujo sin intervención manual
- [ ] Cero violaciones de axe en las pantallas nuevas; checklist WCAG completado
- [ ] CI en verde; ningún fichero supera las 1000 líneas
- [ ] `docs/` actualizado: arquitectura, modelo de datos y desarrollo reflejan lo nuevo

## Decisiones tomadas — Sesión de validación 2026-09-07

| # | Pregunta | Decisión |
|---|---|---|
| 1 | Proveedor de correo en desarrollo | Mailpit en `infra/docker-compose.yml`, sin salir a Internet |
| 2 | Turnstile en el registro | Sí, obligatorio en producción, desactivable por variable en desarrollo y tests |
| 3 | Elección de subdominio | El usuario lo elige; se sugiere a partir del nombre y se comprueba disponibilidad en vivo |
| 4 | Varias organizaciones por persona | Sí; el panel muestra un selector cuando la persona pertenece a más de una |
| 5 | Política de contraseñas | Mínimo 8 caracteres, con mayúscula, minúscula, número y carácter especial, comprobadas además contra una lista de las más filtradas (k-anonymity, sin enviar la contraseña en claro). Revisada el 2026-09-07 durante la implementación de la fase 1: se añadió la exigencia de composición, alineada con el patrón de validación en vivo adoptado del proyecto de referencia `securitycoet` |
| 6 | Cuenta creada y correo nunca verificado | Correo de aviso a los 5 días; la cuenta se borra a los 7 días por tarea programada, liberando el correo y cualquier subdominio que hubiera reservado |
| 7 | Recuperación de contraseña | Entra en esta fase (fase de trabajo 5): mismo mecanismo de token de un solo uso que la verificación de correo, con las mismas protecciones anti-enumeración |

Sin contradicciones con las decisiones de la fase 0 (verificado: EasyPanel, subdominio
por organización, `TRUSTED_PROXY_CIDRS`, cookie first-party sin `Domain` — ninguna
choca con lo decidido aquí).

## Red Team Review

### Sesión — 2026-09-07
**Revisores:** 2 (seguridad, supuestos no verificados) sobre `plan.md` y las 5 fases.
**Hallazgos:** 17 brutos → 14 consolidados (2 Critical, 5 High, 5 Medium, 2 Low), 0 rechazados.

| # | Hallazgo | Severidad | Aplicado a |
|---|---|---|---|
| 1 | La fase 2 no definía con qué motor de conexión el router de autoservicio crea la organización; reutilizar `create_organization` tal cual exigiría dar `engine_maintenance`/`BYPASSRLS` a un endpoint público, rompiendo la invariante «solo `modules/admin` usa el motor de mantenimiento» | Critical | Fase 2 (función `SECURITY DEFINER` de alcance mínimo, patrón de `app_resolve_organization`) |
| 2 | Contradicción: «correo verificado obligatorio para crear organización» vs «organización no verificada se borra a los 7 días» — ninguna organización llegaría nunca a ese estado | Critical | Resuelto por decisión de producto: se verifica antes de crear (ver decisión #6 arriba); el borrado a 7 días pasa a aplicar a **cuentas de usuario**, no a organizaciones |
| 3 | Turnstile: decisión #2 lo exige en el registro, pero la fase 1 (que implementa el registro) no lo menciona en ningún punto — la fase 2 asume un hecho que la fase 1 no entrega | High | Fase 1 (módulo compartido `core/turnstile.py` + uso en `/auth/register`); fase 2 referencia ese módulo en vez de reimplementarlo |
| 4 | Registro y reenvío de verificación sin requisito de respuesta anti-enumeración: permitirían averiguar qué correos están registrados | High | Fase 1 (respuesta idéntica exista o no la cuenta) |
| 5 | Cambio de correo sin exigir la contraseña actual, y sin token de propósito distinto al de verificación de alta (riesgo de confusión de tokens) | High | Fase 5 |
| 6 | Cambio de contraseña no revoca las demás familias de refresh token; una sesión robada seguiría viva | High | Fase 5 |
| 7 | La variable que desactiva Turnstile en desarrollo no tenía salvaguarda contra quedar activa en producción | High | Fase 1 y 2 (arranque falla si `APP_ENV=production` y la variable de desactivación está activa, igual que ya hace `DOMINIO_BASE`) |
| 8 | `is_active` en `users` ya se usa como interruptor de cuenta operativa (`deps.py`, `auth/service.py`) — confirmado en el código, no una hipótesis. Reutilizarlo para «correo verificado» rompería el login de miembros invitados | High | Fase 1 (columna nueva `email_verified_at`, no se toca `is_active`) |
| 9 | El *scheduling* del aviso a 5 días / borrado a 7 exige un proceso `taskiq scheduler` que hoy no existe en ningún Compose ni en `docs/despliegue.md` (solo hay `api`, `worker`, `web`) | High | Fase 2 (barrido periódico por una tarea con *schedule* fijo, en vez de un disparo por cuenta; nuevo servicio `scheduler` documentado) |
| 10 | `GET /users/me/organizations` (selector multi-organización) no se puede resolver con una consulta RLS normal: el contexto de organización lo fija el host, no el usuario — necesita su propia función `SECURITY DEFINER`, no mencionada en el plan original | High | Fase 5 (función `app_user_organizations`, con `REVOKE`/`GRANT` de alcance mínimo y test de aislamiento) |
| 11 | Ventana residual de squatting: 7 días completos por intento, repetible con cuentas nuevas | Medium | Aceptado como riesgo residual, documentado en la tabla de Riesgos |
| 12 | `check-slug` sin límite de peticiones propio ni requisito de autenticación — candidato a escaneo de slugs | Medium | Fase 2 |
| 13 | Condición de carrera entre `check-slug` y la creación real; el `UNIQUE` de base de datos debe ser la única fuente de verdad | Medium | Fase 2 |
| 14 | Comportamiento no definido si el servicio de contraseñas filtradas no responde | Medium | Fase 1 (fail-open documentado explícitamente, no es un control de sesión crítico) |
| 15 | Sin flujo de recuperación de contraseña en ninguna fase | Low → resuelto | Decisión #7 arriba: se añade a la fase 5 |
| 16 | Lista de subdominios reservados solo se exigía en la creación, no en `check-slug` | Low | Fase 2 |
| 17 | Estimaciones de esfuerzo cortas en fase 2 (scheduler nuevo) y fase 5 (función RLS nueva + cierre de fase) | Low | Actualizadas en la tabla de fases de trabajo (2: 3-3.5d; 5: 2.5-3d) |
| — | Falta decidir si `/registro` y `/verificar-correo` son SSR o CSR | Medium | Resuelto por precedente: CSR, igual que `admin/login` — son flujos transaccionales, no contenido público indexable |

**Informes completos:** hallazgos íntegros conservados en el historial de la sesión que generó este plan (no se archivan como fichero aparte por brevedad; cualquier duda sobre un hallazgo concreto, remitirse a la fase donde se aplicó).

### Whole-Plan Consistency Sweep
- Decisiones delta tras el red-team: (a) «no verificado» se predica de **cuentas de usuario**, no de organizaciones — una organización solo existe si su creador ya verificó; (b) `email_verified_at` en vez de reutilizar `is_active`; (c) Turnstile vive en un módulo compartido usado por las fases 1 y 2, no reimplementado; (d) tres funciones `SECURITY DEFINER` nuevas (creación de organización, listado de organizaciones del usuario) además de las dos ya existentes de resolución de tenant; (e) nuevo servicio `scheduler` en Compose y documentación; (f) recuperación de contraseña añadida a la fase 5; (g) cambio de correo y de contraseña exigen la credencial actual y revocan sesiones/token de propósito propio; (h) registro y verificación son rutas CSR.
- Barrido sobre `plan.md` y las cinco fases: eliminada la ambigüedad «revisar si `is_active` ya se usa con otro sentido» (ya está resuelta: sí se usa, no se reutiliza); eliminada la mención a Turnstile solo en la fase 2 sin base en la fase 1; eliminada la referencia a «tarea programada» sin especificar el proceso que la ejecuta.
- Contradicciones sin resolver: **ninguna**.

## Predict/Debate

### Sesión — 2026-09-07
**Formato:** debate de 5 personas (arquitectura, seguridad, rendimiento, UX,
accesibilidad) sobre el plan ya endurecido por el red-team.
**Hallazgos:** 15 puntos → 1 bloqueante, 9 importantes, 5 opcionales, 0 rechazados.

| # | Quién | Hallazgo | Severidad | Aplicado a |
|---|---|---|---|---|
| 1 | Arquitectura | `app_bootstrap_organization` es multi-escritura dentro de `SECURITY DEFINER` (a diferencia de las funciones de solo lectura de la fase 0); `p_owner_user_id` debe venir siempre del token, nunca de un campo de formulario | Importante | Fase 2 |
| 2 | Arquitectura | Dos caminos de creación de organización (admin/CLI y autoservicio) pueden divergir con el tiempo | Importante | Fase 2 (test de paridad) |
| 3 | Seguridad | `resend-verification` solo tenía límite por IP, sin Turnstile: vector de *email bombing* | Importante | Fase 1 |
| 4 | Seguridad | `forgot-password` con el mismo problema | Importante | Fase 5 |
| 5 | Seguridad | Cambio de correo no avisaba a la dirección antigua | Importante | Fase 5 |
| 6 | Seguridad | Miembros invitados (`password_hash=null`, sin pasar por registro) quedarían con `email_verified_at` nulo para siempre, contradiciendo el Goal 1 | Importante | Fase 5 (`reset-password` verifica como efecto secundario) |
| 7 | Rendimiento | El barrido horario de la fase 2 haría *sequential scan* de `users` sin índice | Importante | Fase 1 (índice parcial en la misma migración) |
| 8 | Rendimiento | Límites de peticiones descritos sin cifra concreta, riesgo de heredar un límite demasiado laxo | Importante | Fases 1, 2, 5 (constantes explícitas en `core/ratelimit.py`) |
| 9 | Rendimiento | `check-slug` sin *debounce* agotaría el límite con el uso normal | Opcional | Fase 2 |
| 10 | UX | Ninguna fase incluía las páginas web de registro, verificación, creación de organización ni recuperación de contraseña — el criterio de éxito del plan era inalcanzable sin ellas | **Bloqueante** | Fases 1, 2 y 5 (páginas añadidas explícitamente) |
| 11 | UX | El panel recién creado queda vacío sin eventos | Opcional | Fase 3 |
| 12 | Accesibilidad | Turnstile es un iframe de terceros que axe no audita | Importante | Fase 1 (prueba manual documentada) |
| 13 | Accesibilidad | Sin requisito de cómo se comunica un enlace caducado | Importante | Fases 1 y 5 (`aria-live`, botón de reenvío) |
| 14 | Accesibilidad | Sin patrón de resumen de errores en formularios con varios fallos simultáneos | Opcional | Fase 4 |
| 15 | Accesibilidad | El selector de organización debía ser navegación real (`<a href>`), no un manejador de clic | Opcional | Fase 5 |

**Decisión resuelta durante esta sesión, no aplazada**: el arquitecto marcó como
importante que el mecanismo de *scheduling* de Taskiq quedara como un «if» a resolver
en implementación. Se hizo un spike inmediato (`taskiq==0.12.6`): `TaskiqScheduler`
exige un proceso separado de `taskiq worker`. La fase 2 ya no dice «confirmar en
código»: dice explícitamente que se añade un cuarto servicio `scheduler`.

### Whole-Plan Consistency Sweep (segunda pasada)
- Delta: (a) tres endpoints públicos más llevan Turnstile (reenvío de verificación,
  recuperación de contraseña) además de registro y creación de organización; (b) índice
  parcial sobre `users.created_at WHERE email_verified_at IS NULL`, en la migración de
  la fase 1, no aplazado; (c) constantes de límite de peticiones nombradas
  explícitamente en `core/ratelimit.py`, ninguna fase se queda con «límite propio» sin
  cifra; (d) páginas web de registro, verificación, creación de organización y
  recuperación de contraseña asignadas a fase concreta; (e) `p_owner_user_id` siempre
  del token; (f) `reset-password` fija `email_verified_at` si estaba nulo; (g) aviso
  informativo al correo antiguo en `change-email`; (h) selector de organización con
  `<a href>` reales.
- Contradicciones sin resolver: **ninguna**.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El subdominio automático convierte el registro en una vía de ocupación de nombres | Verificación de correo obligatoria antes de crear, lista de reservados (también en `check-slug`), límite por IP propio en cada endpoint público y caducidad de las cuentas no verificadas |
| Ventana residual: 7 días completos de squat por intento, repetible con cuentas nuevas | Aceptado como riesgo residual tras el red-team. Si se observa abuso real, endurecer con un cooldown por slug liberado o acortar el plazo — no se sobre-diseña de entrada |
| Adelantar el correo arrastra alcance de la fase 3 | Se implementa solo lo necesario para verificar: proveedor, plantilla y cola. Las plantillas de inscripción siguen en su fase |
| El envío de correo falla y bloquea el registro | La cola reintenta; la interfaz permite reenviar el enlace; el registro no se pierde si el correo tarda |
| La UI abre caminos que saltan las reglas anti-escalada | Las reglas viven en el servicio, no en la interfaz; se añaden tests de API por cada regla que la UI exponga |
| Varias organizaciones por persona complican el contexto de RLS | El contexto sigue viniendo del host, no de la sesión; el selector cambia de subdominio, no de variable; el listado de organizaciones del usuario usa una función `SECURITY DEFINER` de alcance mínimo, no una relajación de RLS |
| Exponer la creación de organización sin las validaciones de superadmin | Función `SECURITY DEFINER` dedicada invocada con el rol de la API, no `engine_maintenance`; comprobación estática de que el router de autoservicio no usa `get_maintenance_db` |
| Reutilizar `is_active` para «correo verificado» rompería el gate de login ya existente | Columna nueva `email_verified_at`; `is_active` no se toca |
