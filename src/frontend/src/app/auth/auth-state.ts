import { computed, signal, WritableSignal } from '@angular/core';

export type SessionStatus = 'authenticated' | 'reauthentication-required' | 'unauthenticated';

export interface AuthState {
  status: SessionStatus;
  accessToken: string | null;
  reauthMessage: string | null;
}

const initialState: AuthState = {
  status: 'unauthenticated',
  accessToken: null,
  reauthMessage: null,
};

export const authState: WritableSignal<AuthState> = signal(initialState);

export const isSessionActive = computed(() => authState().status === 'authenticated');
export const needsReauthentication = computed(
  () => authState().status === 'reauthentication-required',
);

export function setAuthenticated(token: string): void {
  authState.update((state) => ({
    ...state,
    accessToken: token,
    status: 'authenticated',
    reauthMessage: null,
  }));
}

export function setReauthenticationRequired(
  message = 'Your session expired due to inactivity. Please reauthenticate.',
): void {
  authState.update((state) => ({
    ...state,
    status: 'reauthentication-required',
    reauthMessage: message,
  }));
}

export function clearSession(): void {
  authState.set(initialState);
}
