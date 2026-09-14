import { Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';
import { guestGuard } from './core/auth/guest.guard';
import { superadminGuard } from './core/auth/superadmin.guard';

export const routes: Routes = [
  {
    path: 'acceder',
    loadComponent: () => import('./features/admin/login/login-page').then((m) => m.LoginPage),
    canActivate: [guestGuard],
  },
  {
    path: 'registro',
    loadComponent: () =>
      import('./features/public/register/register-page').then((m) => m.RegisterPage),
  },
  {
    path: 'verificar-correo',
    loadComponent: () =>
      import('./features/public/verify-email/verify-email-page').then((m) => m.VerifyEmailPage),
  },
  {
    path: 'crear-organizacion',
    loadComponent: () =>
      import('./features/public/create-organization/create-organization-page').then(
        (m) => m.CreateOrganizationPage,
      ),
  },
  {
    path: 'recuperar-contrasena',
    loadComponent: () =>
      import('./features/public/forgot-password/forgot-password-page').then(
        (m) => m.ForgotPasswordPage,
      ),
  },
  {
    path: 'recuperar-contrasena/nueva',
    loadComponent: () =>
      import('./features/public/forgot-password/reset-password-page').then(
        (m) => m.ResetPasswordPage,
      ),
  },
  {
    path: 'invitacion',
    loadComponent: () =>
      import('./features/public/invitations/accept-invitation-page').then(
        (m) => m.AcceptInvitationPage,
      ),
  },
  {
    path: 'cuenta/confirmar-correo',
    loadComponent: () =>
      import('./features/public/confirm-email-change/confirm-email-change-page').then(
        (m) => m.ConfirmEmailChangePage,
      ),
  },
  {
    path: 'verificar-inscripcion',
    loadComponent: () =>
      import('./features/public/events/verify-registration-page').then(
        (m) => m.VerifyRegistrationPage,
      ),
  },
  {
    path: 'confirmar-promocion',
    loadComponent: () =>
      import('./features/public/events/confirm-waitlist-promotion-page').then(
        (m) => m.ConfirmWaitlistPromotionPage,
      ),
  },
  {
    path: 'cancelar-inscripcion',
    loadComponent: () =>
      import('./features/public/events/cancel-registration-page').then(
        (m) => m.CancelRegistrationPage,
      ),
  },
  {
    path: 'mi-entrada',
    loadComponent: () =>
      import('./features/public/events/my-ticket-page').then((m) => m.MyTicketPage),
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
    path: 'admin/events/:eventId/inscripciones',
    redirectTo: '/dashboard/events/:eventId/inscripciones',
  },
  { path: 'admin/events/:id', redirectTo: '/dashboard/events/:id' },
  { path: 'admin/sponsor-tiers', redirectTo: '/dashboard/sponsor-tiers', pathMatch: 'full' },
  { path: 'admin/stripe', redirectTo: '/dashboard/stripe', pathMatch: 'full' },
  { path: 'admin/legal', redirectTo: '/dashboard/legal', pathMatch: 'full' },
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
        loadComponent: () =>
          import('./features/admin/dashboard/dashboard-page').then((m) => m.DashboardPage),
      },
      {
        path: 'organization',
        loadComponent: () =>
          import('./features/admin/organization/organization-page').then((m) => m.OrganizationPage),
      },
      {
        path: 'branding',
        loadComponent: () =>
          import('./features/admin/branding/branding-page').then((m) => m.BrandingPage),
      },
      {
        path: 'roles',
        loadComponent: () => import('./features/admin/roles/roles-page').then((m) => m.RolesPage),
      },
      {
        path: 'roles/:id',
        loadComponent: () => import('./features/admin/roles/role-form').then((m) => m.RoleForm),
      },
      {
        path: 'members',
        loadComponent: () =>
          import('./features/admin/members/members-page').then((m) => m.MembersPage),
      },
      {
        path: 'members/nuevo',
        loadComponent: () =>
          import('./features/admin/members/member-form').then((m) => m.MemberForm),
      },
      {
        path: 'events',
        loadComponent: () =>
          import('./features/admin/events/events-page').then((m) => m.EventsPage),
      },
      {
        path: 'events/nuevo',
        loadComponent: () => import('./features/admin/events/event-form').then((m) => m.EventForm),
      },
      {
        path: 'events/:id',
        loadComponent: () =>
          import('./features/admin/events/event-dashboard').then((m) => m.EventDashboard),
      },
      {
        // El formulario vive en una ruta hermana, no en la raíz: a quien entra a
        // un evento le interesa cómo va (el escritorio), no los campos.
        path: 'events/:id/editar',
        loadComponent: () => import('./features/admin/events/event-form').then((m) => m.EventForm),
      },
      {
        path: 'events/:id/registrations/:registrationId',
        loadComponent: () =>
          import('./features/admin/events/registration-detail-page').then(
            (m) => m.RegistrationDetailPage,
          ),
      },
      {
        path: 'events/:eventId/check-in',
        loadComponent: () =>
          import('./features/admin/events/event-check-in').then((m) => m.EventCheckIn),
      },
      {
        path: 'events/:eventId/payments',
        loadComponent: () =>
          import('./features/admin/events/event-payments').then((m) => m.EventPayments),
      },
      {
        path: 'events/:eventId/contabilidad',
        loadComponent: () =>
          import('./features/admin/events/event-accounting').then((m) => m.EventAccounting),
      },
      {
        // Rutas hermanas de fase 3: solo adiciones, con el parámetro `eventId` (no
        // `id`, que usa la ruta de detalle de arriba) porque `withComponentInputBinding()`
        // vincula por nombre exacto y estos 5 componentes ya declaran
        // `readonly eventId = input.required<string>()`.
        path: 'events/:eventId/agenda',
        loadComponent: () =>
          import('./features/admin/events/event-agenda').then((m) => m.EventAgenda),
      },
      {
        path: 'events/:eventId/entradas',
        loadComponent: () =>
          import('./features/admin/events/event-ticket-types').then((m) => m.EventTicketTypes),
      },
      {
        path: 'events/:eventId/descuentos',
        loadComponent: () =>
          import('./features/admin/events/event-discount-codes').then((m) => m.EventDiscountCodes),
      },
      {
        path: 'events/:eventId/patrocinadores',
        loadComponent: () =>
          import('./features/admin/events/event-sponsors').then((m) => m.EventSponsors),
      },
      {
        path: 'events/:eventId/inscripciones',
        loadComponent: () =>
          import('./features/admin/events/event-registrations').then((m) => m.EventRegistrations),
      },
      {
        path: 'sponsor-tiers',
        loadComponent: () =>
          import('./features/admin/sponsors/sponsor-tiers-page').then((m) => m.SponsorTiersPage),
      },
      {
        path: 'stripe',
        loadComponent: () =>
          import('./features/admin/organization/stripe-connection').then((m) => m.StripeConnection),
      },
      {
        path: 'legal',
        loadComponent: () =>
          import('./features/admin/legal/legal-pages-page').then((m) => m.LegalPagesPage),
      },
      {
        path: 'account',
        loadComponent: () =>
          import('./features/admin/account/account-page').then((m) => m.AccountPage),
      },
    ],
  },

  {
    // Panel de la plataforma: solo quien administra la instalación. Antes vivía
    // bajo `/admin/superadmin`; ahora ocupa la raíz `/admin`, que es lo que su
    // nombre siempre quiso decir.
    path: 'admin',
    loadComponent: () => import('./layouts/admin/admin-shell').then((m) => m.AdminShell),
    canActivate: [superadminGuard],
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
        path: 'legales',
        loadComponent: () =>
          import('./features/admin/superadmin/platform-legal-page').then(
            (m) => m.PlatformLegalPage,
          ),
      },
      {
        path: 'suplantar',
        loadComponent: () =>
          import('./features/admin/superadmin/impersonation-page').then((m) => m.ImpersonationPage),
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

  {
    path: '',
    loadComponent: () => import('./layouts/public/public-shell').then((m) => m.PublicShell),
    children: [
      {
        path: '',
        loadComponent: () => import('./features/public/home/home-page').then((m) => m.HomePage),
      },
      {
        path: 'eventos',
        loadComponent: () =>
          import('./features/public/events/events-list-page').then((m) => m.EventsListPage),
      },
      {
        path: 'eventos/:slug',
        loadComponent: () => import('./features/public/events/event-page').then((m) => m.EventPage),
      },
      {
        path: 'eventos/:slug/sesiones/:sessionId',
        loadComponent: () =>
          import('./features/public/events/session-page').then((m) => m.SessionPage),
      },
      {
        path: 'eventos/:slug/programa',
        loadComponent: () =>
          import('./features/public/events/event-venues-page').then((m) => m.EventVenuesPage),
      },
      {
        path: 'eventos/:slug/patrocinadores/:sponsorId',
        loadComponent: () =>
          import('./features/public/events/sponsor-page').then((m) => m.SponsorPage),
      },
      {
        path: 'eventos/:slug/inscribirse',
        loadComponent: () =>
          import('./features/public/events/registration-page').then((m) => m.RegistrationPage),
      },
      {
        path: 'pago/retorno',
        loadComponent: () =>
          import('./features/public/events/payment-return').then((m) => m.PaymentReturnPage),
      },
      {
        path: 'pago/cancelado',
        loadComponent: () =>
          import('./features/public/events/payment-cancelled-page').then(
            (m) => m.PaymentCancelledPage,
          ),
      },
      {
        path: 'ponentes/:publicSlug',
        loadComponent: () =>
          import('./features/public/events/speaker-page').then((m) => m.SpeakerPage),
      },
      {
        path: 'legal/aviso-legal',
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'aviso-legal' },
      },
      {
        path: 'legal/privacidad',
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'privacidad' },
      },
      {
        path: 'legal/cookies',
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'cookies' },
      },
      {
        path: 'legal/condiciones-de-inscripcion',
        loadComponent: () => import('./features/public/legal/legal-page').then((m) => m.LegalPage),
        data: { page: 'condiciones-de-inscripcion' },
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
