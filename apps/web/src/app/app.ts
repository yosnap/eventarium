import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { SiteUnavailable } from './features/public/site-unavailable';
import { ImpersonationBanner } from './features/admin/impersonation-banner';
import { ThemingService } from './core/theming/theming.service';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, SiteUnavailable, ImpersonationBanner],
  template: `
    @if (theming.error()) {
      <app-site-unavailable />
    } @else {
      <app-impersonation-banner />
      <router-outlet />
    }
  `,
})
export class App {
  protected readonly theming = inject(ThemingService);
}
