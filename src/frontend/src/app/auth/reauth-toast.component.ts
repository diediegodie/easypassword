import { Component, computed } from '@angular/core';
import { SessionState } from '../core/session.state';

@Component({
  selector: 'app-reauth-toast',
  template: `
    <div
      *ngIf="showMessage()"
      class="reauth-toast"
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <span>{{ message() }}</span>
    </div>
  `,
  styles: [
    `
      .reauth-toast {
        position: fixed;
        bottom: 1rem;
        left: 1rem;
        right: 1rem;
        padding: 1rem 1.25rem;
        background: #111827;
        color: white;
        border-radius: 0.75rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.16);
        font-size: 0.95rem;
      }
    `,
  ],
})
export class ReauthToastComponent {
  constructor(private readonly sessionState: SessionState) {}

  public showMessage = computed(() => {
    return (
      this.sessionState.reauthRequired() && this.sessionState.reauthReason().reason === 'inactivity'
    );
  });

  public message = computed(() => {
    return (
      this.sessionState.reauthReason().detail ||
      'Your session expired due to inactivity. Please reauthenticate.'
    );
  });
}
