import { inject } from '@angular/core';
import { Route, Router, Routes } from '@angular/router';

import { guardDe, requierePermiso } from './core/auth/permisos-del-panel';
import { authGuard } from './core/auth/auth.guard';
import { guestGuard } from './core/auth/guest.guard';
import { personalPlataformaGuard } from './core/auth/personal-plataforma.guard';
import { superadminGuard } from './core/auth/superadmin.guard';
import { IDIOMAS, IDIOMA_POR_DEFECTO, Idioma, PREFIJO_DE_IDIOMA } from './core/i18n/idioma';
import { rutaEn, subrutaDeEvento, traducirRuta } from './core/i18n/rutas-traducidas';
import { coincideConEvento, coincideConOrganizacion } from './core/routing/rutas-publicas';
import {
  coincideConEnlaceAntiguo,
  enlaceAntiguoALaPortada,
} from './features/public/events/enlace-antiguo';
import { ThemingService } from './core/theming/theming.service';

/**
 * Páginas de acceso y de enlaces recibidos por correo (registro, recuperación,
 * entrada, cancelación…). Se montan en la raíz y bajo el prefijo de cada idioma.
 */
function rutasDeAcceso(idioma: Idioma): Routes {
  return [
    {
      path: rutaEn(idioma, 'acceder'),
      loadComponent: () => import('./features/admin/login/login-page').then((m) => m.LoginPage),
      canActivate: [guestGuard],
    },
    {
      path: rutaEn(idioma, 'registro'),
      loadComponent: () =>
        import('./features/public/register/register-page').then((m) => m.RegisterPage),
    },
    {
      path: rutaEn(idioma, 'verificar-correo'),
      loadComponent: () =>
        import('./features/public/verify-email/verify-email-page').then((m) => m.VerifyEmailPage),
    },
    {
      path: rutaEn(idioma, 'crear-organizacion'),
      loadComponent: () =>
        import('./features/public/create-organization/create-organization-page').then(
          (m) => m.CreateOrganizationPage,
        ),
    },
    {
      path: rutaEn(idioma, 'recuperar-contrasena'),
      loadComponent: () =>
        import('./features/public/forgot-password/forgot-password-page').then(
          (m) => m.ForgotPasswordPage,
        ),
    },
    {
      path: rutaEn(idioma, 'recuperar-contrasena/nueva'),
      loadComponent: () =>
        import('./features/public/forgot-password/reset-password-page').then(
          (m) => m.ResetPasswordPage,
        ),
    },
    {
      path: rutaEn(idioma, 'invitacion'),
      loadComponent: () =>
        import('./features/public/invitations/accept-invitation-page').then(
          (m) => m.AcceptInvitationPage,
        ),
    },
    {
      path: rutaEn(idioma, 'cuenta/confirmar-correo'),
      loadComponent: () =>
        import('./features/public/confirm-email-change/confirm-email-change-page').then(
          (m) => m.ConfirmEmailChangePage,
        ),
    },
    {
      path: rutaEn(idioma, 'verificar-inscripcion'),
      loadComponent: () =>
        import('./features/public/events/verify-registration-page').then(
          (m) => m.VerifyRegistrationPage,
        ),
    },
    {
      path: rutaEn(idioma, 'confirmar-promocion'),
      loadComponent: () =>
        import('./features/public/events/confirm-waitlist-promotion-page').then(
          (m) => m.ConfirmWaitlistPromotionPage,
        ),
    },
    {
      path: rutaEn(idioma, 'cancelar-inscripcion'),
      loadComponent: () =>
        import('./features/public/events/cancel-registration-page').then(
          (m) => m.CancelRegistrationPage,
        ),
    },
    {
      path: rutaEn(idioma, 'mi-entrada'),
      loadComponent: () =>
        import('./features/public/events/my-ticket-page').then((m) => m.MyTicketPage),
    },
  ];
}

