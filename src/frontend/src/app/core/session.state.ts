import { Injectable, computed, signal } from '@angular/core';

export type ReauthReason = 'expired' | 'inactivity' | 'unknown';

export interface ReauthMetadata {
  reason: ReauthReason;
  detail?: string;
}

@Injectable({ providedIn: 'root' })
export class SessionState {
  public sessionValid = signal(false);
  public accessToken = signal<string | null>(null);
  public reauthRequired = signal(false);
  public reauthReason = signal<ReauthMetadata>({ reason: 'unknown' });
  public vaultAccessBlocked = computed(() => !this.sessionValid() || this.reauthRequired());

  setSessionValid(value: boolean, token: string | null = null) {
    this.sessionValid.set(value);
    this.accessToken.set(value ? token : null);
    if (value) {
      this.reauthRequired.set(false);
      this.reauthReason.set({ reason: 'unknown' });
    }
  }

  requireReauthentication(reason: ReauthReason, detail?: string) {
    this.reauthReason.set({ reason, detail });
    this.reauthRequired.set(true);
    this.sessionValid.set(false);
    this.accessToken.set(null);
  }

  clear() {
    this.sessionValid.set(false);
    this.accessToken.set(null);
    this.reauthRequired.set(false);
    this.reauthReason.set({ reason: 'unknown' });
  }
}
