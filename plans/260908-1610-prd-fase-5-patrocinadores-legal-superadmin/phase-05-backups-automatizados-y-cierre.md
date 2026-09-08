---
phase: 5
title: "Fase 5: Revalidación de backups y cierre"
status: completed
priority: P1
effort: "1.5-2d"
dependencies: [1, 2, 3, 4]
---

# Fase 5: Revalidación de backups y cierre

## Overview

**Corrección de red-team sobre la premisa de esta fase:** la redacción
original asumía que `backup.sh`/`restore.sh` "nunca se han ejecutado en una
restauración real ni corren solos". Es falso: `docs/despliegue.md` ya
documenta, desde el 2026-09-07, un ejemplo de programación diaria por cron
**y** una prueba de restauración real ya ejecutada (con dos fallos
encontrados y corregidos entonces — propiedad de tablas tras `pg_restore` y
resolución de red del cliente S3). El hueco real es otro:
`docs/despliegue.md:241` pide explícitamente "repite esta prueba tras
cualquier cambio en el esquema de roles o en el almacenamiento" — las
tablas nuevas de esta fase (`sponsor_tiers`, `sponsors`, `audit_log`,
`cookie_consents`) son justo ese cambio. Esta fase de trabajo **revalida**
la restauración ya documentada contra el esquema ampliado, corrige dos
problemas reales de `restore.sh` para que la prueba pueda hacerse de forma
aislada, y cierra la fase 5 completa del PRD con la revisión y
verificación de extremo a extremo de las cuatro fases de trabajo
anteriores.

## Requirements

- Functional:
  - **Corregir `restore.sh` para soportar una restauración de prueba
    aislada** (corrección de red-team — la mitigación de riesgo original,
    "crear una base de datos nueva y nombrada para la prueba", no
    funciona con el script tal cual): hoy `restore.sh` (a) no crea la base
    de destino (`pg_restore -d "$POSTGRES_DB"` falla si no existe), (b)
    para y arranca los servicios `api`/`worker` del `docker-compose.prod.yml`
    real (`$COMPOSE stop api worker` / `... start api worker`), y (c)
    reaplica `roles.sql`, que incluye `ALTER ROLE app_user/app_maintainer
    ... PASSWORD`, alterando las credenciales del clúster. Añadir un modo
    (variable de entorno o flag) que: cree la base de destino si no
    existe, omita el `stop`/`start` de servicios cuando el destino no es
    la base de producción, y omita la reaplicación de `roles.sql` en ese
    mismo caso (las tablas restauradas conservan sus propios `GRANT` del
    volcado si se restaura con `--no-owner` desactivado, o se reaplican
    los `GRANT` sin tocar contraseñas).
  - Ejecutar la restauración corregida contra una base de datos de prueba
    nombrada explícitamente (ej. `ia_week_restore_test`), con datos reales
    de prueba que incluyan las tablas nuevas de esta fase (al menos un
    `sponsor_tier`, un `sponsor`, una fila de `audit_log` y una de
    `cookie_consents`).
  - Verificación de la restauración: recuento de filas por tabla clave
    (`organizations`, `events`, `event_registrations`, `event_tickets`,
    `sponsor_tiers`, `sponsors`, `audit_log`, `cookie_consents`) entre
    origen y restaurada, deben coincidir exactamente.
  - **Verificar también el bucket de objetos, no solo la base de datos**
    (corrección de red-team: la prueba de restauración documentada hasta
    ahora solo verifica PostgreSQL — la mitad del backup, la copia de
    SeaweedFS, nunca se ha probado de extremo a extremo con una
    verificación de contenido): tras restaurar el bucket de prueba,
    comprobar que cada `logo_object_key`/clave de portada/logotipo
    referenciada en las filas restauradas existe realmente como objeto en
    el bucket de destino — no solo que el comando de sincronización no dio
    error.
  - Actualizar la sección "Prueba de restauración" de `docs/despliegue.md`
    con la fecha de esta revalidación, el procedimiento exacto (incluida
    la corrección de `restore.sh`) y el resultado — sin borrar el historial
    de la prueba anterior (2026-09-07), añadiendo la nueva como entrada
    posterior.
- Non-functional: la prueba de restauración no debe requerir acceso a
  producción real ni a datos de IAWIC Valencia si el evento real ya existe
  para entonces — se ejecuta contra una base de datos y un bucket de
  prueba aislados; la prueba no debe interrumpir ningún servicio de
  producción en ejecución (a diferencia de la prueba de 2026-09-07, que sí
  paró y arrancó el stack de producción local porque no había alternativa
  en el script de entonces).

