# Investigación previa al PRD — Plataforma open source de eventos (IA Week)

Fecha: 2026-09-06. Síntesis de dos investigaciones (producto y técnica). Los informes completos, con todas las fuentes, están en:

- `plans/reports/researcher-260906-1806-producto-plataformas-eventos.md`
- `plans/reports/researcher-260906-1806-tecnica-stack-eventos.md`

Este documento resume hallazgos, decisiones que se derivan y preguntas abiertas. No es asesoría legal ni fiscal.

---

## 1. Resumen ejecutivo

1. **No existe una base open source que encaje** para forkear: Hi.Events obliga a mostrar su marca en la versión gratuita (incompatible con white-label), Attendize está prácticamente abandonado, Pretix esconde funciones grandes tras un muro Enterprise, Pretalx/Sessionize solo cubren CfP/ponentes, Gancio/Mobilizon no tienen ticketing, Indico es demasiado pesado para organizadores comunitarios. Construir desde cero está justificado, asumiendo el coste de mantenimiento.
2. **Tres huecos de mercado** no cubiertos por ninguna plataforma revisada y que son diferenciadores claros: patrocinadores por niveles, contabilidad integrada del evento (presupuesto + ingresos + gastos + aportaciones en especie) y agenda con descansos/servicios como objetos de primera clase.
3. **Dos requisitos legales** entran directamente en el producto: (a) consentimiento de grabación de imagen como casilla separada que no condicione el registro, y banner de cookies con "rechazar" al mismo nivel que "aceptar" (guía AEPD 2023); (b) **Verifactu** puede obligar a que la venta de entradas de pago genere registros de facturación verificables — plazo de referencia julio 2026, ya vencido o inminente según fuentes; requiere asesor fiscal antes de activar ticketing de pago.
4. **MinIO ya no es una elección segura**: según las fuentes consultadas, su Community Edition entró en modo mantenimiento (dic. 2025), el repositorio se archivó como solo lectura (inicios de 2026) y dejaron de publicar imágenes Docker. Recomendación: SeaweedFS (Apache 2.0) por defecto, detrás de una interfaz `StorageProvider` compatible S3 para que cada instalación elija (SeaweedFS, Garage, MinIO, AWS S3, R2…).
5. El resto del stack confirmado (FastAPI, Angular, PostgreSQL, Stripe, Turnstile) se valida sin cambios, con elecciones concretas de librerías (§4).

---

## 2. Referentes de producto

| Plataforma | Tipo | Ticketing pago | Ponentes/CfP | QR check-in | White-label real | Veredicto |
|---|---|---|---|---|---|---|
| Luma | SaaS cerrado | Sí (plan Plus) | No | Sí, wallet, offline | Parcial | **Referencia UX principal**: registro sin fricción, aprobación/waitlist, 40+ temas, color del evento propagado a emails |
| Eventbrite | SaaS | Sí | No | Sí | No | Ticketing masivo; inútil para conferencias con agenda |
| Sessionize / Pretalx | SaaS / OSS | No | **Muy fuerte** | No | Sí (Pretalx) | Referencia para perfiles de ponente, historial y agenda por tracks |
| Pretix | OSS + Enterprise | Sí | No | Sí (hardware) | Sí self-host | Referencia de ticketing avanzado; muro de pago en seating/POS/badges |
| Hi.Events | AGPL + marca obligatoria | Sí (Stripe) | No | Sí | **No en gratis** | Referencia de flujo de compra; licencia incompatible con nuestro objetivo |
| Indico (CERN) | OSS | Limitado | Abstracts | Limitado | Sí | Robusto a gran escala, adopción compleja |
| Attendize / OSEM | OSS | Sí / ? | No / Sí | Básico / ? | Sí | Mantenimiento bajo o no confirmado |
| Gancio / Mobilizon | AGPL federado | No | No | No | Sí | Solo agenda comunitaria |
| Hopin / RingCentral Events | SaaS corporativo | Sí | No | — | No | Empresa original quebró; referencia solo de features híbridas |

Patrones de UX que conviene copiar de Luma: formulario de registro ligero (email + nombre), verificación por enlace, capacidad que gobierna la waitlist automáticamente, cambio manual de estado con notificación personalizada, QR por invitado exportable a wallet, temas de página con color propagado a emails, "calendario" del organizador que agrupa ediciones.

Funcionalidades pedidas **sin referente documentado** (hay que diseñarlas nosotros): patrocinadores por niveles, contabilidad, agenda con descansos/servicios, hoteles/restaurantes cercanos, páginas de ponencia con vídeo + visualizaciones + reviews.

---

## 3. Multi-tenant y white-label

- Patrón general: capa de branding separada del núcleo (logo, colores, tipografía, dominio, nombre, redes, features visibles por organización).
- Imprescindibles para que otro organizador adopte el software: dominio propio con TLS automático, emails enviados desde el dominio del organizador (DKIM/return-path) o SMTP configurable, aislamiento de datos por organización, **cero atribución obligatoria** (es justo donde falla Hi.Events).
- Dos modelos de despliegue a cubrir con el mismo código:
  - **Un organizador = una instalación** (caso IA Week y de la mayoría de adoptantes).
  - **Una instalación aloja varios organizadores** (SaaS gestionado o sub-marcas).