/** Cabecera y pie públicos con todas sus páginas. Se monta en la raíz y bajo cada prefijo. */
function shellPublico(idioma: Idioma): Route {
  return {
    path: '',
    loadComponent: () => import('./layouts/public/public-shell').then((m) => m.PublicShell),
    children: [
      {
        // La raíz es la landing de la instalación (quiénes somos, eventos en
        // directo, funcionalidades, cómo colaborar); el directorio de eventos
        // sigue en /eventos. Revierte la decisión de la fase 6 del plan de
        // organización sin dominio (raíz = directorio) por petición del dueño.
        path: '',
        pathMatch: 'full',
        loadComponent: () =>
          import('./features/public/landing/landing-page').then((m) => m.LandingPage),
      },
      {
        path: rutaEn(idioma, 'eventos'),
        loadComponent: () =>
          import('./features/public/events/events-list-page').then((m) => m.EventsListPage),
      },
      {
        path: rutaEn(idioma, 'pago/retorno'),
        loadComponent: () =>
          import('./features/public/events/payment-return').then((m) => m.PaymentReturnPage),
      },
      {
        path: rutaEn(idioma, 'pago/cancelado'),
        loadComponent: () =>
          import('./features/public/events/payment-cancelled-page').then(
            (m) => m.PaymentCancelledPage,
          ),
      },
      {
        path: rutaEn(idioma, 'ponentes/:publicSlug'),
        loadComponent: () =>
          import('./features/public/events/speaker-page').then((m) => m.SpeakerPage),
      },
      {
        // Vista previa del panel (también de un borrador): solo para quien
        // puede ver los eventos; el backend vuelve a exigirlo.
        path: rutaEn(idioma, 'vista-previa/:eventId'),
        canActivate: [authGuard, requierePermiso({ permiso: 'events:read' })],
        loadComponent: () => import('./features/public/events/event-page').then((m) => m.EventPage),
      },
      {
        path: rutaEn(idioma, 'mis-eventos'),
        loadComponent: () =>
          import('./features/public/mis-eventos/mis-eventos-solicitar-page').then(
            (m) => m.MisEventosSolicitarPage,
          ),
      },
      {
        path: rutaEn(idioma, 'mis-eventos/ver'),
        loadComponent: () =>
          import('./features/public/mis-eventos/mis-eventos-listado-page').then(
            (m) => m.MisEventosListadoPage,
          ),
      },
      {
        path: rutaEn(idioma, 'legal/aviso-legal'),
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'aviso-legal' },
      },
      {
        path: rutaEn(idioma, 'legal/privacidad'),
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'privacidad' },
      },
      {
        path: rutaEn(idioma, 'legal/cookies'),
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'cookies' },
      },
      {
        path: rutaEn(idioma, 'legal/condiciones-de-inscripcion'),
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'condiciones-de-inscripcion' },
      },
      // Enlaces antiguos `/eventos/:slug/**`: antes que `:org/:slug`, que también
      // los reconocería. Ya no se conservan: el guard las manda a la portada. Nunca
      // `redirectTo` con `matcher`: ver `enlace-antiguo.ts`.
      {
        matcher: coincideConEnlaceAntiguo,
        canActivate: [enlaceAntiguoALaPortada],
        loadComponent: () =>
          import('./features/public/pagina-no-encontrada').then((m) => m.PaginaNoEncontrada),
      },
      // `/{org}/{evento}/…`: al final del árbol público, para que ninguna ruta
      // estática (legal, mis-eventos, pago, ponentes…) quede tapada. Los
      // matchers exigen `PATRON_SLUG`: `/foo.php` o `/.env` no coinciden.
      {
        matcher: coincideConEvento(),
        loadComponent: () => import('./features/public/events/event-page').then((m) => m.EventPage),
      },
      {
        matcher: coincideConEvento(subrutaDeEvento(idioma, 'sesiones/:sessionId')),
        loadComponent: () =>
          import('./features/public/events/session-page').then((m) => m.SessionPage),
      },
      {
        matcher: coincideConEvento(subrutaDeEvento(idioma, 'programa')),
        loadComponent: () =>
          import('./features/public/events/event-venues-page').then((m) => m.EventVenuesPage),
      },
      {
        matcher: coincideConEvento(subrutaDeEvento(idioma, 'patrocinadores/:sponsorId')),
        loadComponent: () =>
          import('./features/public/events/sponsor-page').then((m) => m.SponsorPage),
      },
      {
        matcher: coincideConEvento(subrutaDeEvento(idioma, 'politicas')),
        loadComponent: () =>
          import('./features/public/events/public-policies-page').then((m) => m.PublicPoliciesPage),
      },
      {
        matcher: coincideConEvento(subrutaDeEvento(idioma, 'inscribirse')),
        loadComponent: () =>
          import('./features/public/events/registration-page').then((m) => m.RegistrationPage),
      },
      // `/{org}`: página pública de la organización (opt-in). Detrás de todo lo
      // estático y de las rutas de evento; si la organización no activó su
      // página, la propia página responde 404.
      {
        matcher: coincideConOrganizacion,
        loadComponent: () =>
          import('./features/public/organization/organization-public-page').then(
            (m) => m.OrganizationPublicPage,
          ),
      },
      // Cualquier otra cosa: 404 real dentro de la cabecera y el pie públicos.
      {
        path: '**',
        loadComponent: () =>
          import('./features/public/pagina-no-encontrada').then((m) => m.PaginaNoEncontrada),
      },
    ],
  };
}

