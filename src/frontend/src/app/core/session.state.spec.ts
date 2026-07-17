import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { SessionState } from './session.state';

describe('SessionState', () => {
  let state: SessionState;

  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [HttpClientTestingModule], providers: [SessionState] });
    state = TestBed.inject(SessionState);
  });

  it('computes vaultAccessBlocked when reauth required', () => {
    state.setSessionValid(true);
    expect(state.vaultAccessBlocked()).toBe(false);
    state.requireReauthentication('inactivity');
    expect(state.vaultAccessBlocked()).toBe(true);
  });

  it('clears state on logout', () => {
    state.setSessionValid(true);
    state.requireReauthentication('expired');
    state.clear();
    expect(state.sessionValid()).toBe(false);
    expect(state.reauthRequired()).toBe(false);
    expect(state.reauthReason().reason).toBe('unknown');
  });
});
