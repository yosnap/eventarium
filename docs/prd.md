# PRD — Plataforma open source de gestión y registro de eventos

| Campo | Valor |
|---|---|
| Versión | 1.0 |
| Fecha | 2026-09-06 |
| Estado | Aprobado (preguntas abiertas resueltas) |
| Nombre del producto | Provisional; se decidirá más adelante (distinto de IAWIC) |
| Licencia | MIT |
| Base | `docs/investigacion.md` |
| Primer despliegue | IAWIC (IA Week) — Valencia |

---

## 1. Visión

Una plataforma de eventos **open source, autoinstalable y con marca propia** que permita a cualquier organizador publicar eventos, gestionar inscripciones con la fricción mínima de Luma, controlar el acceso con entradas QR, cobrar entradas, mostrar patrocinadores, publicar las ponencias en vídeo y llevar la contabilidad completa del evento, todo en un solo sistema.

Cada instalación —o cada organización dentro de una instalación— tiene su logo, colores, plantilla de página, redes sociales, dominio y datos de la entidad responsable. **Nunca** se impone atribución ni marca del proyecto.

### Problema

Los organizadores combinan hoy Luma/Eventbrite (registro), Sessionize/Pretalx (ponentes), hojas de cálculo (contabilidad, patrocinios) y páginas ad-hoc (patrocinadores, vídeos). Las alternativas open source o están abandonadas, o esconden funciones tras un muro de pago, o obligan a mostrar su marca (ver investigación §1-2).

### Propuesta de valor

1. Registro tipo Luma sin cuenta obligatoria, con verificación de email, aprobación bajo demanda y lista de espera.
2. Entradas QR firmadas e intransferibles con app de escaneo.
3. White-label real sin coste: branding, plantillas y dominio propio por organización.
4. Diferenciadores que ninguna plataforma revisada ofrece: **patrocinadores por niveles**, **contabilidad integrada del evento** (presupuesto, ingresos, gastos, aportaciones en especie, OCR de facturas) y **agenda con descansos y servicios** como datos de primera clase.
5. Ponencias con vídeo en directo y grabado, visualizaciones, reviews e historial de ponente entre ediciones.

---

## 2. Objetivos y métricas

| Objetivo | Métrica de éxito |
|---|---|
| Organizar IAWIC Valencia (≈ 500 asistentes, gratuito) íntegramente con la plataforma | 100 % de inscripciones, check-ins, patrocinadores y contabilidad gestionados en la plataforma |
| Fricción mínima de registro | ≥ 70 % de quienes inician el formulario completan la verificación de email |
| Control de acceso fiable | 0 entradas duplicadas aceptadas; check-in medio < 5 s |
| Reutilización por terceros | Un organizador externo instala y personaliza una instancia siguiendo solo la documentación, sin tocar código |
| Contabilidad útil | Balance final del evento generado desde la plataforma sin hoja de cálculo auxiliar |
| Calidad open source | CI verde, cobertura de tests de aislamiento multi-tenant, docs de instalación y contribución |

---

## 3. Usuarios y roles

### Personas

| Persona | Necesidad principal |
|---|---|
| **Asistente** | Inscribirse en segundos, recibir su entrada, saber la agenda, ver las charlas después |
| **Organizador** | Crear y publicar eventos, aprobar inscritos, gestionar agenda, ponentes, patrocinadores, emails y estadísticas |
| **Administrador de la organización** | Todo lo anterior más branding, dominio, roles, contabilidad y facturas |
| **Ponente** | Mantener su perfil (bio, foto, web, redes), ver su historial de ponencias, acceder a su página de ponencia |
| **Voluntario / staff de puerta** | Escanear entradas y hacer check-in desde el móvil |
| **Patrocinador** | Ver su presencia en la página del evento (sin acceso a la plataforma en el MVP) |
| **Superadministrador de la instalación** | Crear organizaciones, gestionar dominios, configuración global |

### Sistema de roles

Dos tipos de rol, con el mismo mecanismo por debajo (permisos + campos de perfil):

**Roles por defecto** — vienen con la plataforma, no se pueden borrar, y cada uno trae **sus propios campos de perfil predefinidos** para que se distingan claramente entre sí. La organización puede añadir campos a estos roles, pero no quitar los básicos.