/**
 * Las mismas páginas públicas bajo el prefijo de cada idioma que no es el de por
 * defecto (`/en/…`). Rutas explícitas generadas desde el catálogo, no un `matcher`:
 * así `app.routes.server.ts` puede declarar su modo de render ruta a ruta.
 */
const RUTAS_CON_PREFIJO_DE_IDIOMA: Routes = IDIOMAS.filter(
  (idioma) => PREFIJO_DE_IDIOMA[idioma] !== '',
).map((idioma) => ({
  path: PREFIJO_DE_IDIOMA[idioma],
  // Un idioma desactivado en `/admin/idiomas` no tiene páginas: su prefijo cae
  // en las rutas de la raíz y acaba en 404 (está reservado como organización).
  canMatch: [() => inject(ThemingService).idiomasActivos().includes(idioma)],
  children: [...rutasDeAcceso(idioma), shellPublico(idioma)],
}));

/**
 * Con el idioma desactivado en `/admin/idiomas`, sus enlaces (correos ya enviados,
 * marcadores, lo que tenga indexado un buscador) llevan a la misma página en el
 * idioma por defecto, con su consulta (`?token=…`) y su ancla, en vez de a un 404.
 */
const IDIOMAS_DESACTIVADOS_A_LA_RAIZ: Routes = IDIOMAS.filter(
  (idioma) => PREFIJO_DE_IDIOMA[idioma] !== '',
).map((idioma) => ({
  path: PREFIJO_DE_IDIOMA[idioma],
  children: [
    {
      path: '**',
      redirectTo: ({ url, queryParams, fragment }) => {
        const ruta = traducirRuta(
          `/${url.map((segmento) => segmento.path).join('/')}`,
          idioma,
          IDIOMA_POR_DEFECTO,
        );
        return inject(Router).createUrlTree(ruta.split('/').filter(Boolean), {
          queryParams,
          fragment: fragment ?? undefined,
        });
      },
    },
  ],
}));

