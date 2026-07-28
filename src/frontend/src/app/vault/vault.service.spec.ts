import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { VaultService, VaultItem, VaultItemPlaintext } from './vault.service';
import { CryptoService } from '../core/crypto.service';
import { KeyLifecycleService } from '../core/key-lifecycle.service';
import { SessionState } from '../core/session.state';

function createCryptoMock() {
  return {
    generateIV: jest.fn().mockReturnValue(new Uint8Array(12)),
    nextCounter: jest.fn().mockReturnValue(0),
    encryptBlob: jest.fn().mockResolvedValue('encrypted-blob'),
    decryptBlob: jest.fn().mockResolvedValue({ v: 'decrypted-value' }),
    generateSalt: jest.fn().mockReturnValue(new Uint8Array(16)),
  };
}

function createKeyLifecycleMock(hasKey = true) {
  const fakeKey = {} as CryptoKey;
  return {
    getKey: jest.fn().mockReturnValue(fakeKey),
    hasKey: jest.fn().mockReturnValue(hasKey),
    keyState: signal({ hasKey, keyVersion: 1, rotating: false, derivedAt: null }),
  };
}

function createSessionMock(userId = 'user-123', deviceId = 'device-456') {
  return {
    userId: signal(userId),
    deviceId: signal(deviceId),
    sessionValid: signal(true),
    accessToken: signal('token'),
    reauthRequired: signal(false),
    reauthReason: signal({ reason: null, detail: null }),
    vaultAccessBlocked: signal(false),
    setSessionValid: jest.fn(),
    requireReauthentication: jest.fn(),
    clear: jest.fn(),
  };
}