| Rol | Permisos base | Campos de perfil predefinidos |
|---|---|---|
| `owner` (responsable/administrador) | Todos en la organización | Nombre, cargo, email de contacto, teléfono, foto |
| `organizer` (organizador) | Eventos, inscripciones, agenda, patrocinadores, emails, estadísticas | Nombre, cargo, área de responsabilidad, foto |
| `speaker` (ponente) | Editar su perfil y su página de ponencia | Nombre, foto, titular profesional, bio, **currículum** (texto o PDF), empresa/organización, web, redes sociales (varias), enlaces de contacto, temas/especialidades; **historial de ponencias** (derivado) |
| `volunteer` (voluntario) | Escaneo/check-in, ver agenda | Nombre, teléfono, disponibilidad, tareas asignadas, talla de camiseta (opcional) |
| `attendee` (asistente) | Ver su entrada y las ponencias | Nombre, email; respuestas del formulario del evento |

**Roles personalizados** — la organización crea los que necesite (cantante, animador, presentador, moderador, fotógrafo, patrocinador con acceso…), eligiendo:
- sus **permisos** de un catálogo fijo definido en código (`events:write`, `registrations:approve`, `accounting:read`, …);
- sus **campos de perfil** (tipo, obligatorio, opciones, orden), que pueden partir de un rol por defecto como plantilla o definirse desde cero.

Reglas comunes:
- Una misma persona puede tener varios roles en la misma organización o evento (responsable que además es ponente; ponente que también presenta).
- **Historial de participación** para cualquier rol: cada persona acumula "participó en el evento X como Y" dentro de la organización (Valencia, Barcelona…). Se deriva de la asignación persona × evento × rol; no se mantiene a mano. En el perfil público del ponente se muestra como historial de ponencias; en el panel del organizador se ve para todos los roles (p. ej. "este presentador ya estuvo en IAWIC Valencia").
- Los datos de perfil de un rol viven en la organización (se reutilizan entre ediciones); los específicos de un evento (charla asignada, sala, tareas de voluntario) viven en la participación en ese evento.

---

## 4. Alcance funcional

Prioridad: **M** = MVP IAWIC Valencia · **S** = siguiente · **P** = posterior.

### 4.1 Organizaciones, branding y plantillas — M

- Organización con nombre, entidad legal, descripción, web, contacto, redes sociales, "quién está detrás".
- Branding: logo, favicon, paleta (primario, secundario, acento, fondo, superficie, texto), tipografías, imagen de cabecera.
- Plantillas de página de evento: el organizador elige una plantilla (`classic`, `minimal`, … ampliables) y el orden/visibilidad de bloques (hero, descripción, agenda, ponentes, patrocinadores, lugar, cercanías, registro). Modelo "renderer de bloques" guardado como JSON, no un CMS.
- Dominio propio con TLS automático — **S** (subdominio/dominio de la instalación en M).
- Superadmin: varias organizaciones por instalación — M en modelo de datos, **S** en interfaz.

### 4.2 Eventos y agenda — M

- Evento: título, slug, resumen, descripción, portada, estado (borrador/publicado/archivado), visibilidad (público/oculto/privado), zona horaria, inicio/fin, lugar (presencial, online, híbrido), aforo, modo de inscripción (gratuito / con aprobación / de pago), verificación de email obligatoria u opcional.
- Multi-día: agenda por día.
- Sesiones tipadas: **charla, descanso, servicio** (catering, guardarropa, networking…), otro; con horario, sala, ponentes asignados.
- Eventos recurrentes (serie con instancias) — **S**.
- Lugares cercanos (hoteles, restaurantes) con nombre, enlace, distancia y nota — **S** (contenido manual; sin integración de mapas en M).
- Página pública del evento con OG tags para compartir.

### 4.3 Inscripción tipo Luma — M

- Formulario ligero: email + nombre + preguntas personalizadas del evento.
- Sin cuenta obligatoria; si el email pertenece a una cuenta existente se enlaza.
- Verificación de email por enlace (configurable por evento).
- Cloudflare Turnstile en todos los formularios públicos; rate limiting.
- Consentimientos separados y auditables: tratamiento necesario, marketing (opcional), **grabación de imagen/voz** (opcional, no condiciona la inscripción).
- Estados: pendiente de verificación → pendiente de aprobación → confirmada / rechazada / cancelada / lista de espera.
- Aprobación bajo demanda: con aforo limitado, el organizador ve el perfil/respuestas y acepta o rechaza; notificación personalizada.
- Lista de espera automática al llenarse el aforo; promoción automática al liberarse plaza, con ventana de confirmación fija de 48h a nivel de aplicación (no por evento) antes de pasar a la siguiente persona.
- Estadísticas: iniciados, verificados, aprobados, rechazados, cancelados, check-ins, emails enviados/entregados/abiertos, conversión.

### 4.4 Entradas QR y control de acceso — M

