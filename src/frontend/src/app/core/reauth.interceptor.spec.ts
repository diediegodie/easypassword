import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { inject, TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { HttpClient, HTTP_INTERCEPTORS } from '@angular/common/http';
import { ReauthInterceptor } from './reauth.interceptor';
import { SessionState } from './session.state';

class RouterStub {
  navigate(commands: any[]) {
    return Promise.resolve(true);
  }
}

describe('ReauthInterceptor', () => {
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

  afterEach(() => {
    httpMock.verify();
  });

  it('redirects on ReauthenticationRequired inactivity response', (done) => {
    http.get('/api/v1/protected/test').subscribe({
      next: () => fail('Should not succeed'),
      error: () => {
        expect(sessionState.reauthRequired()).toBe(true);
        expect(sessionState.reauthReason().reason).toBe('inactivity');
        done();
      },
    });

    const req = httpMock.expectOne('/api/v1/protected/test');
    req.flush(
      { detail: 'Session expired due to inactivity', code: 'ReauthenticationRequired' },
      { status: 401, statusText: 'Unauthorized' },
    );
  });

  it('redirects on ReauthenticationRequired expired token response', (done) => {
    http.get('/api/v1/protected/test').subscribe({
      next: () => fail('Should not succeed'),
      error: () => {
        expect(sessionState.reauthRequired()).toBe(true);
        expect(sessionState.reauthReason().reason).toBe('expired');
        done();
      },
    });

    const req = httpMock.expectOne('/api/v1/protected/test');
    req.flush(
      { detail: 'JWT expired', code: 'ReauthenticationRequired' },
      { status: 401, statusText: 'Unauthorized' },
    );
  });
});
