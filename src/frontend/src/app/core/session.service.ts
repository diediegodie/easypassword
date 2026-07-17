import { HttpClient } from '@angular/common/http';
import { Injectable, signal, computed } from '@angular/core';
import { Router } from '@angular/router';

export type ReauthReason = 'expired' | 'inactivity' | 'unknown';

export interface ReauthMetadata {
  reason: ReauthReason;
  detail?: string;
}

@Injectable({ providedIn: 'root' })
export class SessionService {
  public sessionValid = signal(false);
  public accessToken = signal<string | null>(null);
  public reauthRequired = signal(false);
  public reauthReason = signal<ReauthMetadata>({ reason: 'unknown' });
  public vaultAccessBlocked = computed(() => !this.sessionValid() || this.reauthRequired());

  constructor(
    private readonly http: HttpClient,
    private readonly router: Router,
  ) {}

  refreshSession() {
    return this.http.post<{ access_token: string }>('/api/v1/session/refresh', {});
  }

  revokeSession() {
    return this.http.post<{ status: string }>('/api/v1/session/revoke', {});
  }

  setSessionValid(token: string | null): void {
    this.sessionValid.set(true);
    this.accessToken.set(token);
    this.reauthRequired.set(false);
    this.reauthReason.set({ reason: 'unknown' });
  }

  requireReauthentication(reason: ReauthReason, detail?: string): void {
    this.reauthReason.set({ reason, detail });
    this.reauthRequired.set(true);
    this.sessionValid.set(false);
    this.accessToken.set(null);
  }

  clear(): void {
    this.sessionValid.set(false);
    this.accessToken.set(null);
    this.reauthRequired.set(false);
    this.reauthReason.set({ reason: 'unknown' });
  }
}
