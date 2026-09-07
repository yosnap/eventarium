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

## Decisiones a validar antes de implementar

- ¿El usuario elige su subdominio o se deriva del nombre? Por defecto: lo elige, con
  sugerencia automática y comprobación de disponibilidad en vivo.
- ¿Qué pasa con una organización creada y nunca verificada? Por defecto: se borra a los
  7 días por tarea programada, liberando el subdominio.
- Lista de subdominios reservados (`www`, `api`, `admin`, `mail`, `app`, el propio
  dominio raíz…) a fijar con el usuario antes de escribir la validación.

## Requirements

- Functional: `POST /api/v1/auth/register` (fase 1) devuelve también, tras verificar,
  un flujo para crear la organización: `POST /api/v1/organizations` (nuevo, distinto
  del endpoint de superadmin) que recibe nombre y subdominio deseado, valida
  disponibilidad y formato, crea la organización con `OrganizationService.create`,
  registra al creador como `owner` y añade el dominio `{subdominio}.{dominio_base}`.
  `GET /api/v1/organizations/check-slug?slug=…` para comprobación en vivo desde el
  formulario.
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
- Tarea programada (Taskiq schedule o cron del worker) que borra organizaciones sin
  verificar tras el plazo acordado. Revisar si Taskiq de esta versión soporta tareas
  programadas de forma nativa o si hace falta un bucle simple en el worker.

## Related Code Files

- Create: `apps/api/app/modules/organizations/self_service.py` (o extender
  `service.py` si no crece demasiado — vigilar el límite de 300 líneas)
- Modify: `apps/api/app/modules/organizations/router.py`, `schemas.py`
- Modify: `apps/api/app/core/config.py` (`DOMINIO_BASE`, reservados)
- Create: `apps/api/tests/modules/test_self_service_organizations.py`
- Create: `apps/api/app/core/cleanup.py` o tarea equivalente + su test

## Implementation Steps

1. Cerrar las decisiones abiertas con el usuario (subdominio elegido, plazo de
   caducidad, lista de reservados).
2. `DOMINIO_BASE` en `Settings`, validado en producción (no vacío).
3. Endpoint de comprobación de disponibilidad de slug.
4. Endpoint de creación: valida, crea, asigna `owner`, registra dominio.
5. Límite de peticiones específico para este endpoint.
6. Tarea de limpieza de organizaciones no verificadas.
7. Tests: creación válida deja al creador como `owner` con el rol correcto; slug
   repetido → 409; slug reservado → 422; sin verificar el correo → 403; límite de
   peticiones; la organización sin verificar desaparece tras el plazo y no antes.
8. Actualizar `docs/arquitectura.md` y `docs/despliegue.md` (subdominio automático) si
   algo cambia respecto a lo ya documentado en la fase 0.6.0.

## Success Criteria

- [ ] Un usuario verificado crea su organización y aparece como `owner`
- [ ] El subdominio responde en `GET /api/v1/tenant/branding` inmediatamente después
- [ ] No se puede repetir un slug ni usar uno reservado
- [ ] Un usuario sin verificar no puede crear organización
- [ ] Una organización sin verificar desaparece tras el plazo acordado y no antes
- [ ] Tests de aislamiento existentes siguen en verde

## Risk Assessment

- Exponer `create_organization` sin las validaciones de superadmin es el punto de mayor
  riesgo de esta fase → tests explícitos de cada validación, revisión de PR obligatoria
  centrada en este fichero.
- Colisión entre el router de autoservicio y el de `modules/admin` → mantenerlos en
  módulos separados; el test estático de la fase 0 (`get_maintenance_db` solo en
  `admin`) sigue aplicando y hay que comprobar que el nuevo router no lo usa.
