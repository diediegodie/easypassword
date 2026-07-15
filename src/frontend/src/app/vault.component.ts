import { Component } from '@angular/core';
import { SessionState } from './core/session.state';

@Component({
  selector: 'app-vault',
  template: `
    <section class="vault-shell">
      <h1>Vault Access</h1>
      <p *ngIf="sessionState.vaultAccessBlocked()">Your vault is locked. Please reauthenticate.</p>
      <p *ngIf="!sessionState.vaultAccessBlocked()">Welcome back. Vault access is enabled.</p>
    </section>
  `,
  styles: [
    `
      .vault-shell {
        max-width: 700px;
        margin: 48px auto;
        padding: 24px;
      }
    `,
  ],
})
export class VaultComponent {
  constructor(public readonly sessionState: SessionState) {}
}
