import { Component, computed, signal } from '@angular/core';
import { authState, needsReauthentication } from '../auth/auth-state';

@Component({
  selector: 'app-reauth-toast',
  template: `
    <div
      *ngIf="isVisible()"
      class="reauth-toast"
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <span>{{ message }}</span>
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
        background: #1f2937;
        color: white;
        border-radius: 0.75rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.16);
        font-size: 0.95rem;
      }
    `,
  ],
})
export class ReauthToastComponent {
  readonly isVisible = needsReauthentication;
  readonly message = computed(
    () => authState().reauthMessage || 'Please reauthenticate to continue.',
  );
}
