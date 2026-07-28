import { Injectable, computed, WritableSignal } from '@angular/core';
import { SessionService, ReauthMetadata, ReauthReason } from './session.service';

@Injectable({ providedIn: 'root' })
export class SessionState {
  public sessionValid: WritableSignal<boolean>;
  public accessToken: WritableSignal<string | null>;
  public userId: WritableSignal<string | null>;
  public deviceId: WritableSignal<string | null>;
  public reauthRequired: WritableSignal<boolean>;
  public reauthReason: WritableSignal<ReauthMetadata>;
  public vaultAccessBlocked: ReturnType<typeof computed>;

  constructor(private readonly sessionService: SessionService) {
    this.sessionValid = this.sessionService.sessionValid;
    this.accessToken = this.sessionService.accessToken;
    this.userId = this.sessionService.userId;
    this.deviceId = this.sessionService.deviceId;
    this.reauthRequired = this.sessionService.reauthRequired;
    this.reauthReason = this.sessionService.reauthReason;
    this.vaultAccessBlocked = computed(() => !this.sessionValid() || this.reauthRequired());
  }

  setSessionValid(
    value: boolean,
    token: string | null = null,
    userId: string | null = null,
    deviceId: string | null = null,
  ): void {
    this.sessionService.setSessionValid(token, userId, deviceId);
  }

  requireReauthentication(reason: ReauthReason, detail?: string) {
    this.sessionService.requireReauthentication(reason, detail);
  }

  clear() {
    this.sessionService.clear();
  }
}
