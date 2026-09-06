import { Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    path: 'admin/login',
    loadComponent: () => import('./features/admin/login/login-page').then((m) => m.LoginPage),
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
