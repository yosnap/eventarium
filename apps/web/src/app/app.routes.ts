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
    // Catálogo interno de componentes: sin enlace desde ningún sitio, solo para
    // revisarlos juntos mientras se diseña. No forma parte del producto.
    path: 'estilo',
    loadComponent: () =>
      import('./features/dev/style-guide/style-guide-page').then((m) => m.StyleGuidePage),
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
        path: 'branding',
        loadComponent: () =>
          import('./features/admin/branding/branding-page').then((m) => m.BrandingPage),
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
