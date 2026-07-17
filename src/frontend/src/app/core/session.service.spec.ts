import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { SessionService } from './session.service';

describe('SessionService', () => {
  let service: SessionService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [SessionService, { provide: Router, useValue: { navigate: () => {} } }],
    });
    service = TestBed.inject(SessionService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('refreshSession posts to session/refresh', () => {
    service.refreshSession().subscribe();
    const req = httpMock.expectOne('/api/v1/session/refresh');
    expect(req.request.method).toBe('POST');
    req.flush({ access_token: 'tok' });
  });
});
