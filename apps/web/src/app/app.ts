import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { SiteUnavailable } from './features/public/site-unavailable';
import { ThemingService } from './core/theming/theming.service';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, SiteUnavailable],
  template: `
    @if (theming.error()) {
      <app-site-unavailable />
    } @else {
      <router-outlet />
    }
  `,
})
export class App {
  protected readonly theming = inject(ThemingService);
}
