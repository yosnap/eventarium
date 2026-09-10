import {
  ApplicationConfig,
  LOCALE_ID,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideServiceWorker } from '@angular/service-worker';
import { provideTransloco } from '@jsverse/transloco';

import { authInterceptor } from './core/api/auth.interceptor';
import { errorInterceptor } from './core/api/error.interceptor';
import { TraduccionesLoader } from './core/i18n/transloco-loader';
import { ThemingService } from './core/theming/theming.service';
import { environment } from '../environments/environment';
import { routes } from './app.routes';

// Sin esto, DatePipe/DecimalPipe caen al 'en-US' que Angular trae integrado por
// defecto: las fechas de la app (creada íntegramente en castellano) salían en
// inglés ("Friday, January 15, 2027") pese a que Transloco sí traduce el resto
// de textos — son dos mecanismos de localización distintos, y solo se había
// configurado uno.
registerLocaleData(localeEs, 'es-ES');

export const appConfig: ApplicationConfig = {
  providers: [
    { provide: LOCALE_ID, useValue: 'es-ES' },
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes, withComponentInputBinding()),
    provideClientHydration(withEventReplay()),
    // `withFetch` es necesario para que las peticiones funcionen igual en SSR.
    provideHttpClient(withFetch(), withInterceptors([errorInterceptor, authInterceptor])),
    provideTransloco({
      config: {
        availableLangs: ['es-ES'],
        defaultLang: 'es-ES',
        reRenderOnLangChange: false,
        prodMode: true,
      },
      loader: TraduccionesLoader,
    }),
    // El branding se carga antes de pintar nada: así no hay un parpadeo con la paleta
    // por defecto antes de aplicar la de la organización.
    provideAppInitializer(() => inject(ThemingService).load()),
    // Solo la PWA de check-in (fase 4 del PRD) lo necesita hoy, pero registrarlo aquí
    // no afecta al resto del panel: `enabled` ya lo desactiva fuera de producción, y
    // `provideServiceWorker` no hace nada en SSR (no hay `navigator.serviceWorker`).
    provideServiceWorker('ngsw-worker.js', {
      enabled: environment.production,
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
