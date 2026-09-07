import { Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'admin/login',
    loadComponent: () => import('./features/admin/login/login-page').then((m) => m.LoginPage),
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
    path: 'cuenta/confirmar-correo',
    loadComponent: () =>
      import('./features/public/confirm-email-change/confirm-email-change-page').then(
        (m) => m.ConfirmEmailChangePage,
      ),
  },
  {
    path: 'admin',
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
        loadComponent: () => import('./features/admin/events/event-form').then((m) => m.EventForm),
      },
      {
        path: 'account',
        loadComponent: () =>
          import('./features/admin/account/account-page').then((m) => m.AccountPage),
      },
      {
        // Catálogo interno de componentes: no forma parte del producto, pero vive
        // dentro del panel (autenticado) para revisarlos en el mismo contexto donde
        // se usan, en vez de una ruta pública sin enlace desde ningún sitio.
        path: 'estilo',
        loadComponent: () =>
          import('./features/dev/style-guide/style-guide-page').then((m) => m.StyleGuidePage),
      },
    ],
  },
  {
    path: '',
    loadComponent: () => import('./layouts/public/public-shell').then((m) => m.PublicShell),
    children: [
      {
        path: '',
        loadComponent: () => import('./features/public/home/home-page').then((m) => m.HomePage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
