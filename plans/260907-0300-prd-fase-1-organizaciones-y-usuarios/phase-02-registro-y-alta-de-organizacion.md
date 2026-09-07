---
phase: 2
title: "Fase 2: Registro y alta de organización"
status: pending
priority: P1
effort: "2-2.5d"
dependencies: [1]
---

# Fase 2: Registro y alta de organización

## Overview

De una cuenta verificada a una organización operativa con su propio subdominio, sin que
un superadministrador intervenga. Es el cambio de mayor riesgo de la fase: hoy
`create_organization` es una operación de mantenimiento invocada por el CLI o por
`modules/admin`; aquí se expone, con las salvaguardas que evitan que se convierta en
una vía de ocupación de subdominios.

## Decisiones validadas — Sesión 2026-09-07

- El usuario **elige** su subdominio, con sugerencia automática a partir del nombre y
  comprobación de disponibilidad en vivo (`GET /api/v1/organizations/check-slug`).
- Una organización creada y nunca verificada **se borra a los 7 días** por tarea
  programada, liberando el subdominio. Se envía un **correo de aviso a los 5 días**
  (2 días antes del borrado) para dar ocasión de verificar antes de perderla.
- Turnstile **obligatorio en producción** en este endpoint (formulario público),
  desactivable por variable en desarrollo y tests — igual que en el registro de la
  fase 1.
- Lista de subdominios reservados (`www`, `api`, `admin`, `mail`, `app`, `media`, el
  propio dominio raíz…) a fijar en el código de esta fase; no bloquea el diseño.

## Requirements

- Functional: `POST /api/v1/auth/register` (fase 1) devuelve también, tras verificar,
  un flujo para crear la organización: `POST /api/v1/organizations` (nuevo, distinto
  del endpoint de superadmin) que recibe nombre y subdominio deseado, valida
  disponibilidad y formato, crea la organización con `OrganizationService.create`,
  registra al creador como `owner` y añade el dominio `{subdominio}.{dominio_base}`.
  `GET /api/v1/organizations/check-slug?slug=…` para comprobación en vivo desde el
  formulario. Tarea `send_unverified_org_warning_email` a los 5 días y
  `delete_unverified_organizations` a los 7, reutilizando `EmailProvider` de la
  fase 1.
- Non-functional: `DOMINIO_BASE` en configuración (el dominio de la instalación); el
  slug se valida contra el mismo patrón que ya usa `OrganizationCreate`
  (`^[a-z0-9]+(?:-[a-z0-9]+)*$`) más la lista de reservados; límite de organizaciones
  creadas por IP y por usuario en una ventana de tiempo, igual que el login.

## Architecture

- Reutiliza `app.modules.organizations.service.create_organization` y `add_domain`,
  que ya son correctos y están probados: la novedad es *quién* puede invocarlos y con
  qué validaciones adicionales, no el mecanismo de creación en sí.
- Nuevo router `modules/organizations/router.py` (público, autenticado pero no
  superadmin) para el alta propia, separado de `modules/admin` para no mezclar el
  camino de superadministración con el de autoservicio: son superficies de ataque
  distintas y conviene poder auditarlas por separado.
- Tarea programada (Taskiq schedule o cron del worker) con dos disparos sobre la misma
  organización: aviso a los 5 días, borrado a los 7. Revisar si Taskiq de esta versión
  soporta tareas programadas de forma nativa o si hace falta un bucle simple en el
  worker. El aviso solo se envía si la organización sigue sin verificar en ese
  momento (una verificación entre medias cancela ambos disparos).

## Related Code Files

- Create: `apps/api/app/modules/organizations/self_service.py` (o extender
  `service.py` si no crece demasiado — vigilar el límite de 300 líneas)
- Modify: `apps/api/app/modules/organizations/router.py`, `schemas.py`
- Modify: `apps/api/app/core/config.py` (`DOMINIO_BASE`, reservados)
- Create: `apps/api/tests/modules/test_self_service_organizations.py`
- Create: `apps/api/app/core/cleanup.py` o tarea equivalente (aviso + borrado) + su test

## Implementation Steps

1. Cerrar las decisiones abiertas con el usuario (subdominio elegido, plazo de
   caducidad, lista de reservados).
2. `DOMINIO_BASE` en `Settings`, validado en producción (no vacío).
3. Endpoint de comprobación de disponibilidad de slug.
4. Endpoint de creación: valida, crea, asigna `owner`, registra dominio.
5. Límite de peticiones específico para este endpoint.
6. Tarea de aviso a los 5 días y de borrado a los 7, ambas sobre organizaciones sin
   verificar; la verificación entre medias cancela los dos disparos.
7. Tests: creación válida deja al creador como `owner` con el rol correcto; slug
   repetido → 409; slug reservado → 422; sin verificar el correo → 403; límite de
   peticiones; el aviso se envía a los 5 días y no antes; la organización sin
   verificar desaparece a los 7 días y no antes; verificar tras el aviso cancela el
   borrado.
8. Actualizar `docs/arquitectura.md` y `docs/despliegue.md` (subdominio automático) si
   algo cambia respecto a lo ya documentado en la fase 0.6.0.

## Success Criteria

- [ ] Un usuario verificado crea su organización y aparece como `owner`
- [ ] El subdominio responde en `GET /api/v1/tenant/branding` inmediatamente después
- [ ] No se puede repetir un slug ni usar uno reservado
- [ ] Un usuario sin verificar no puede crear organización
- [ ] Se envía el correo de aviso a los 5 días de crear una organización sin verificar
- [ ] Verificar después del aviso cancela el borrado
- [ ] Una organización sin verificar desaparece a los 7 días y no antes
- [ ] Tests de aislamiento existentes siguen en verde

## Risk Assessment

- Exponer `create_organization` sin las validaciones de superadmin es el punto de mayor
  riesgo de esta fase → tests explícitos de cada validación, revisión de PR obligatoria
  centrada en este fichero.
- Colisión entre el router de autoservicio y el de `modules/admin` → mantenerlos en
  módulos separados; el test estático de la fase 0 (`get_maintenance_db` solo en
  `admin`) sigue aplicando y hay que comprobar que el nuevo router no lo usa.
