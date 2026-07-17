import { Component } from '@angular/core';
import { Observable } from 'rxjs';
import { VaultItem, VaultService } from './vault.service';
import { SessionState } from '../core/session.state';

@Component({
  selector: 'app-vault',
  template: `
    <section class="vault-shell">
      <h1>Vault Access</h1>
      <p *ngIf="sessionState.vaultAccessBlocked()">Your vault is locked. Please reauthenticate.</p>
      <ng-container *ngIf="!sessionState.vaultAccessBlocked()">
        <p>Welcome back. Vault access is enabled.</p>
        <div *ngIf="vaultItems$ | async as vaultItems">
          <h2>Your vault entries</h2>
          <ul>
            <li *ngFor="let item of vaultItems">
              <strong>{{ item.service_name }}</strong> — {{ item.login_name }}
            </li>
          </ul>
          <p *ngIf="vaultItems.length === 0">No vault items found yet.</p>
        </div>
      </ng-container>
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
  public readonly vaultItems$: Observable<VaultItem[]>;

  constructor(
    public readonly sessionState: SessionState,
    private readonly vaultService: VaultService,
  ) {
    this.vaultItems$ = this.vaultService.list();
  }
}