describe('VaultService', () => {
  let service: VaultService;
  let httpMock: HttpTestingController;
  let cryptoMock: ReturnType<typeof createCryptoMock>;
  let keyLifecycleMock: ReturnType<typeof createKeyLifecycleMock>;
  let sessionMock: ReturnType<typeof createSessionMock>;

  beforeEach(() => {
    cryptoMock = createCryptoMock();
    keyLifecycleMock = createKeyLifecycleMock();
    sessionMock = createSessionMock();

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        VaultService,
        { provide: CryptoService, useValue: cryptoMock },
        { provide: KeyLifecycleService, useValue: keyLifecycleMock },
        { provide: SessionState, useValue: sessionMock },
      ],
    });
    service = TestBed.inject(VaultService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  describe('list()', () => {
    it('calls GET /api/v1/vault and decrypts all items', async () => {
      const serverItems: VaultItem[] = [
        {
          id: 'item-1',
          service_name: 'GitHub',
          login_name: 'user1',
          password_blob: 'pw-blob-1',
          notes_blob: 'notes-blob-1',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'item-2',
          service_name: 'GitLab',
          login_name: 'user2',
          password_blob: 'pw-blob-2',
          created_at: '2024-01-02T00:00:00Z',
          updated_at: '2024-01-02T00:00:00Z',
        },
      ];

      const promise = service.list();
      const req = httpMock.expectOne('/api/v1/vault');
      expect(req.request.method).toBe('GET');
      req.flush(serverItems);

      const result = await promise;

      expect(result.length).toBe(2);
      expect(result[0].id).toBe('item-1');
      expect(result[0].password).toBe('decrypted-value');
      expect(result[0].notes).toBe('decrypted-value');
      expect(result[1].id).toBe('item-2');
      expect(result[1].notes).toBeUndefined();
      expect(cryptoMock.decryptBlob).toHaveBeenCalledWith(
        'pw-blob-1',
        expect.anything(),
        'user-123',
        'item-1',
        'GitHub',
      );
      expect(cryptoMock.decryptBlob).toHaveBeenCalledWith(
        'notes-blob-1',
        expect.anything(),
        'user-123',
        'item-1',
        'GitHub',
      );
    });

    it('handles empty list', async () => {
      const promise = service.list();
      const req = httpMock.expectOne('/api/v1/vault');
      req.flush([]);

      const result = await promise;
      expect(result).toEqual([]);
    });
  });

  describe('create()', () => {
    it('encrypts password and notes, then POSTs encrypted payload', async () => {
      const payload = {
        service_name: 'GitHub',
        login_name: 'myuser',
        password: 'plain-password',
        notes: 'plain-notes',
      };

      const serverResponse: VaultItem = {
        id: 'new-item-id',
        service_name: 'GitHub',
        login_name: 'myuser',
        password_blob: 'server-pw-blob',
        notes_blob: 'server-notes-blob',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      };

      const promise = service.create(payload);
      await Promise.resolve();
      await Promise.resolve();
      const req = httpMock.expectOne('/api/v1/vault');
      const body = req.request.body as Partial<VaultItem>;
      expect(body.service_name).toBe('GitHub');
      expect(body.login_name).toBe('myuser');
      expect(body.password_blob).toBe('encrypted-blob');
      expect(body.notes_blob).toBe('encrypted-blob');

      expect(cryptoMock.encryptBlob).toHaveBeenCalledWith(
        { v: 'plain-password' },
        expect.anything(),
        expect.any(Uint8Array),
        'user-123',
        '', // itemId is empty for new items
        'GitHub',
      );
      expect(cryptoMock.encryptBlob).toHaveBeenCalledWith(
        { v: 'plain-notes' },
        expect.anything(),
        expect.any(Uint8Array),
        'user-123',
        '',
        'GitHub',
      );

      req.flush(serverResponse);
      const result = await promise;

      expect(result.id).toBe('new-item-id');
      expect(result.password).toBe('decrypted-value');
      expect(result.notes).toBe('decrypted-value');
    });

    it('omits notes_blob when notes are not provided', async () => {
      const payload = {
        service_name: 'GitHub',
        login_name: 'myuser',
        password: 'plain-password',
      };

      const serverResponse: VaultItem = {
        id: 'new-item-id',
        service_name: 'GitHub',
        login_name: 'myuser',
        password_blob: 'server-pw-blob',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      };

      const promise = service.create(payload);
      await Promise.resolve();
      await Promise.resolve();
      const req = httpMock.expectOne('/api/v1/vault');
      const body = req.request.body as Partial<VaultItem>;
      expect(body.notes_blob).toBeUndefined();
      req.flush(serverResponse);
      await promise;
    });

    it('uses generateIV and nextCounter for IV generation', async () => {
      const payload = {
        service_name: 'GitHub',
        login_name: 'myuser',
        password: 'plain-password',
      };

      const promise = service.create(payload);
  await Promise.resolve();
  await Promise.resolve();
      const req = httpMock.expectOne('/api/v1/vault');
      req.flush({
        id: 'new-id',
        service_name: 'GitHub',
        login_name: 'myuser',
        password_blob: 'blob',
        created_at: '',
        updated_at: '',
      });

      expect(cryptoMock.nextCounter).toHaveBeenCalled();
      expect(cryptoMock.generateIV).toHaveBeenCalledWith('device-456', expect.any(Number));
      await promise;
    });
  });

  describe('update()', () => {
    it('PUTs to /api/v1/vault/{id} and returns decrypted item', async () => {
      const serverResponse: VaultItem = {
        id: 'item-1',
        service_name: 'GitHub',
        login_name: 'updated-user',
        password_blob: 'server-blob',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
      };

      const promise = service.update('item-1', { login_name: 'updated-user' });
  await Promise.resolve();
  await Promise.resolve();
      const req = httpMock.expectOne('/api/v1/vault/item-1');
      expect(req.request.method).toBe('PUT');

      const body = req.request.body as Partial<VaultItem>;
      expect(body.login_name).toBe('updated-user');
      expect(body.password_blob).toBeUndefined();
      expect(body.notes_blob).toBeUndefined();

      req.flush(serverResponse);
      const result = await promise;
      expect(result.id).toBe('item-1');
      expect(result.login_name).toBe('updated-user');
    });

    it('encrypts password when provided in update payload', async () => {
      const promise = service.update('item-1', {
        password: 'new-password',
        service_name: 'GitHub',
      });
      await Promise.resolve();
      await Promise.resolve();
      const req = httpMock.expectOne('/api/v1/vault/item-1');
      const body = req.request.body as Partial<VaultItem>;
      expect(body.password_blob).toBe('encrypted-blob');

      expect(cryptoMock.encryptBlob).toHaveBeenCalledWith(
        { v: 'new-password' },
        expect.anything(),
        expect.any(Uint8Array),
        'user-123',
        'item-1',
        'GitHub',
      );

      req.flush({
        id: 'item-1',
        service_name: 'GitHub',
        login_name: 'user',
        password_blob: 'blob',
        created_at: '',
        updated_at: '',
      });
      await promise;
    });

    it('encrypts notes when provided in update payload', async () => {
      const promise = service.update('item-1', {
        notes: 'new-notes',
        service_name: 'GitLab',
      });
      await Promise.resolve();
      await Promise.resolve();
      const req = httpMock.expectOne('/api/v1/vault/item-1');
      const body = req.request.body as Partial<VaultItem>;
      expect(body.notes_blob).toBe('encrypted-blob');

      expect(cryptoMock.encryptBlob).toHaveBeenCalledWith(
        { v: 'new-notes' },
        expect.anything(),
        expect.any(Uint8Array),
        'user-123',
        'item-1',
        'GitLab',
      );

      req.flush({
        id: 'item-1',
        service_name: 'GitLab',
        login_name: 'user',
        password_blob: 'blob',
        created_at: '',
        updated_at: '',
      });
      await promise;
    });

    it('uses empty string as serviceNameForAad when service_name not in payload', async () => {
      const promise = service.update('item-1', { password: 'new-pw' });
  await Promise.resolve();
  await Promise.resolve();
      const req = httpMock.expectOne('/api/v1/vault/item-1');

      expect(cryptoMock.encryptBlob).toHaveBeenCalledWith(
        { v: 'new-pw' },
        expect.anything(),
        expect.any(Uint8Array),
        'user-123',
        'item-1',
        '', // serviceNameForAad falls back to ''
      );

      req.flush({
        id: 'item-1',
        service_name: 'GitHub',
        login_name: 'user',
        password_blob: 'blob',
        created_at: '',
        updated_at: '',
      });
      await promise;
    });
  });

  describe('delete()', () => {
    it('sends DELETE to /api/v1/vault/{id}', async () => {
      const promise = service.delete('item-1');
      const req = httpMock.expectOne('/api/v1/vault/item-1');
      expect(req.request.method).toBe('DELETE');
      req.flush({ status: 'deleted' });

      const result = await promise;
      expect(result).toEqual({ status: 'deleted' });
    });
  });

  describe('requireSession() error handling', () => {
    it('throws when userId is null', async () => {
      sessionMock.userId.set(null as unknown as string);
      await expect(service.list()).rejects.toThrow('User session not active');
    });

    it('throws when deviceId is null', async () => {
      sessionMock.deviceId.set(null as unknown as string);
      await expect(service.list()).rejects.toThrow('User session not active');
    });

    it('throws when key is not unlocked', async () => {
      keyLifecycleMock.hasKey.mockReturnValue(false);
      await expect(service.list()).rejects.toThrow('Encryption key not unlocked');
    });

    it('throws on create() when session is not active', async () => {
      sessionMock.userId.set(null as unknown as string);
      await expect(
        service.create({ service_name: 's', login_name: 'l', password: 'p' }),
      ).rejects.toThrow('User session not active');
    });

    it('throws on update() when key is not unlocked', async () => {
      keyLifecycleMock.hasKey.mockReturnValue(false);
      await expect(service.update('id', { login_name: 'x' })).rejects.toThrow(
        'Encryption key not unlocked',
      );
    });
  });

  describe('decryption', () => {
    it('extracts .v field from decrypted blob', async () => {
      cryptoMock.decryptBlob
        .mockResolvedValueOnce({ v: 'plain-pw' })
        .mockResolvedValueOnce({ v: 'plain-notes' });

      const promise = service.list();
      const req = httpMock.expectOne('/api/v1/vault');
      req.flush([
        {
          id: 'item-1',
          service_name: 'GitHub',
          login_name: 'user',
          password_blob: 'pw-blob',
          notes_blob: 'notes-blob',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ]);

      const result = await promise;
      expect(result[0].password).toBe('plain-pw');
      expect(result[0].notes).toBe('plain-notes');
    });

    it('skips notes decryption when notes_blob is absent', async () => {
      cryptoMock.decryptBlob.mockResolvedValue({ v: 'plain-pw' });

      const promise = service.list();
      const req = httpMock.expectOne('/api/v1/vault');
      req.flush([
        {
          id: 'item-1',
          service_name: 'GitHub',
          login_name: 'user',
          password_blob: 'pw-blob',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
      ]);

      const result = await promise;
      expect(result[0].password).toBe('plain-pw');
      expect(result[0].notes).toBeUndefined();
      expect(cryptoMock.decryptBlob).toHaveBeenCalledTimes(1);
    });
  });
});
