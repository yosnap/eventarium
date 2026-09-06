import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideTransloco } from '@jsverse/transloco';

import { authInterceptor } from './core/api/auth.interceptor';
import { errorInterceptor } from './core/api/error.interceptor';
import { TraduccionesLoader } from './core/i18n/transloco-loader';
import { ThemingService } from './core/theming/theming.service';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
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
  ],
};
