import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { SessionState } from '../core/session.state';

interface LoginVerifyResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  device_id: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  constructor(
    private readonly http: HttpClient,
    private readonly sessionState: SessionState,
  ) {}

  testProtected(): Observable<{ status: string }> {
    return this.http.get<{ status: string }>('/api/v1/protected/test');
  }

  requestReauthentication(
    email: string,
  ): Observable<{ authentication_id: string; public_key: unknown }> {
    return this.http.post<{ authentication_id: string; public_key: unknown }>(
      '/api/v1/auth/login/options',
      { email },
    );
  }

  verifyLogin(credential: unknown): Observable<LoginVerifyResponse> {
    return this.http.post<LoginVerifyResponse>('/api/v1/auth/login/verify', credential);
  }

  handleSuccess(accessToken: string, userId?: string, deviceId?: string): void {
    this.sessionState.setSessionValid(true, accessToken, userId ?? null, deviceId ?? null);
  }

  logout(): void {
    this.sessionState.clear();
  }

  handleNetworkFailure(): void {
    this.sessionState.requireReauthentication(
      'unknown',
      'Network error occurred while validating session. Please reconnect and try again.',
    );
  }
}
