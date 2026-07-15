import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { LoginVerifyComponent } from './login-verify.component';
import { SessionState } from '../core/session.state';
import { environment } from '../../environments/environment';

describe('LoginVerifyComponent', () => {
  let component: LoginVerifyComponent;
  let fixture: ComponentFixture<LoginVerifyComponent>;
  let httpMock: HttpTestingController;
  let sessionState: SessionState;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HttpClientTestingModule, RouterTestingModule.withRoutes([])],
      declarations: [LoginVerifyComponent],
      providers: [SessionState],
    }).compileComponents();

    fixture = TestBed.createComponent(LoginVerifyComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    sessionState = TestBed.inject(SessionState);
    sessionState.requireReauthentication('inactivity');
    fixture.detectChanges();

    const credentials = {
      get: jest.fn().mockResolvedValue({
        id: 'test-credential',
        type: 'public-key',
        rawId: new ArrayBuffer(1),
        response: {
          authenticatorData: new ArrayBuffer(1),
          clientDataJSON: new ArrayBuffer(1),
          signature: new ArrayBuffer(1),
          userHandle: null,
        },
      }),
    };
    Object.defineProperty(navigator, 'credentials', {
      value: credentials,
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('shows inactivity detail when required', () => {
    expect(component.detail()).toContain('Your session expired due to inactivity');
  });

  it('requests challenge and completes reauth successfully', async () => {
    component.email.set('test@example.com');
    component.startReauth();

    const req = httpMock.expectOne('/api/v1/auth/login/options');
    expect(req.request.method).toBe('POST');
    req.flush({ authentication_id: 'test-auth-id', public_key: { challenge: 'dummy' } });

    await fixture.whenStable();

    const completeReq = httpMock.expectOne('/api/v1/auth/login/verify');
    expect(completeReq.request.method).toBe('POST');
    completeReq.flush({
      access_token: 'test-token',
      token_type: 'Bearer',
      user_id: 'uuid',
      device_id: 'uuid',
    });

    await fixture.whenStable();
    expect(sessionState.sessionValid()).toBe(true);
    expect(sessionState.reauthRequired()).toBe(false);
  });
});
