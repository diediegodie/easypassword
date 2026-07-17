import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { SessionState } from '../core/session.state';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [AuthService, SessionState],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('requestReauthentication calls login/options', () => {
    const email = 'a@b.com';
    service.requestReauthentication(email).subscribe();
    const req = httpMock.expectOne('/api/v1/auth/login/options');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ email });
    req.flush({ authentication_id: 'id', public_key: {} });
  });
});