- Recomendación técnica: tabla compartida + `organization_id` + **Row-Level Security de PostgreSQL** (`SET LOCAL app.tenant_id` por transacción, centralizado en la dependencia de sesión). Schema-por-tenant descartado por complejidad operativa. Riesgo conocido: RLS + pool async exige tests de aislamiento automatizados desde el primer sprint.
- Dominios personalizados: **Caddy con TLS on-demand** validando contra un endpoint del backend ("¿este dominio está registrado?").

---

## 4. Stack técnico validado

| Área | Elección | Descartado / alternativa | Motivo |
|---|---|---|---|
| Backend | FastAPI 0.13x+ (rango pineado, `uv` + lockfile) | — | Ya decidido; releases frecuentes, no seguir "latest" sin CI |
| Estructura | Módulos por dominio: router → service → repository → models | Estructura por tipo de fichero | Escala mejor en monolitos grandes |
| ORM | SQLAlchemy 2 async + asyncpg + Alembic | SQLModel | Madurez, tipado |
| Validación | Pydantic v2, DTOs separados del ORM | — | Estándar |
| Auth | PyJWT ≥ 2.13 (algoritmo fijado explícitamente) + Argon2 | python-jose (sin mantenimiento, CVEs) | Seguridad |
| Tareas async | Taskiq + Redis | arq (más simple), Celery (solo cómputo pesado) | Nativo async, DI tipo FastAPI; vigilar breaking changes |
| Rate limiting | fastapi-limiter (Redis) | SlowAPI | Reutiliza Redis |
| Email | fastapi-mail (SMTP) tras interfaz `EmailProvider`; Resend/Postmark como plug-in | — | Self-host sin proveedor de pago obligatorio |
| QR | segno + firma HMAC/JWT propia (`ticket_id`, `event_id`, `exp`, `nonce`) + `used_at` en BD | Librerías de nicho | ~30 líneas, sin dependencia extra |
| OCR facturas | PaddleOCR self-hosted + fallback LLM vision si baja confianza | Tesseract (peor en tablas), EasyOCR (confunde símbolos monetarios) | Precisión en facturas |
| Pagos | stripe-python, **Stripe Checkout** hosted, webhooks con firma verificada | — | Mínima superficie PCI; pendiente marketplace vs Connect |
| Antibot | Cloudflare Turnstile verificado server-side (`siteverify`, token 5 min, un uso) | — | Trivial con httpx |
| Frontend | Angular 22 (o 21 LTS si hay fricción), standalone + Signals; zone.js por defecto salvo experiencia zoneless | — | Proyecto nuevo, última estable |
| SSR | Activar solo en rutas públicas (evento, listado, organizador); admin CSR | SSR global | Limita riesgo de hydration a donde aporta (OG tags, compartir en redes) |
| Theming | Tailwind v4 (`@theme` sobre CSS custom properties) inyectadas por tenant; **sin Angular Material** (o solo 2-3 componentes) | Material M3 completo | Evita doble sistema de tokens |
| Plantillas de página | "Renderer de bloques": layout guardado como JSON por organización (hero, agenda, ponentes, patrocinadores…) y componentes por tipo de bloque | Motor de templates / CMS | KISS; permite el efecto Luma sin reinventar un CMS |
| i18n | Transloco (runtime) | @angular/localize (build por idioma) | Cambio de idioma sin recargar |
| Tipos API | ng-openapi-gen | orval | Madurez |
| Tests front | Vitest | Karma/Jasmine (deprecado) | Default oficial |
| Escáner QR | PWA + `qr-scanner` (nimiq, Web Worker) | ZXing, jsQR | Mejor detección continua |
| Almacenamiento | **SeaweedFS** (Apache 2.0) tras `StorageProvider` S3 | MinIO (mantenimiento/archivado), Garage (AGPL, activo), RustFS (inmaduro) | Ver §1.4 |
| Imágenes | Pillow en MVP → pyvips si hay cuello de botella medido | — | Simplicidad de despliegue |
| Vídeo | Embeds YouTube/Twitch/Vimeo; contadores vía API de cada plataforma | PeerTube/Owncast como opción avanzada futura | Cero infraestructura de transcodificación |
| Cookies | Klaro (BSD-3) | Orejime (si accesibilidad WCAG es requisito duro), CookieConsent | Completo y permisivo |
| Escaneo automático de cookies | **No hay solución OSS fiable**; mantenimiento manual de la lista en Klaro | Cookiebot/OneTrust (pago) | Punto abierto |
| Páginas legales | Plantillas + revisión humana | Generadores automáticos | No hay generador OSS fiable |
| Despliegue | Docker Compose + Caddy (portable); Coolify/Dokploy como capa opcional | Kubernetes | Autoinstalación simple por terceros |
| Backups | pg_dump + WAL a objetos; réplica de bucket; restauración probada periódicamente | — | Obligatorio |
| Observabilidad | Prometheus + Grafana + Loki (o OpenObserve) | — | Cabe en un VPS de 4 GB |