export const routes: Routes = [
  // Primero: el prefijo de idioma no puede caer en el matcher de organización.
  ...RUTAS_CON_PREFIJO_DE_IDIOMA,
  ...IDIOMAS_DESACTIVADOS_A_LA_RAIZ,
  ...rutasDeAcceso(IDIOMA_POR_DEFECTO),
  {
    // Consentimiento OAuth del MCP: un asistente pide conectarse con la cuenta
    // de la persona. Con sesión (`authGuard` conserva la vuelta tras el login).
    path: 'oauth/consentimiento',
    loadComponent: () =>
      import('./features/public/oauth/consentimiento-page').then((m) => m.ConsentimientoPage),
    canActivate: [authGuard],
  },
  {
    path: 'espacio-de-trabajo',
    loadComponent: () =>
      import('./features/admin/workspace-selector/workspace-selector-page').then(
        (m) => m.WorkspaceSelectorPage,
      ),
    canActivate: [authGuard],
  },
  // Redirecciones de las rutas antiguas del panel, que vivía bajo `/admin` para
  // **ambos** ámbitos. Ahora el panel de organización está en `/dashboard` y
  // `/admin` es solo la plataforma.
  //
  // Van **antes** del árbol `admin` y son **explícitas**, no paramétricas: el
  // matcher de Angular no reintenta con la siguiente configuración cuando un
  // padre matchea y ningún hijo lo hace, así que un `admin/:a` genérico o no se
  // alcanzaría nunca, o capturaría las rutas nuevas de plataforma (`/admin/plantillas`
  // acabaría en `/dashboard/plantillas`). Enumerarlas evita las dos cosas.
  //
  // `/admin` a secas **no** se redirige: esa ruta es ahora el escritorio de
  // plataforma, y un marcador antiguo del organizador apuntará ahí (y el guard
  // lo devolverá a `/dashboard`). Es el precio de reutilizar el nombre, y está
  // documentado en el PRD.
  { path: 'admin/login', redirectTo: '/acceder', pathMatch: 'full' },
  { path: 'admin/superadmin', redirectTo: '/admin', pathMatch: 'full' },
  { path: 'admin/superadmin/plantillas', redirectTo: '/admin/plantillas', pathMatch: 'full' },
  { path: 'admin/superadmin/identidad', redirectTo: '/admin/identidad', pathMatch: 'full' },
  { path: 'admin/superadmin/legales', redirectTo: '/admin/legales', pathMatch: 'full' },
  { path: 'admin/superadmin/suplantar', redirectTo: '/admin/suplantar', pathMatch: 'full' },

  { path: 'admin/organization', redirectTo: '/dashboard/organization', pathMatch: 'full' },
  { path: 'admin/branding', redirectTo: '/dashboard/branding', pathMatch: 'full' },
  { path: 'admin/roles', redirectTo: '/dashboard/roles', pathMatch: 'full' },
  { path: 'admin/roles/:id', redirectTo: '/dashboard/roles/:id' },
  { path: 'admin/members', redirectTo: '/dashboard/members', pathMatch: 'full' },
  { path: 'admin/members/nuevo', redirectTo: '/dashboard/members/nuevo', pathMatch: 'full' },
  { path: 'admin/events', redirectTo: '/dashboard/events', pathMatch: 'full' },
  { path: 'admin/events/nuevo', redirectTo: '/dashboard/events/nuevo', pathMatch: 'full' },
  // De la más específica a la más general: `events/:id` captura cualquier cosa
  // que empiece por `events/`, así que las secciones anidadas van **antes** o
  // nunca se alcanzan (y `pathMatch: 'full'` no basta, porque `:id` matchea el
  // segmento y el resto se pierde).
  {
    path: 'admin/events/:id/registrations/:registrationId',
    redirectTo: '/dashboard/events/:id/registrations/:registrationId',
  },
  { path: 'admin/events/:eventId/check-in', redirectTo: '/dashboard/events/:eventId/check-in' },
  { path: 'admin/events/:eventId/payments', redirectTo: '/dashboard/events/:eventId/payments' },
  {
    path: 'admin/events/:eventId/contabilidad',
    redirectTo: '/dashboard/events/:eventId/contabilidad',
  },
  { path: 'admin/events/:eventId/agenda', redirectTo: '/dashboard/events/:eventId/agenda' },
  { path: 'admin/events/:eventId/entradas', redirectTo: '/dashboard/events/:eventId/entradas' },
  { path: 'admin/events/:eventId/descuentos', redirectTo: '/dashboard/events/:eventId/descuentos' },
  {
    path: 'admin/events/:eventId/patrocinadores',
    redirectTo: '/dashboard/events/:eventId/patrocinadores',
  },
  {
    path: 'admin/events/:eventId/ponentes',
    redirectTo: '/dashboard/events/:eventId/ponentes',
  },
  {
    path: 'admin/events/:eventId/inscripciones',
    redirectTo: '/dashboard/events/:eventId/inscripciones',
  },
  { path: 'admin/events/:id', redirectTo: '/dashboard/events/:id' },
  { path: 'admin/sponsor-tiers', redirectTo: '/dashboard/sponsor-tiers', pathMatch: 'full' },
  { path: 'admin/stripe', redirectTo: '/dashboard/stripe', pathMatch: 'full' },
  // La pantalla de páginas legales de organización se retiró (decisión del
  // usuario, 2026-09-14): son siempre las de plataforma. Un marcador antiguo
  // a `/admin/legal` (o a `/dashboard/legal`, mientras existió con ese
  // nombre) ya no tiene destino propio; vuelve al escritorio.
  { path: 'admin/legal', redirectTo: '/dashboard', pathMatch: 'full' },
  { path: 'dashboard/legal', redirectTo: '/dashboard', pathMatch: 'full' },
  { path: 'admin/account', redirectTo: '/dashboard/account', pathMatch: 'full' },
  // Sentido contrario a las de arriba: el catálogo de componentes vivió un tiempo en
  // `/dashboard/estilo` (organización), pero es la herramienta de quien diseña la
  // presentación de la plataforma (landing, plantillas que luego reutilizan las
  // organizaciones, al estilo de Luma) — vuelve a `/admin`, y un enlace guardado a la
  // ubicación antigua sigue llegando, sujeto ya al guard de superadmin.
  { path: 'dashboard/estilo', redirectTo: '/admin/estilo', pathMatch: 'full' },

  {
    path: 'dashboard',
    loadComponent: () => import('./layouts/admin/admin-shell').then((m) => m.AdminShell),
    canActivate: [authGuard],
    children: [
      {
        path: '',
        canActivate: [guardDe('')],
        loadComponent: () =>
          import('./features/admin/dashboard/dashboard-page').then((m) => m.DashboardPage),
      },
      {
        path: 'organization',
        canActivate: [guardDe('organization')],
        loadComponent: () =>
          import('./features/admin/organization/organization-page').then((m) => m.OrganizationPage),
      },
      {
        path: 'branding',
        canActivate: [guardDe('branding')],
        loadComponent: () =>
          import('./features/admin/branding/branding-page').then((m) => m.BrandingPage),
      },
      {
        path: 'politicas',
        canActivate: [guardDe('politicas')],
        loadComponent: () =>
          import('./features/admin/policies/organization-policies-page').then(
            (m) => m.OrganizationPoliciesPage,
          ),
      },
      {
        path: 'roles',
        canActivate: [guardDe('roles')],
        loadComponent: () => import('./features/admin/roles/roles-page').then((m) => m.RolesPage),
      },
      {
        path: 'roles/:id',
        canActivate: [guardDe('roles/:id')],
        loadComponent: () => import('./features/admin/roles/role-form').then((m) => m.RoleForm),
      },
      {
        path: 'members',
        canActivate: [guardDe('members')],
        loadComponent: () =>
          import('./features/admin/members/members-page').then((m) => m.MembersPage),
      },
      {
        path: 'members/nuevo',
        canActivate: [guardDe('members/nuevo')],
        loadComponent: () =>
          import('./features/admin/members/member-form').then((m) => m.MemberForm),
      },
      {
        path: 'events',
        canActivate: [guardDe('events')],
        loadComponent: () =>
          import('./features/admin/events/events-page').then((m) => m.EventsPage),
      },
      {
        path: 'events/nuevo',
        canActivate: [guardDe('events/nuevo')],
        loadComponent: () => import('./features/admin/events/event-form').then((m) => m.EventForm),
      },
      {
        // Envuelve todas las pantallas de un evento con la flecha de vuelta, el
        // título y las pestañas horizontales (`EventShell`). El parámetro se
        // llama `eventId` en todo el árbol — no `id`— porque la mayoría de estas
        // pantallas ya declaraban `readonly eventId = input.required<string>()`
        // desde antes de anidarlas aquí; `withRouterConfig` con
        // `paramsInheritanceStrategy: 'always'` (`app.config.ts`) es lo que hace
        // que ese único parámetro del padre llegue a cada hijo sin que cada ruta
        // tenga que repetirlo.
        path: 'events/:eventId',
        canActivate: [guardDe('events/:eventId')],
        loadComponent: () => import('./layouts/admin/event-shell').then((m) => m.EventShell),
        children: [
          {
            path: '',
            loadComponent: () =>
              import('./features/admin/events/event-dashboard').then((m) => m.EventDashboard),
          },
          {
            // El formulario vive en una ruta hermana, no en la raíz: a quien entra a
            // un evento le interesa cómo va (el escritorio), no los campos.
            path: 'editar',
            canActivate: [guardDe('events/:eventId/editar')],
            loadComponent: () =>
              import('./features/admin/events/event-form').then((m) => m.EventForm),
          },
          {
            path: 'registrations/:registrationId',
            canActivate: [guardDe('events/:eventId/registrations/:registrationId')],
            loadComponent: () =>
              import('./features/admin/events/registration-detail-page').then(
                (m) => m.RegistrationDetailPage,
              ),
          },
          {
            path: 'check-in',
            canActivate: [guardDe('events/:eventId/check-in')],
            loadComponent: () =>
              import('./features/admin/events/event-check-in').then((m) => m.EventCheckIn),
          },
          {
            path: 'payments',
            canActivate: [guardDe('events/:eventId/payments')],
            loadComponent: () =>
              import('./features/admin/events/event-payments').then((m) => m.EventPayments),
          },
          {
            path: 'contabilidad',
            canActivate: [guardDe('events/:eventId/contabilidad')],
            loadComponent: () =>
              import('./features/admin/events/event-accounting').then((m) => m.EventAccounting),
          },
          {
            path: 'agenda',
            canActivate: [guardDe('events/:eventId/agenda')],
            loadComponent: () =>
              import('./features/admin/events/event-agenda').then((m) => m.EventAgenda),
          },
          {
            path: 'diseno',
            canActivate: [guardDe('events/:eventId/diseno')],
            loadComponent: () =>
              import('./features/admin/events/event-design').then((m) => m.EventDesign),
          },
          {
            path: 'entradas',
            canActivate: [guardDe('events/:eventId/entradas')],
            loadComponent: () =>
              import('./features/admin/events/event-ticket-types').then((m) => m.EventTicketTypes),
          },
          {
            path: 'descuentos',
            canActivate: [guardDe('events/:eventId/descuentos')],
            loadComponent: () =>
              import('./features/admin/events/event-discount-codes').then(
                (m) => m.EventDiscountCodes,
              ),
          },
          {
            path: 'patrocinadores',
            canActivate: [guardDe('events/:eventId/patrocinadores')],
            loadComponent: () =>
              import('./features/admin/events/event-sponsors').then((m) => m.EventSponsors),
          },
          {
            path: 'ponentes',
            canActivate: [guardDe('events/:eventId/ponentes')],
            loadComponent: () =>
              import('./features/admin/events/event-speakers').then((m) => m.EventSpeakers),
          },
          {
            path: 'politicas',
            canActivate: [guardDe('events/:eventId/politicas')],
            loadComponent: () =>
              import('./features/admin/policies/event-policies-page').then(
                (m) => m.EventPoliciesPage,
              ),
          },
          {
            path: 'inscripciones',
            canActivate: [guardDe('events/:eventId/inscripciones')],
            loadComponent: () =>
              import('./features/admin/events/event-registrations').then(
                (m) => m.EventRegistrations,
              ),
          },
        ],
      },
      {
        path: 'session-types',
        canActivate: [guardDe('session-types')],
        loadComponent: () =>
          import('./features/admin/session-types/session-types-page').then(
            (m) => m.SessionTypesPage,
          ),
      },
      {
        path: 'sponsor-tiers',
        canActivate: [guardDe('sponsor-tiers')],
        loadComponent: () =>
          import('./features/admin/sponsors/sponsor-tiers-page').then((m) => m.SponsorTiersPage),
      },
      {
        path: 'stripe',
        canActivate: [guardDe('stripe')],
        loadComponent: () =>
          import('./features/admin/organization/stripe-connection').then((m) => m.StripeConnection),
      },
      {
        // Configuración de IA: solo el propietario (`OrgOwnerDep`). Antes se
        // dejaba entrar a cualquiera para que viera el aviso de solo lectura;
        // el dueño decidió (19-oct) cerrar en el panel toda pantalla sin
        // permiso, con la misma tabla que el menú (`REQUISITOS_DEL_PANEL`).
        path: 'ia',
        canActivate: [guardDe('ia')],
        loadComponent: () =>
          import('./features/admin/organization/ai-settings').then((m) => m.OrganizationAiSettings),
      },
      {
        // Ayuda de la traducción automática: la enlazan los avisos de clave propia.
        path: 'ayuda/traduccion',
        canActivate: [guardDe('ayuda/traduccion')],
        loadComponent: () =>
          import('./features/admin/ayuda/traduccion-automatica-page').then(
            (m) => m.TraduccionAutomaticaPage,
          ),
      },
      {
        path: 'account',
        canActivate: [guardDe('account')],
        loadComponent: () =>
          import('./features/admin/account/account-page').then((m) => m.AccountPage),
      },
      {
        // Asistentes por MCP: con `mcp:connect`, el mismo criterio que `ia`.
        path: 'mcp',
        canActivate: [guardDe('mcp')],
        loadComponent: () =>
          import('./features/admin/mcp/mcp-connections-page').then((m) => m.McpConnectionsPage),
      },
    ],
  },

  {
    // Panel de la plataforma: solo quien administra la instalación. Antes vivía
    // bajo `/admin/superadmin`; ahora ocupa la raíz `/admin`, que es lo que su
    // nombre siempre quiso decir.
    path: 'admin',
    loadComponent: () => import('./layouts/admin/admin-shell').then((m) => m.AdminShell),
    canActivate: [personalPlataformaGuard],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/admin/superadmin/superadmin-page').then((m) => m.SuperadminPage),
      },
      {
        path: 'plantillas',
        loadComponent: () =>
          import('./features/admin/superadmin/theme-templates-page').then(
            (m) => m.ThemeTemplatesPage,
          ),
      },
      {
        path: 'identidad',
        loadComponent: () =>
          import('./features/admin/superadmin/platform-identity-page').then(
            (m) => m.PlatformIdentityPage,
          ),
      },
      {
        path: 'idiomas',
        loadComponent: () =>
          import('./features/admin/superadmin/platform-languages-page').then(
            (m) => m.PlatformLanguagesPage,
          ),
      },
      {
        path: 'legales',
        loadComponent: () =>
          import('./features/admin/superadmin/platform-legal-page').then(
            (m) => m.PlatformLegalPage,
          ),
      },
      {
        // Fase 3 del plan de cookies: pantalla de analítica externa, de
        // lectura también para `soporte` (la escritura es solo superadmin).
        path: 'analitica-externa',
        loadComponent: () =>
          import('./features/admin/superadmin/analytics-page').then((m) => m.AnalyticsPage),
      },
      {
        // Catálogo de categorías de eventos: solo superadmin (escribe una tabla
        // de instalación), no el rol `soporte`.
        path: 'categorias',
        canActivate: [superadminGuard],
        loadComponent: () =>
          import('./features/admin/superadmin/event-categories-page').then(
            (m) => m.EventCategoriesPage,
          ),
      },
      {
        // Credencial del proveedor de IA e interruptores de servicio: solo
        // superadmin, no el rol `soporte` que sí entra al resto de `/admin`.
        path: 'ia',
        canActivate: [superadminGuard],
        loadComponent: () =>
          import('./features/admin/superadmin/ai-settings-page').then((m) => m.AiSettingsPage),
      },
      {
        path: 'correo',
        canActivate: [superadminGuard],
        loadComponent: () =>
          import('./features/admin/superadmin/email-settings-page').then(
            (m) => m.EmailSettingsPage,
          ),
      },
      {
        path: 'servicios',
        canActivate: [superadminGuard],
        loadComponent: () =>
          import('./features/admin/superadmin/services-page').then((m) => m.ServicesPage),
      },
      {
        path: 'suplantar',
        loadComponent: () =>
          import('./features/admin/superadmin/impersonation-page').then((m) => m.ImpersonationPage),
      },
      {
        path: 'usuarios',
        loadComponent: () =>
          import('./features/admin/superadmin/users-page').then((m) => m.UsersPage),
      },
      {
        // Catálogo de componentes: la caja de piezas con la que se construyen la
        // landing y la presentación del portal, y de la que salen las plantillas
        // que luego usan las organizaciones (mismo papel que cumple para Luma).
        // Es trabajo de quien administra la instalación, no de un organizador —
        // vivió una temporada en `/dashboard/estilo`, sin el guard, hasta que se
        // corrigió ese alcance.
        path: 'estilo',
        loadComponent: () =>
          import('./features/dev/style-guide/style-guide-page').then((m) => m.StyleGuidePage),
      },
    ],
  },

  // Enlaces antiguos del panel de organización: se van al árbol `dashboard` con
  // el mismo resto de ruta. Están enumerados arriba, uno por uno, en vez de con
  // un `admin/:a` genérico, porque un comodín aquí capturaría las rutas nuevas
  // de plataforma y no habría forma de distinguir «enlace viejo del organizador»
  // de «ruta nueva del admin».

  shellPublico(IDIOMA_POR_DEFECTO),
];
