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

Cada instalación —o cada organización dentro de una instalación— tiene su logo, colores, plantilla de página, redes sociales y datos de la entidad responsable. **Nunca** se impone atribución ni marca del proyecto.

<!-- Corregido 2026-09-14: "y dominio" retirado de la frase anterior. Ver «Decisiones
tomadas (2026-09-14)» — la organización nunca tiene un dominio propio; es un dato
más, no un mecanismo de enrutado. -->

### Problema

Los organizadores combinan hoy Luma/Eventbrite (registro), Sessionize/Pretalx (ponentes), hojas de cálculo (contabilidad, patrocinios) y páginas ad-hoc (patrocinadores, vídeos). Las alternativas open source o están abandonadas, o esconden funciones tras un muro de pago, o obligan a mostrar su marca (ver investigación §1-2).

### Propuesta de valor

1. Registro tipo Luma sin cuenta obligatoria, con verificación de email, aprobación bajo demanda y lista de espera.
2. Entradas QR firmadas e intransferibles con app de escaneo.
3. White-label real sin coste: branding y plantillas por organización, en un único dominio de instalación (sin dominio propio por organización — ver «Decisiones tomadas (2026-09-14)»).
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
| **Administrador de la organización** | Todo lo anterior más branding, roles, contabilidad y facturas |
| **Ponente** | Mantener su perfil (bio, foto, web, redes), ver su historial de ponencias, acceder a su página de ponencia |
| **Voluntario / staff de puerta** | Escanear entradas y hacer check-in desde el móvil |
| **Patrocinador** | Ver su presencia en la página del evento (sin acceso a la plataforma en el MVP) |
| **Superadministrador de la instalación** | Crear organizaciones, configuración global |

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

### Roles de plataforma — S

Distintos de los roles de organización de arriba: gobiernan qué puede hacer alguien sobre la instalación entera (todas las organizaciones), no dentro de una. Hoy solo existe un booleano `is_superadmin` en `User`; pasa a un catálogo pequeño y cerrado, mismo patrón de permisos de un catálogo fijo que los roles de organización:

| Rol de plataforma | Permisos |
|---|---|
| `superadmin` | Todos — organizaciones, plantillas de tema, identidad de la plataforma, usuarios, roles de plataforma |
| `soporte` | Ver usuarios y eventos de cualquier organización, suplantar una cuenta; **sin** borrar usuarios ni cambiar roles de plataforma ni facturación |

Una persona puede no tener ningún rol de plataforma (caso normal: solo es organizador/asistente).

---

## 4. Alcance funcional

Prioridad: **M** = MVP IAWIC Valencia · **S** = siguiente · **P** = posterior.

### 4.1 Organizaciones, branding y plantillas — M

- Organización con nombre, entidad legal, descripción, web, contacto, redes sociales, "quién está detrás".
- Branding: logo, favicon, paleta (primario, secundario, acento, fondo, superficie, texto), tipografías, imagen de cabecera.
- Plantillas de página de evento: el organizador elige una plantilla (`classic`, `minimal`, … ampliables) y el orden/visibilidad de bloques (hero, descripción, agenda, ponentes, patrocinadores, lugar, cercanías, registro). Modelo "renderer de bloques" guardado como JSON, no un CMS.
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
- Subida de facturas y tickets (imagen/PDF) a almacenamiento; **OCR** vía la pasarela de IA multi-proveedor de la organización (LLM vision — OpenRouter/Anthropic/OpenAI/Gemini/personalizado, sin motor autoalojado) que propone proveedor, fecha, base, IVA y total para confirmar. Ver `plans/260911-0325-prd-pasarela-ia-multiproveedor/plan.md`.
- Panel: presupuesto vs ejecutado, recaudado por origen, saldo, fondo de contingencia, evolución temporal; balance final exportable (CSV/PDF).
- Acceso restringido a administradores de la organización (`accounting:*`).

### 4.9 Emails — M

- Plantillas por organización con el branding aplicado: verificación, confirmación, aprobación/rechazo, lista de espera, entrada QR, recordatorio, post-evento.
- Proveedor configurable (SMTP propio por defecto; Resend/Postmark opcionales); dominio de envío del organizador.
- Cola de envío con reintentos; métricas de envío/apertura.