- Entrada por inscripción confirmada con QR firmado (HMAC/JWT: id de entrada, evento, caducidad, nonce).
- **Intransferible**: ligada al email verificado; el escaneo muestra nombre y estado; un solo uso (`used_at`); re-escaneo marcado como duplicado.
- App de escaneo PWA (cámara del móvil, funciona con conectividad intermitente con cola de sincronización) para el rol voluntario/staff.
- Búsqueda manual por nombre/email como respaldo.
- Añadir a Apple/Google Wallet — **S**.

### 4.5 Pagos — S

- Eventos de pago con tipos de entrada (precio, cantidad, ventana de venta), códigos de descuento — **S**.
- **Stripe Connect**: cada organización conecta su cuenta y cobra directamente; la plataforma no custodia dinero.
- Stripe Checkout hosted; webhooks con firma verificada; reembolsos desde el panel.
- **Facturación delegada**: Stripe emite recibos; la plataforma no genera facturas (no es "sistema informático de facturación" a efectos de Verifactu). Decisión a validar con asesor fiscal antes de activar ventas.
- Ingresos por entradas se vuelcan automáticamente en contabilidad (4.8).

### 4.6 Patrocinadores — M

- Niveles personalizables por organización (Oro, Plata, Bronce, Colaborador…): nombre, orden, tamaño de logo, beneficios.
- Patrocinador: nombre, logo, web, nivel, aportación (económica o en especie con valoración) → enlazada a contabilidad.
- Bloque de patrocinadores en la página del evento agrupado por nivel.
- Organizaciones colaboradoras (asociaciones, fundaciones, hoteles, restaurantes que aportan servicios a cambio de visibilidad) se modelan como patrocinadores con tipo de aportación "en especie".

### 4.7 Ponencias, vídeo y ponentes — M parcial / S

- Página de detalle por ponencia (sesión tipo charla): título, resumen, ponentes, materiales, vídeo.
- Vídeo en directo embebido y grabación posterior — **M** (embed). **YouTube** es la plataforma de IAWIC; se soporta cualquier otra embebible (Twitch, Vimeo…). Contadores de visualización vía API de cada plataforma — **S**.
- Reviews/valoraciones de la ponencia — **S**: solo **asistentes con check-in** realizado en el evento.
- Perfil público de ponente (bio, currículum, web, redes, contacto) con historial de ponencias entre ediciones — **M**. Perfiles de otros roles (presentador, animador…) visibles en la página del evento si la organización lo decide.
- CfP (propuestas y revisión) — **P** (carga manual de ponentes en M).

### 4.8 Contabilidad por evento — S

- Cada evento tiene su libro: presupuesto inicial por partidas, ingresos (patrocinios, colaboradores, entradas, subvenciones), gastos (con categoría, proveedor, fecha, importe, IVA), aportaciones en especie valoradas (constan como ingreso y gasto).
- Subida de facturas y tickets (imagen/PDF) a almacenamiento; **OCR** (PaddleOCR + respaldo LLM vision) que propone proveedor, fecha, base, IVA y total para confirmar.
- Panel: presupuesto vs ejecutado, recaudado por origen, saldo, fondo de contingencia, evolución temporal; balance final exportable (CSV/PDF).
- Acceso restringido a administradores de la organización (`accounting:*`).

### 4.9 Emails — M

- Plantillas por organización con el branding aplicado: verificación, confirmación, aprobación/rechazo, lista de espera, entrada QR, recordatorio, post-evento.
- Proveedor configurable (SMTP propio por defecto; Resend/Postmark opcionales); dominio de envío del organizador.
- Cola de envío con reintentos; métricas de envío/apertura.

### 4.10 Legal y cookies — M

- Banner de cookies (Klaro) con "rechazar" al mismo nivel que "aceptar", categorías separadas; bloqueo de scripts hasta consentimiento.
- Páginas legales (aviso legal, privacidad, cookies, condiciones de inscripción) generadas desde plantillas con los datos de la entidad responsable, editables.
- **Escaneo automático de cookies** — **S**: rastreo periódico de las páginas públicas de la propia instalación (navegador headless) para inventariar cookies y detectar las no declaradas. No existe solución open source fiable; se construye una versión ligera propia.
- Registro auditable de consentimientos (inscripción y cookies).

### 4.11 Plataforma — M / S

- Superadmin, auditoría de acciones sensibles, exportación de datos de un evento (RGPD), borrado de inscritos bajo solicitud — **M**.
- Instalación con Docker Compose + Caddy; backups automatizados de PostgreSQL y almacenamiento con restauración probada — **M**.
- Observabilidad mínima (métricas, logs) — **S**.
- i18n: interfaz en español de España por defecto, inglés en **S**; cambio de idioma en runtime.

