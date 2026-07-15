import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { ReauthInterceptor } from '../core/reauth.interceptor';
import { SessionState } from '../core/session.state';

class RouterStub {
  navigate(commands: any[]) {
    return Promise.resolve(true);
  }
}

describe('Protected endpoint integration', () => {
  let httpMock: HttpTestingController;
  let http: HttpClient;
  let sessionState: SessionState;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        SessionState,
        { provide: Router, useClass: RouterStub },
        {
          provide: HTTP_INTERCEPTORS,
          useClass: ReauthInterceptor,
          multi: true,
        },
      ],
    });

    httpMock = TestBed.inject(HttpTestingController);
    http = TestBed.inject(HttpClient);
    sessionState = TestBed.inject(SessionState);
    router = TestBed.inject(Router);
  });

  afterEach(() => httpMock.verify());

  it('allows access to /api/v1/protected/test when the token is valid', (done) => {
    http.get('/api/v1/protected/test').subscribe({
      next: (response) => {
        expect(response).toEqual({ status: 'ok' });
        expect(sessionState.reauthRequired()).toBe(false);
        done();
      },
      error: () => fail('Should not fail on valid protected request'),
    });

    const req = httpMock.expectOne('/api/v1/protected/test');
    expect(req.request.method).toBe('GET');
    req.flush({ status: 'ok' });
  });

  it('requires reauthentication on inactivity timeout response', (done) => {
    jest.spyOn(router, 'navigate').mockResolvedValue(true);

    http.get('/api/v1/protected/test').subscribe({
      next: () => fail('Should not succeed'),
      error: () => {
        expect(sessionState.reauthRequired()).toBe(true);
        expect(sessionState.reauthReason().reason).toBe('inactivity');
        expect(router.navigate).toHaveBeenCalledWith(['/auth/login/verify'], {
          queryParams: { from: '/api/v1/protected/test' },
        });
        done();
      },
    });

    const req = httpMock.expectOne('/api/v1/protected/test');
    req.flush(
      { detail: 'Session expired due to inactivity', code: 'ReauthenticationRequired' },
      { status: 401, statusText: 'Unauthorized' },
    );
  });
});