### 4.10 Legal y cookies — M

- Banner de cookies con "rechazar" al mismo nivel que "aceptar", categorías separadas (`necessary`/`analytics`/`marketing`); bloqueo de scripts hasta consentimiento — construido.
- Páginas legales (aviso legal, privacidad, cookies, condiciones de inscripción), editables desde `/admin/legales` — construido.
- Registro de consentimientos de cookies, **anónimo a propósito** (sin `user_id`, email ni IP/hash de IP — un hash sin sal es reversible por fuerza bruta, no cuenta como anonimización) — construido, pero hoy `app_user` solo tiene `INSERT`, nada lo lee todavía.
- **Panel de consentimientos agregados** (`/admin`) — construido (plan 260916-2246): agregado **semanal** por categoría con supresión de celdas por debajo de 5 (hallazgo de red-team: un «1» semanal es cruzable con contexto externo), lectura para `superadmin` y `soporte`, nunca filas individuales.
- **Proveedores externos de analítica** (`/admin`) — construido: pantalla propia `/admin/analitica-externa` («Cookies y analítica externa», con la palabra cookies en el menú — la razón original de que no se encontrara nada); el banner carga los scripts reales de GA4 (`analytics`), Meta Pixel (`marketing`) y Cloudflare (también `analytics` — decisión conservadora: la doc oficial no habla de cookies, y ante ambigüedad el fail-safe es hacia más consentimiento). `DummyAnalyticsService` retirado.
- **Estadísticas de GA4 embebidas en `/admin`** — construido: `GET /admin/analytics-providers/ga4-stats` con estados explícitos (no configurado / credencial inválida / cuota / error de proveedor), nunca un 500; caché del resultado en Redis con TTL de 1 hora; el rango solo admite 7 o 30 días. Requiere una credencial de cuenta de servicio de Google con acceso de solo lectura a la propiedad GA4 — va como variable de entorno gestionada por quien despliega, no como campo editable desde la interfaz (no hay cifrado en reposo en este proyecto para secretos en BD; todo secreto de terceros vive hoy en variables de entorno, mismo patrón que Stripe/SMTP/Turnstile). Meta Pixel y Cloudflare quedan solo en modo "cargar script" en esta fase — sus APIs de estadísticas (Meta Marketing API, Cloudflare Analytics API) exigen cada una su propio flujo de credenciales y quedan fuera de este primer corte.
- **Escaneo automático de cookies** — **P**: rastreo periódico de las páginas públicas de la propia instalación (navegador headless) para inventariar cookies y detectar las no declaradas. No existe solución open source fiable; se construiría una versión ligera propia.

### 4.11 Plataforma — M / S