---

## 5. Fuera de alcance (esta versión del PRD)

Marketplace público de eventos, app nativa, seating/mapas de asientos, POS físico, impresión de acreditaciones, integración con CRM, chat/networking entre asistentes, streaming self-hosted (PeerTube/Owncast: opción futura), facturación conforme a Verifactu desde la plataforma, federación (ActivityPub).

---

## 6. Requisitos no funcionales

| Área | Requisito |
|---|---|
| Multi-tenant | `organization_id` en toda tabla de dominio + Row-Level Security en PostgreSQL fijada por transacción en un único punto; tests automáticos de aislamiento |
| Seguridad | Argon2; JWT con algoritmo fijado; Turnstile y rate limiting en endpoints públicos; webhooks Stripe verificados; QR firmados de un solo uso; OWASP ASVS nivel 2 como referencia |
| Privacidad | RGPD: minimización de datos, consentimientos separados y trazables, exportación y borrado, retención configurable |
| Rendimiento | Página pública de evento < 2 s LCP en móvil 4G; check-in < 5 s; 1.000 inscripciones/hora sin degradación; check-in de 500 asistentes en < 45 min con 3 escáneres |
| Disponibilidad | Instalación en un VPS de 4 GB; backups diarios; restauración documentada |
| Accesibilidad | **WCAG 2.1 AA en toda la aplicación** (páginas públicas, inscripción, PWA de escaneo y panel de administración); auditoría automática (axe) en CI y revisión manual por fase. Banner de cookies: Orejime (fork accesible de Klaro) o Klaro con auditoría propia |
| Internacionalización | Textos externalizados desde el inicio; zona horaria por evento |
| Portabilidad | Sin dependencia de servicios de pago para funcionar (SMTP genérico, S3 genérico); Stripe solo para eventos de pago |
| Calidad de código | Ficheros ≤ 1000 líneas (objetivo ≤ 300); CI con lint, tipos, tests; conventional commits |
| Licencia y modelo | **MIT**; proyecto 100 % gratuito, sin funciones de pago ni licencia comercial |

---

## 7. Arquitectura y stack (decisiones cerradas)

| Capa | Decisión |
|---|---|
| Backend | FastAPI (Python 3.12), módulos por dominio (router → service → repository → models), SQLAlchemy 2 async + asyncpg + Alembic, Pydantic v2, PyJWT + Argon2, Taskiq + Redis (emails, QR, OCR, recordatorios), fastapi-limiter, fastapi-mail tras `EmailProvider`, segno para QR, stripe-python, httpx para Turnstile |
| Frontend | Angular (última estable), standalone + Signals, SSR solo en rutas públicas, Tailwind v4 con tokens en CSS custom properties inyectadas por organización, sin Angular Material, Transloco, Vitest, ng-openapi-gen, PWA + `qr-scanner` para escaneo |
| Base de datos | PostgreSQL 16, tabla compartida + RLS |
| Almacenamiento | **SeaweedFS** por defecto tras interfaz `StorageProvider` compatible S3 (permite MinIO, Garage, AWS S3, R2). Presigned URLs; Pillow para miniaturas |
| Pagos | Stripe Connect + Checkout; facturación delegada |
| Antibot | Cloudflare Turnstile (verificación server-side) |
| Vídeo | Embeds de plataformas externas |
| Cookies | Orejime (Klaro accesible) — a confirmar frente a Klaro en la fase 5 según auditoría WCAG |
| OCR | PaddleOCR self-hosted + LLM vision de respaldo |
| Despliegue | Docker Compose (api, web, worker, postgres, redis, seaweedfs, caddy); Caddy con TLS on-demand para dominios propios; GitHub Actions; Coolify/Dokploy opcionales |
| Repositorio | Monorepo `apps/api`, `apps/web`, `infra/`, `docs/`, `plans/` |

Justificación completa en `docs/investigacion.md` §3-4.

### Modelo de dominio (alto nivel)

```
Organization ─┬─ OrganizationBranding, OrganizationDomain, EmailTemplate, SponsorTier, Role ─ RolePermission, RoleProfileField
              ├─ OrganizationMember (User × Role, profile_data)
              └─ Event ─┬─ EventSession (talk|break|service) ─ SessionSpeaker, SessionVideo, SessionReview
                        ├─ EventMember (User × Role, p. ej. ponente)
                        ├─ Registration ─ Consent, Ticket (QR, used_at)
                        ├─ TicketType, Order, Payment (Stripe)
                        ├─ Sponsor (tier, contribution)
                        ├─ NearbyPlace
                        └─ Ledger ─ BudgetLine, Income, Expense ─ Receipt (OCR)
User ─ UserSocialLink
```