---

## 5. Contabilidad de eventos (referencia funcional)

- Estructura estándar: ingresos (entradas, patrocinios, expositores, donaciones/subvenciones) frente a gastos fijos (sede, seguros) y variables (catering ~30 %, materiales).
- Aportaciones en especie: registrar a valor de mercado, tanto en ingresos como en gastos, para reflejar el coste real.
- Buena práctica: fondo de contingencia 5-10 %.
- Ninguna plataforma de eventos revisada integra esto; se hace en hojas de cálculo o ERP → oportunidad clara.

---

## 6. Legal (España / UE) con impacto en producto

| Tema | Requisito | Impacto en producto |
|---|---|---|
| Cookies (AEPD 2023, CEPD 03/2022) | "Rechazar" al mismo nivel que "aceptar"; técnicas/personalización sin consentimiento; analítica/marketing con consentimiento | Banner simétrico; categorías separadas; lista de cookies mantenida manualmente |
| RGPD registro | Base legal art. 6; consentimiento no puede condicionar la entrada | Separar datos necesarios (nombre, email) de consentimientos opcionales (marketing) |
| Grabación de imagen/voz | Consentimiento libre, específico, revocable y trazable; menores con autorización de tutores | Casilla propia con finalidad y registro auditable (timestamp); flujo de revocación |
| Verifactu (RD 1007/2023) | Software de facturación con registros encadenados, huella, QR de verificación, envío opcional a AEAT; plazo general julio 2026 (fuentes con matices) | Si la plataforma emite facturas/recibos de entradas, puede ser "sistema informático de facturación" → **validar con asesor fiscal antes de activar pagos** |

---

## 7. Riesgos identificados

1. **Sobre-alcance**: el conjunto pedido equivale a Luma + Pretalx + Pretix + ERP ligero. Obliga a fasear y a un MVP disciplinado.
2. **Verifactu**: puede bloquear el ticketing de pago o exigir un módulo de facturación conforme (o delegar la facturación en Stripe Invoicing/terceros). Decisión temprana.
3. **Fuga entre tenants** por RLS mal aplicado con pool async: tests de aislamiento desde el inicio.
4. **Volatilidad del almacenamiento S3 OSS** (caso MinIO): capa `StorageProvider` obligatoria.
5. **Mantenimiento propio** al no reutilizar un proyecto existente: asumirlo explícitamente.
6. **APIs experimentales de Angular** (Signal Forms, zoneless): no construir checkout ni alta de evento sobre ellas.
7. **Taskiq** joven: fijar versiones y probar en cada actualización mayor.

---

## 8. Preguntas abiertas para el PRD

1. Almacenamiento: ¿SeaweedFS por defecto tras `StorageProvider`, o mantener MinIO asumiendo su estado?
2. Modelo de pagos: ¿la plataforma cobra y liquida (marketplace) o **Stripe Connect** con cuenta propia por organizador? Cambia webhooks, KYC y responsabilidad fiscal.
3. Facturación: ¿la plataforma emite facturas/recibos de entradas (→ Verifactu) o delega (Stripe Invoicing / facturación externa del organizador)?
4. Multi-tenant: ¿una instalación debe poder alojar varios organizadores desde el día uno, o basta "un organizador = una instalación" con el modelo de datos preparado?
5. CfP: ¿se necesita flujo de propuestas y revisión, o carga manual de ponentes por el organizador?
6. Contabilidad: ¿balance completo con gastos, patrocinios e in-kind desde el MVP, o solo reporting de ventas primero?
7. Grabación de charlas: ¿se graba/emite? Si sí, consentimiento de imagen en el MVP.
8. Accesibilidad: ¿WCAG 2.x como requisito explícito? Determina Klaro vs Orejime y esfuerzo de UI.
9. Modelo de proyecto: ¿100 % gratuito o self-host gratis + licencia comercial para funciones avanzadas (modelo Pretix/Hi.Events)? Determina también la licencia del repositorio.
10. Escaneo automático de cookies: ¿aceptar mantenimiento manual o presupuesto para proveedor de pago?

---

## 9. Limitaciones de la investigación

- Cifras de rendimiento y versiones proceden de fuentes de terceros; re-verificar versiones al iniciar el scaffolding.
- Comisiones exactas de Luma/Eventbrite, licencia exacta de Pretalx y actividad de OSEM no verificadas con fuente primaria.
- No se probó end-to-end Caddy on-demand TLS + FastAPI.
- No se investigaron plataformas de gran escala (Bizzabo, Cvent) para páginas de ponencia con vídeo ni "lugares cercanos".
- Verifactu: fechas y sujetos obligados con matices entre fuentes; contrastar con asesor fiscal.