- Superadmin, auditoría de acciones sensibles, exportación de datos de un evento (RGPD), borrado de inscritos bajo solicitud — **M**.
- **Directorio de usuarios** (`/admin`) — **S**: listado de toda persona con cuenta en la instalación (organizador, asistente con cuenta, o ambos), con filtro por rol de plataforma/organización y buscador. Detalle por usuario: en qué organizaciones participa y con qué rol, en qué eventos se ha inscrito (como asistente vía QR sin cuenta se sigue viendo por `Registration.email`, sin fila de usuario). **Borrado suave**: desactivar/anonimizar (nombre e identificadores personales sustituidos, cuenta inutilizable para iniciar sesión), nunca eliminación física de la fila ni de sus organizaciones/inscripciones — mismo espíritu que el borrado de inscritos bajo solicitud ya M.
- **Preferencia de notificaciones** — **S**: campo en el perfil de usuario ("avisarme de eventos similares") que la persona activa desde su cuenta; se guarda desde ya aunque el motor que efectivamente envíe esas notificaciones (eventos en la misma ciudad, mismo ponente…) sea **P**.
- **Roles de plataforma** — **S**: ver subsección "Roles de plataforma" en §3.
- **Biblioteca de medios** — **S** (antes **P**, se adelanta): sustituye los `<input type="file">` sueltos de portada de evento y logo de patrocinador, y las subidas ya existentes de logo de organización y logo/favicon de identidad de plataforma, por un único componente reutilizable (`MediaPicker`) con cuatro caminos para elegir imagen — arrastrar, seleccionar fichero del dispositivo, pegar una URL externa, o elegir de la biblioteca ya subida. Fuera de alcance a propósito: favicon de organización (el campo existe en la fila de `branding` pero no tiene endpoint de subida ni hueco en el panel) y avatar de usuario — ninguno de los dos pasa por esta biblioteca. Referencia de diseño: `media-picker.tsx`/`media-library.tsx` del proyecto Motoraldia, adaptado al stack propio.
  - **URL externa**: se descarga en el servidor y se aloja en el `StorageProvider` propio (SeaweedFS) — nunca se guarda la URL externa tal cual. Protección SSRF obligatoria (solo HTTPS, hosts públicos; bloquea localhost/IPs privadas/direcciones de metadata de nube).
  - Dos pares de tablas, no una sola: `media`/`media_folders` (de organización, con RLS — `organization_id` siempre relleno) y `platform_media`/`platform_media_folders` (de instalación, sin RLS, solo escribibles desde el panel de superadmin). Sin un GUC de sesión para "esto es de plataforma", mezclar ambos casos en una tabla con `organization_id` nulo habría exigido inventar ese GUC — se separaron en su lugar. Columnas de cada fila: `uploaded_by_user_id`, `object_key`, `filename`, `mime_type`, `size`, `width`, `height`, `alt` (un solo idioma — la plataforma es monolingüe en español, sin el alt multi-idioma de la referencia), `folder_id` (nulo si no está en ninguna carpeta), `deleted_at`.
  - **Visibilidad**: cada persona ve las imágenes que subió ella misma; quien tenga el permiso de escritura del campo que está editando (`branding:write`, `events:write`, `sponsors:write`…) ve además las de cualquier miembro de su propia organización — no hace falta un permiso `media:*` nuevo, se reutiliza el permiso de cada campo. La biblioteca de plataforma es un espacio aparte, solo para superadmin — no hay una vista que junte medios de distintas organizaciones ni de todas a la vez.
  - Procesamiento en servidor: conversión a WebP y redimensionado a un máximo por perfil (logo/favicon/patrocinador vs. portada de evento); GIF se sube sin tocar, para no perder la animación.
  - Carpetas para organizar la biblioteca; editor de recorte sobre una imagen ya subida (crea una imagen nueva, nunca sustituye la original); borrado = papelera con restaurar y comprobación de referencias antes de aceptar el borrado, nunca fila física hasta purgarla a mano.
  - Sin sincronización con CDN externo (no aplica: el storage ya es propio).
- **Analítica de plataforma** — **P**: panel con cifras agregadas de toda la instalación (eventos totales/activos, inscripciones por periodo, organizaciones activas) y su evolución en el tiempo, no solo el embudo por evento que ya tiene el organizador (§4.3).
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
| OCR | LLM vision vía pasarela de IA multi-proveedor propia (LiteLLM SDK embebido; sin motor autoalojado) |
| Despliegue | Docker Compose (api, web, worker, postgres, redis, seaweedfs, caddy); un único dominio por instalación; GitHub Actions; Coolify/Dokploy opcionales |
| Repositorio | Monorepo `apps/api`, `apps/web`, `infra/`, `docs/`, `plans/` |

Justificación completa en `docs/investigacion.md` §3-4.

### Modelo de dominio (alto nivel)

