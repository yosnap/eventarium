# Fase 5 del PRD — fase de trabajo 5: revalidación de backups y cierre

Fecha: 2026-09-08

## Resumen

Se corrigió `infra/scripts/restore.sh` para soportar un modo de restauración
aislada (`RESTAURACION_AISLADA=1`), se sembraron datos reales en la base de
desarrollo con las cuatro tablas nuevas de la fase 5 del PRD, se ejecutó
`backup.sh`/`restore.sh` de punta a punta contra una base de datos
(`ia_week_restore_test`) y un bucket (`media-restore-test`) de prueba, y se
verificó recuento de filas + existencia de objetos uno por uno. Se recorrieron
todos los Success Criteria de `plan.md` con evidencia real (test ya existente
re-ejecutado, o comprobación puntual). Se actualizó `docs/despliegue.md`,
`docs/arquitectura.md` y `docs/modelo-de-datos.md`.

## Archivos modificados

- `infra/scripts/restore.sh` — modo `RESTAURACION_AISLADA=1` (crea la BD de
  destino si no existe, omite parar/arrancar `api`/`worker`, omite reaplicar
  `roles.sql`), guardas de seguridad, y corrección de un bug latente de Bash
  (`set -u` + carácter multibyte pegado a una variable) en el camino por
  defecto — ver "Desviaciones" abajo.
- `docs/despliegue.md` — nueva entrada "Revalidación — 2026-09-07 + esquema
  fase 5 del PRD (2026-09-08)" bajo "Prueba de restauración", sin borrar la
  entrada de 2026-09-07.
- `docs/arquitectura.md` — nueva sección "Auditoría y RGPD (superadmin)" +
  nota sobre `AUDIT_READ` fuera del enum en "Permisos y anti-escalada" (hueco
  real: fases 2-4 nunca lo documentaron ahí).
- `docs/modelo-de-datos.md` — tabla de RLS ampliada con las tablas de fases
  3-4 que faltaban y con la excepción `audit_log`/`cookie_consents`; tabla de
  migraciones ampliada con `0009`-`0012` (solo llegaba a `0008`).
- `plans/260908-1610-prd-fase-5-patrocinadores-legal-superadmin/plan.md` —
  `status: completed`, Success Criteria marcados `[x]`/`[ ]` según
  verificación real.
- `plans/260908-1610-prd-fase-5-patrocinadores-legal-superadmin/phase-05-backups-automatizados-y-cierre.md`
  — `status: completed`.

No se tocó ningún fichero de `apps/api`/`apps/web` de producción: el script de
siembra de datos de prueba vivió fuera del repo (scratchpad de la sesión), tal
como permite el plan ("un script puntual").

## Revalidación de backups: resultado exacto

Procedimiento ejecutado contra el entorno de desarrollo
(`infra/docker-compose.yml`, proyecto `ia-week`), sin tocar
`docker-compose.prod.yml` ni parar ningún servicio de la API/worker en ningún
momento.

1. Siembra: organización `iawic` existente + evento nuevo con portada, un
   `sponsor_tier`, un `sponsor` con logo, una `event_registration` `confirmed`
   con su `event_ticket`, un `cookie_consents`, un `audit_log`.
2. `infra/scripts/backup.sh` con `COMPOSE` apuntando al compose de desarrollo
   y `COMPOSE_NETWORK=ia-week_default`: volcado + sincronización completa del
   bucket `media` a un directorio local.
3. `RESTAURACION_AISLADA=1 POSTGRES_DB=ia_week_restore_test
   S3_BUCKET=media-restore-test infra/scripts/restore.sh <volcado> <objetos>
   --si-estoy-seguro`.
4. Recuento de filas, origen (`ia_week`) vs. restaurada
   (`ia_week_restore_test`):

   | Tabla | Origen | Restaurada |
   |---|---|---|
   | organizations | 5 | 5 |
   | events | 4 | 4 |
   | event_registrations | 1 | 1 |
   | event_tickets | 1 | 1 |
   | sponsor_tiers | 1 | 1 |
   | sponsors | 1 | 1 |
   | audit_log | 1 | 1 |
   | cookie_consents | 2 | 2 |

   Coinciden exactamente en las 8 tablas.
5. Objetos verificados uno por uno con `s3api head-object` contra
   `media-restore-test` (no solo ausencia de error de `s3 sync`):
   - `orgs/.../events/.../cover/f64292b974234a0283905b059f35c7a2.png` → OK
   - `orgs/.../event-covers/031129c764c844c9b7471eb7c846c0bd.png` → OK
   - `orgs/.../sponsors/2d593e6e46af4ffca5a464a2cafda647.png` → OK
6. `curl http://localhost:8080/api/v1/health` devolvió `200` de forma
   continua durante toda la prueba: `api`/`worker`/`web` nunca se pararon.

Limpieza tras la verificación: `DROP DATABASE ia_week_restore_test`,
`s3 rb s3://media-restore-test --force`, y las filas/objetos sembrados para
la prueba se retiraron de `ia_week`/`media` para no dejar datos ficticios en
el entorno de desarrollo compartido.