---

## 8. Flujos principales

1. **Inscripción gratuita**: página del evento → formulario (email, nombre, preguntas, consentimientos, Turnstile) → email de verificación → confirmada (o pendiente de aprobación / lista de espera) → email con entrada QR.
2. **Aprobación**: organizador filtra pendientes, ve perfil y respuestas → aprueba/rechaza con mensaje → email → entrada QR si aprobado.
3. **Check-in**: voluntario abre la PWA → escanea → verde (válida, marca `used_at`) / rojo (usada, cancelada, otro evento) → contador de aforo en tiempo real.
4. **Evento de pago**: elegir tipo de entrada → Stripe Checkout → webhook `checkout.session.completed` → inscripción confirmada + entrada + ingreso en contabilidad.
5. **Configurar marca**: admin sube logo, elige colores y plantilla → vista previa en vivo → publicar; los emails heredan el branding.
6. **Cerrar contabilidad**: registrar patrocinios, subir facturas (OCR), confirmar datos → panel presupuesto vs ejecutado → exportar balance.
7. **Post-evento**: añadir enlace de grabación a cada ponencia → páginas públicas con vídeo, visualizaciones y reviews → historial actualizado en el perfil del ponente.

---

## 9. Fases de entrega (propuesta)

| Fase | Contenido | Prioridad |
|---|---|---|
| 0 | Scaffolding: monorepo, Compose, FastAPI base, RLS, Angular base con theming, CI, docs de desarrollo | M |
| 1 | Organizaciones, branding, plantillas, roles y campos de perfil, usuarios | M |
| 2 | Eventos, agenda con sesiones tipadas, ponentes e historial, página pública con SSR | M |
| 3 | Inscripción tipo Luma: verificación, aprobación, lista de espera, Turnstile, consentimientos, emails, estadísticas | M |
| 4 | Entradas QR, PWA de escaneo, check-in | M |
| 5 | Patrocinadores por niveles; legal y cookies; superadmin; backups | M |
| 6 | Pagos Stripe Connect y tipos de entrada | S |
| 7 | Contabilidad, OCR, informes | S |
| 8 | Vídeo: contadores, reviews; dominio propio; recurrencia; lugares cercanos; escaneo de cookies; inglés | S |
| 9 | CfP, wallet, observabilidad avanzada | P |

Cada fase se convierte en su propio plan de implementación en `plans/` cuando se apruebe este PRD.

---

## 10. Riesgos y preguntas abiertas

### Riesgos

| Riesgo | Mitigación |
|---|---|
| Verifactu aplique aunque se delegue la facturación | Consulta con asesor fiscal antes de la fase 6; mantener la plataforma sin emisión de facturas |
| Fuga de datos entre organizaciones (RLS + pool async) | Fijación de tenant centralizada; tests de aislamiento en CI desde la fase 0 |
| Sobre-alcance | Fases M cerradas antes de S; no añadir nada fuera del PRD sin actualizarlo |
| Volatilidad de dependencias (almacenamiento, Taskiq, APIs experimentales de Angular) | Interfaces de abstracción, versiones fijadas, no usar APIs experimentales en flujos críticos |
| Consentimiento de imagen mal recogido | Casilla propia, texto de finalidad, registro con timestamp, revocación desde enlace |
| Coste de mantenimiento al construir desde cero | Aceptado explícitamente; documentación y tests como prioridad |

### Decisiones tomadas (2026-09-06)

| Pregunta | Decisión |
|---|---|
| Licencia | MIT (se prefiere adopción máxima frente a la protección anti-fork cerrado de AGPL) |
| Modelo del proyecto | 100 % gratuito, sin funciones de pago |
| Accesibilidad | WCAG 2.1 AA en toda la aplicación |
| Volumen IAWIC Valencia | ≈ 500 asistentes, evento gratuito → la fase 6 (pagos) no es urgente; la consulta fiscal se hace antes de activar pagos |
| Emisión en directo | YouTube para IAWIC; soporte genérico de embeds |
| Reviews | Solo asistentes con check-in |
| Nombre del producto | Pendiente; se propondrán nombres más adelante (no bloquea) |

### Preguntas abiertas

Ninguna que bloquee el inicio de la fase 0. Pendiente no bloqueante: nombre del producto y organización de GitHub.
