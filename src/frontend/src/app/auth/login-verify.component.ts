import { Component, computed, signal, NgZone } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from './auth.service';
import { SessionState } from '../core/session.state';

@Component({
  selector: 'app-login-verify',
  template: `
    <section class="verify-shell" aria-labelledby="reauth-heading">
      <h1 id="reauth-heading">Reauthenticate to continue</h1>
      <p *ngIf="detail()" class="detail" role="status">{{ detail() }}</p>

      <form (submit)="onSubmit($event)" class="reauth-form" aria-describedby="reauth-help">
        <label for="email">Email address</label>
        <input
          id="email"
          type="email"
          [value]="email()"
          (input)="email.set($any($event.target).value)"
          autocomplete="email"
          placeholder="you@example.com"
          aria-required="true"
          aria-describedby="email-help"
        />
        <p id="email-help" class="hint">Use the email associated with your account.</p>
        <div *ngIf="email().length && !isEmailValid()" class="error" role="alert">
          Enter a valid email address.
        </div>

        <button type="submit" [disabled]="isLoading() || !isEmailValid()">
          Request reauthentication
        </button>
      </form>

      <div aria-live="polite" class="status-messages">
        <p *ngIf="resultMessage()" class="success">{{ resultMessage() }}</p>
        <p *ngIf="errorMessage()" class="error" role="alert">{{ errorMessage() }}</p>
      </div>
    </section>
  `,
  styles: [
    `
      .verify-shell {
        display: flex;
        flex-direction: column;
        gap: 16px;
        max-width: 560px;
        margin: 56px auto;
        padding: 24px;
        border: 1px solid #d1d5db;
        border-radius: 1rem;
        background: #ffffff;
      }

      .reauth-form {
        display: grid;
        gap: 12px;
      }

      input {
        width: 100%;
        padding: 12px 14px;
        border: 1px solid #9ca3af;
        border-radius: 0.75rem;
        font-size: 1rem;
      }

      button {
        width: fit-content;
        padding: 12px 18px;
        border: none;
        border-radius: 8px;
        color: white;
        background: #2563eb;
        font-size: 1rem;
        cursor: pointer;
      }

      button:disabled {
        opacity: 0.65;
        cursor: not-allowed;
      }

      .hint {
        margin: 0;
        color: #6b7280;
        font-size: 0.95rem;
      }

      .success {
        color: #047857;
      }

      .error {
        color: #dc2626;
      }
    `,
  ],
})
export class LoginVerifyComponent {
  public email = signal('');
  public isLoading = signal(false);
  public resultMessage = signal('');
  public errorMessage = signal('');
  public detail = computed(() => {
    const reason = this.sessionState.reauthReason().reason;
    if (reason === 'inactivity') {
      return 'Your session expired due to inactivity. Please reauthenticate.';
    }
    if (reason === 'expired') {
      return 'Your access token expired. Please reauthenticate to continue.';
    }
    return 'Please reauthenticate to continue.';
  });

  private retryCount = 0;

  constructor(
    private readonly authService: AuthService,
    private readonly router: Router,
    private readonly ngZone: NgZone,
    private readonly sessionState: SessionState,
  ) {}

  public onSubmit(event: Event): void {
    event.preventDefault();
    this.startReauth();
  }

  public startReauth(): void {
    if (!this.isEmailValid()) {
      this.errorMessage.set('Enter a valid email address to continue.');
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');
    this.resultMessage.set('');

    const email = this.email().trim();
    this.authService.requestReauthentication(email).subscribe({
      next: ({ authentication_id, public_key }) => {
        this.resultMessage.set('Request sent. Waiting for your authenticator...');
        void this.performWebAuthn(authentication_id, public_key);
      },
      error: (error: unknown) => {
        this.handleError(error, 'Unable to request reauthentication.');
      },
    });
  }

  private handleError(error: unknown, fallback: string): void {
    if (this.isChallengeExpired(error)) {
      this.errorMessage.set(
        'The authentication challenge expired. Requesting a new one. Please try again.',
      );
      if (this.retryCount < 1) {
        this.retryCount += 1;
        this.startReauth();
        return;
      }
    } else if (error instanceof Error) {
      this.errorMessage.set(error.message);
    } else {
      this.errorMessage.set(fallback);
    }

    this.isLoading.set(false);
  }

  private async performWebAuthn(authenticationId: string, publicKey: unknown): Promise<void> {
    try {
      if (!navigator.credentials?.get) {
        throw new Error('WebAuthn is not available in this browser.');
      }

      const assertion = await navigator.credentials.get({
        publicKey: publicKey as PublicKeyCredentialRequestOptions,
      });

      if (!assertion) {
        throw new Error('Reauthentication was cancelled.');
      }

      this.authService
        .verifyLogin({
          authentication_id: authenticationId,
          credential: this.serializeCredential(assertion as PublicKeyCredential),
        })
        .subscribe({
          next: (response) => {
            this.authService.handleSuccess(
              response.access_token,
              response.user_id,
              response.device_id,
            );
            this.resultMessage.set('Reauthentication succeeded. You may continue.');
            this.ngZone.run(() => {
              this.router.navigate(['/vault']);
            });
            this.isLoading.set(false);
          },
          error: (error: unknown) => {
            this.handleError(error, 'Reauthentication failed. Please try again.');
          },
        });
    } catch (error: unknown) {
      this.handleError(error, 'Unable to complete WebAuthn authentication. Please try again.');
    }
  }

  public isEmailValid(): boolean {
    const value = this.email().trim();
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  private serializeCredential(credential: PublicKeyCredential): unknown {
    const authResponse = credential.response as AuthenticatorAssertionResponse;
    return {
      id: credential.id,
      type: credential.type,
      rawId: this.arrayBufferToBase64(credential.rawId),
      response: {
        authenticatorData: this.arrayBufferToBase64(authResponse.authenticatorData),
        clientDataJSON: this.arrayBufferToBase64(authResponse.clientDataJSON),
        signature: this.arrayBufferToBase64(authResponse.signature),
        userHandle: this.arrayBufferToBase64(authResponse.userHandle),
      },
    };
  }

  private arrayBufferToBase64(buffer: ArrayBuffer | null): string | null {
    if (!buffer) {
      return null;
    }
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return window.btoa(binary);
  }

  private isChallengeExpired(error: unknown): boolean {
    const message = error instanceof Error ? error.message : typeof error === 'string' ? error : '';
    return /expired|timeout|challenge/i.test(message);
  }
}
