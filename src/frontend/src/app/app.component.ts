import { Component, signal } from '@angular/core';
import { SessionState } from './core/session.state';

@Component({
  selector: 'app-root',
  template: `
    <div class="app-shell">
      <app-reauth-toast></app-reauth-toast>
      <router-outlet></router-outlet>
    </div>
  `,
})
export class AppComponent {
  constructor(public readonly sessionState: SessionState) {}
}