```
Organization ─┬─ OrganizationBranding, EmailTemplate, SponsorTier, Role ─ RolePermission, RoleProfileField
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
| 8 | Vídeo: contadores, reviews; ~~dominio propio~~ (retirado, ver decisión 2026-09-14); recurrencia; lugares cercanos; escaneo de cookies; inglés | S |
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

### Decisiones tomadas (2026-09-14)

| Pregunta | Decisión |
|---|---|
| ¿Dominio propio por organización? | **No, retirado.** Una sola instalación vive en **un único dominio**, para el panel y para la web pública. El dominio dejó de ser el mecanismo con el que la API decide de qué organización es una petición — ese mecanismo desaparece; la organización pasa a ser un dato más de cada evento y de cada membresía, nunca una señal de enrutado. Superponía además dos cosas distintas que convenía separar: el aislamiento de datos entre organizaciones (necesario desde el primer día, vía RLS) y el dominio propio como función de marca blanca (fase 8, pospuesta, y ahora retirada del todo en vez de solo pospuesta). |
| ¿Cómo sabe la API para qué organización trabaja un administrador? | Por una **organización activa** de su sesión, elegible en cualquier momento desde el selector del panel (ya existía la lista de organizaciones de la persona; lo que faltaba era que cambiar de una a otra no dependiera de navegar a otro dominio). |
| ¿Cómo sabe la API de qué organización es un evento público? | Se deriva de la propia fila del evento (`event.organization_id`), nunca de la URL ni del host — mismo patrón que ya usaba `checkout_service.py` para fijar el contexto RLS de un pago. |
| ¿Y el slug de un evento? | Pasa a ser **único en toda la instalación**, no solo dentro de su organización (antes `UNIQUE(organization_id, slug)`, ahora `UNIQUE(slug)`) — sin dominio por organización que ya lo desambigüe, dos organizaciones no pueden competir por el mismo slug. Mismo cambio para el perfil público de ponente (`speaker_public_profiles.public_slug`). |

**Aplicada** (plan `plans/260914-0741-organizacion-sin-dominio/`, cerrado): resolución
por sesión/recurso implementada, `organization_domains`/`platform_domains` retiradas del
esquema, y con ellas la plantilla de portada por organización — la home pública es el
directorio de eventos de toda la instalación.

### Decisiones tomadas (2026-09-16)

| Pregunta | Decisión |
|---|---|
| ¿Qué usuarios muestra el directorio de `/admin`? | Todos los que tienen cuenta en la instalación (organizador, asistente con cuenta, o ambos), con filtros por rol/organización — no solo quien tiene un rol de plataforma |
| ¿Qué pasa al "eliminar" un usuario desde `/admin`? | **Borrado suave**: desactivar/anonimizar, nunca borrado físico. Sus organizaciones e inscripciones permanecen intactas |
| ¿Qué son los "permisos" que faltan, si el RBAC por organización ya existe? | **Roles de plataforma** — hoy solo hay un booleano `is_superadmin`; pasa a un catálogo pequeño (`superadmin`, `soporte`…), ver §3 |
| ¿Se prepara ya el campo de preferencia de notificaciones (eventos similares/misma ciudad/mismo ponente)? | Sí, solo el campo en el perfil de usuario ahora; el motor de envío que lo consuma queda en **P** |
| El panel de consentimientos de cookies: ¿identifica a quién ha consentido? | No — se mantiene anónimo (decisión ya cerrada); el panel nuevo es solo agregado (conteos por categoría/periodo), nunca por visita identificable |
| ¿Dónde vive la credencial de la API de Google Analytics? | Variable de entorno, gestionada por quien despliega — no editable desde `/admin`; el proyecto no tiene cifrado en reposo para secretos en BD, y no se construye esa infraestructura solo para esto (mismo patrón que Stripe/SMTP/Turnstile) |
| ¿Se conecta también la API de estadísticas de Meta Pixel y Cloudflare en este primer corte? | No — cada una exige su propio flujo de credenciales (Meta Marketing API, Cloudflare Analytics API); en esta fase solo cargan su script tras consentimiento, sin panel de estadísticas propio |
| ¿Cloudflare Web Analytics necesita consentimiento si su doc dice que no recoge datos personales? | Se le exige la categoría `analytics` igual que GA4 — la documentación oficial (developers.cloudflare.com/web-analytics/about) no menciona cookies ni identificadores de forma explícita; en ePrivacy la ausencia de datos personales no exime del consentimiento, así que el fail-safe es hacia más consentimiento (decisión de implementación, 17-sep) |
| ¿Puede `soporte` entrar en el panel de plataforma? | Sí, en modo lectura: el guard de `/admin` acepta superadmin o `soporte` (`platform_role` viaja en `/users/me` y en el login) y la escritura sigue bloqueada en el backend — primera pantalla abierta a soporte: la de analítica externa |

### Preguntas abiertas

Ninguna que bloquee el inicio de la fase 0. Pendiente no bloqueante: nombre del producto y organización de GitHub.
