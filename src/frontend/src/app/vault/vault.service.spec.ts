import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { VaultService } from './vault.service';

describe('VaultService', () => {
  let service: VaultService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [VaultService],
    });
    service = TestBed.inject(VaultService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('list() calls GET /api/v1/vault', () => {
    service.list().subscribe();
    const req = httpMock.expectOne('/api/v1/vault');
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });
});