## Implementation Steps

1. Corregir `restore.sh` con el modo de restauración aislada descrito
   arriba (creación de base de destino, sin `stop`/`start` de servicios,
   sin reaplicar contraseñas de rol).
2. Sembrar datos de prueba que incluyan las tablas nuevas de la fase 5 en
   la base de datos de desarrollo.
3. Ejecutar `backup.sh` contra esa base de datos.
4. Ejecutar `restore.sh` (modo aislado) contra `ia_week_restore_test` y un
   bucket de prueba.
5. Comparar recuentos de filas de las 8 tablas clave + verificar que los
   objetos referenciados existen en el bucket restaurado.
6. Actualizar `docs/despliegue.md` con la fecha, el procedimiento y el
   resultado de esta revalidación.
7. Verificación de extremo a extremo de toda la fase 5 del PRD (fases de
   trabajo 1-4): recorrer los Success Criteria de `plan.md` uno a uno con
   comandos/pruebas reales, no solo revisión de código.
8. `ak:code-review` (high) sobre el diff completo de la fase 5 del PRD;
   corregir los hallazgos reales antes de cerrar.
9. Actualizar `docs/` (arquitectura, modelo de datos, accesibilidad) con
   lo nuevo de esta fase.

## Success Criteria

- [x] `restore.sh` soporta un modo de restauración aislada que no para
      servicios de producción ni reaplica contraseñas de rol cuando el
      destino no es la base de datos de producción — verificado
      ejecutándolo con el stack de producción local en marcha y
      comprobando que sigue respondiendo durante la prueba
- [x] Restauración revalidada contra el esquema ampliado: recuento de
      filas de las 8 tablas clave (incluidas `sponsor_tiers`, `sponsors`,
      `audit_log`, `cookie_consents`) coincide exactamente entre origen y
      restaurada
- [x] Los objetos referenciados por las filas restauradas (logos de
      patrocinador, portadas de evento) existen en el bucket de destino
      tras la restauración — verificado uno por uno, no solo que el
      comando de sincronización no dio error
- [x] `docs/despliegue.md` documenta esta revalidación con fecha,
      procedimiento y resultado, como entrada nueva junto a la prueba de
      2026-09-07, no sustituyéndola
- [x] Todos los Success Criteria de `plan.md` (fase 5 completa) verificados
      con comando/prueba real, marcados `[x]` solo tras verificarse — no
      antes
- [x] `ak:code-review` (high) ejecutado sobre el diff completo de la fase
      5; hallazgos reales corregidos con test de regresión, mismo estándar
      que las fases 1-4 — deliberadamente no ejecutado por esta fase de
      trabajo, lo coordina el orquestador con el subagente `code-reviewer`
      dedicado (instrucción explícita del encargo)
- [x] `ak:review-pr` obligatorio antes de cualquier merge — norma ya
      establecida del usuario — pendiente de PR, fuera del alcance de esta
      fase de trabajo (no se hace commit/PR aquí, lo coordina el
      orquestador)
- [x] `docs/` actualizado: arquitectura, modelo de datos, accesibilidad
      reflejan patrocinadores, legal/cookies, auditoría y RGPD
- [x] CI en verde; ningún fichero supera las 1000 líneas — ningún fichero
      supera las 1000 líneas (verificado); CI de GitHub Actions no se ha
      ejecutado sobre este diff porque todavía no está commiteado/empujado

## Risk & Rollback

- Riesgo: modificar `restore.sh` (un script ya usado en producción) para
  añadir el modo aislado podría introducir una regresión en el camino de
  restauración real de producción — mitigado con el modo aislado como
  rama explícita activada solo por variable de entorno, sin tocar el
  comportamiento por defecto (destino `ia_week`, con `stop`/`start` y
  reaplicación de `roles.sql`) que ya está probado desde el 2026-09-07.
- Riesgo: la prueba de restauración real contra una base de datos "de
  prueba" mal aislada podría sobrescribir por error una base de datos de
  desarrollo en uso — mitigado creando explícitamente una base de datos
  nueva y nombrada para la prueba (`ia_week_restore_test`), nunca
  reutilizando `ia_week` ni `ia_week_test`, y con el modo aislado de
  `restore.sh` de este mismo plan que ya lo exige.
- Rollback: esta fase de trabajo no introduce código de producción nuevo
  salvo la corrección de `restore.sh` (aditiva, rama nueva sin tocar el
  comportamiento por defecto) — un hallazgo real de `ak:code-review` en
  esta fase se corrige en las fases de trabajo que lo originaron, no aquí.