## Hallazgos y desviaciones del plan

1. **Bug de entorno, no de código: `-volume.max=10` de SeaweedFS agotado.**
   La primera ejecución de la sincronización de objetos en modo aislado falló
   con `InternalError` en el 100% de los objetos porque el SeaweedFS de
   desarrollo (`infra/docker-compose.yml`) tiene `-volume.max=10` y ya estaba
   en `Free: 0` tras meses de uso real del bucket `media` — un bucket/colección
   nueva no tenía dónde alojar su primer volumen. Se subió temporalmente a
   `-volume.max=30`, se recreó solo el contenedor `seaweedfs` (sin afectar
   `postgres`/`api`/`worker`/`web`), se repitió la prueba con éxito, y se
   revirtió el valor a 10 al terminar (`git diff infra/docker-compose.yml`
   limpio, confirmado). No es una regresión de esta fase: en producción el
   cupo de volúmenes se dimensiona según el uso real.
2. **Bug pre-existente corregido en `restore.sh` (fuera del modo aislado).**
   La línea de confirmación interactiva
   (`echo "Se va a SOBRESCRIBIR la base de datos «$POSTGRES_DB» ..."`, ya
   presente en `HEAD` antes de esta fase) rompe con `unbound variable` bajo
   `set -u` porque el carácter multibyte `»` pegado directamente a
   `$POSTGRES_DB` confunde al parser de nombres de variable de Bash
   (reproducible con `bash -c 'set -u; V=x; echo "«$V»"'`). Es un defecto real
   que habría hecho fallar **cualquier** invocación real de `restore.sh` sin
   `--si-estoy-seguro`, en el camino de producción tal cual estaba. Se corrigió
   con `${POSTGRES_DB}` (mismo mensaje, sin cambio de comportamiento) — el
   plan autoriza corregir problemas reales de `restore.sh` en esta fase de
   trabajo. Desviación menor del alcance ("no toques comportamiento de
   producción... fuera del modo aislado"): el cambio es una corrección de bug
   de sintaxis, no un cambio de comportamiento, y sin él el camino por
   defecto está roto igualmente.
3. **`ia_week_restore_test` no se dejó persistente.** El plan pide nombrarla
   así explícitamente pero no exige conservarla; se eliminó tras verificar,
   junto con el bucket de prueba, para no dejar residuos en el Postgres/
   SeaweedFS de desarrollo del usuario.

## Success Criteria de `plan.md` sin marcar (y por qué)

- **CI en verde** — no marcado. Ningún fichero supera las 1000 líneas
  (verificado con `find` + `wc -l` sobre todo el repo, cero resultados). El
  workflow de GitHub Actions no se ha ejecutado sobre este diff porque
  todavía no está commiteado/empujado — corresponde al orquestador tras el
  commit.
- **`ak:code-review` (high) sobre el diff completo** — no marcado
  deliberadamente, por instrucción explícita del encargo: lo ejecuta el
  orquestador con el subagente `code-reviewer` dedicado sobre el diff
  completo de las 5 fases.
- **`ak:review-pr` obligatorio antes de merge** — no marcado: no se ha hecho
  commit ni PR en esta fase de trabajo, por instrucción explícita del
  encargo.

Todos los demás Success Criteria de `plan.md` (fase 5 completa) se marcaron
`[x]` tras verificación real: se re-ejecutó la suite completa de `apps/api`
(364 tests, verde), se re-ejecutaron 5 ficheros de test de frontend afectados
(`cookie-banner.spec.ts`, `legal-page.spec.ts`, `legal-pages-page.spec.ts`,
`sponsor-tiers-page.spec.ts`, `event-sponsors*.spec.ts` — 18 tests, verde), se
comprobó con `grep` que `AUDIT_READ` no es miembro del enum `Permission`, y se
verificó de extremo a extremo la revalidación de backups descrita arriba.

## Tests

- API: `apps/api/.venv/bin/python -m pytest -q` → 364 tests, verde (sin
  regresión tras los cambios de esta fase; no se tocó código de `apps/api`).
- Web: 2 tandas de `ng test --include=...` → 18 tests, verde (banner de
  cookies, páginas legales/editor, patrocinadores).
- `alembic upgrade head` → `downgrade -1` → `upgrade head`: cubierto por
  `test_ciclo_de_migracion_limpio`, verde.

## Estado del entorno de desarrollo al terminar

`infra/scripts/dev.sh status` antes y después: mismo estado (API/web/Caddy
arriba). `docker-compose.yml` sin diferencias (`git diff` limpio) — el
`-volume.max` de SeaweedFS se subió y se revirtió durante la prueba, el
contenedor quedó sano (`healthy`) con la configuración original.

## Preguntas sin resolver

Ninguna. Si el orquestador prefiere conservar `ia_week_restore_test`/
`media-restore-test` como artefactos de evidencia en vez de limpiarlos,
puede repetirse la prueba en 2 minutos con el procedimiento documentado en
`docs/despliegue.md`.
