import { TestBed } from '@angular/core/testing';
import { webcrypto } from 'crypto';
import {
  CryptoService,
  VERSION_BYTE,
  IV_LENGTH,
  TAG_LENGTH,
  SALT_LENGTH,
  PBKDF2_ITERATIONS,
  DERIVED_KEY_LENGTH,
  AAD_SEPARATOR,
  hexToBytes,
  bytesToHex,
} from './crypto.service';

if (typeof (globalThis as any).crypto === 'undefined' || !(globalThis as any).crypto.subtle) {
  Object.defineProperty(globalThis, 'crypto', {
    value: webcrypto,
    configurable: true,
    writable: true,
  });
}

const TEST_PASSWORD = 'CorrectHorseBatteryStaple';
const TEST_SALT_HEX = '000102030405060708090a0b0c0d0e0f';
const TEST_SALT = hexToBytes(TEST_SALT_HEX);
const TEST_DEVICE_ID = 'device-uuid-1234';
const TEST_USER_ID = 'user-abc';
const TEST_ITEM_ID = 'item-xyz';
const TEST_SERVICE_NAME = 'GitHub';

describe('CryptoService constants', () => {
  it('exports the canonical Phase 3.1 values', () => {
    expect(VERSION_BYTE).toBe(0x01);
    expect(IV_LENGTH).toBe(12);
    expect(TAG_LENGTH).toBe(16);
    expect(SALT_LENGTH).toBe(16);
    expect(PBKDF2_ITERATIONS).toBe(310_000);
    expect(DERIVED_KEY_LENGTH).toBe(32);
    expect(AAD_SEPARATOR).toBe(0x1f);
  });
});

describe('hex helpers', () => {
  it('round-trips bytes through hex', () => {
    const original = new Uint8Array([0x00, 0xff, 0xab, 0x01]);
    const hex = bytesToHex(original);
    expect(hex).toBe('00ffab01');
    expect(hexToBytes(hex)).toEqual(original);
  });

  it('hexToBytes produces correct values', () => {
    expect(hexToBytes('deadbeef')).toEqual(new Uint8Array([0xde, 0xad, 0xbe, 0xef]));
  });
});

describe('CryptoService.deriveKey', () => {
  let service: CryptoService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(CryptoService);
  });

  it('derives a non-extractable AES-GCM 256-bit key', async () => {
    const key = await service.deriveKey(TEST_PASSWORD, TEST_SALT);
    expect(key.extractable).toBe(false);
    expect(key.algorithm).toMatchObject({ name: 'AES-GCM', length: 256 });
    expect(key.usages).toContain('encrypt');
    expect(key.usages).toContain('decrypt');
  });

  it('is deterministic — same password + salt yields the same key', async () => {
    const key1 = await service.deriveKey(TEST_PASSWORD, TEST_SALT);
    const key2 = await service.deriveKey(TEST_PASSWORD, TEST_SALT);
    const iv = new Uint8Array(IV_LENGTH); // all zeros for determinism
    const plaintext = new TextEncoder().encode('test');
    const aad = new Uint8Array(0);

    const ct1 = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: aad, tagLength: 128 },
      key1,
      plaintext,
    );
    const ct2 = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: aad, tagLength: 128 },
      key2,
      plaintext,
    );
    expect(new Uint8Array(ct1)).toEqual(new Uint8Array(ct2));
  });

  it('throws when salt is not 16 bytes', async () => {
    await expect(service.deriveKey(TEST_PASSWORD, new Uint8Array(15))).rejects.toThrow(
      'Salt must be 16 bytes',
    );
    await expect(service.deriveKey(TEST_PASSWORD, new Uint8Array(17))).rejects.toThrow(
      'Salt must be 16 bytes',
    );
  });

  it('produces different keys for different salts', async () => {
    const salt2 = hexToBytes('ff0102030405060708090a0b0c0d0e0f');
    const key1 = await service.deriveKey(TEST_PASSWORD, TEST_SALT);
    const key2 = await service.deriveKey(TEST_PASSWORD, salt2);

    const iv = new Uint8Array(IV_LENGTH);
    const plaintext = new TextEncoder().encode('test');
    const aad = new Uint8Array(0);

    const ct1 = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: aad, tagLength: 128 },
      key1,
      plaintext,
    );
    const ct2 = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv, additionalData: aad, tagLength: 128 },
      key2,
      plaintext,
    );
    expect(new Uint8Array(ct1)).not.toEqual(new Uint8Array(ct2));
  });
});

describe('CryptoService.generateIV', () => {
  let service: CryptoService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(CryptoService);
  });

  it('produces a 12-byte IV', () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    expect(iv.length).toBe(IV_LENGTH);
  });

  it('throws for negative counters', () => {
    expect(() => service.generateIV(TEST_DEVICE_ID, -1)).toThrow();
  });

  it('throws for counters exceeding 32-bit range', () => {
    expect(() => service.generateIV(TEST_DEVICE_ID, 0x100000000)).toThrow();
  });

  it('produces unique IVs across multiple calls (random prefix)', () => {
    const ivs = new Set<string>();
    for (let i = 0; i < 100; i++) {
      ivs.add(bytesToHex(service.generateIV(TEST_DEVICE_ID, i)));
    }
    expect(ivs.size).toBe(100);
  });

  it('embeds counter XOR device-hash in bytes 8–11', () => {
    const counter = 0x12345678;
    const fakeRandom = new Uint8Array(8);
    const spy = jest
      .spyOn(crypto, 'getRandomValues')
      .mockImplementation(((array: ArrayBufferView | null): ArrayBufferView | null => {
        if (!array) return array;
        const view = array as unknown as Uint8Array;
        for (let i = 0; i < view.length; i++) {
          view[i] = fakeRandom[i % fakeRandom.length];
        }
        return array;
      }) as typeof crypto.getRandomValues);

    const iv = service.generateIV(TEST_DEVICE_ID, counter);
    spy.mockRestore();

    let h1 = 0x811c9dc5;
    for (let i = 0; i < TEST_DEVICE_ID.length; i++) {
      h1 ^= TEST_DEVICE_ID.charCodeAt(i);
      h1 = Math.imul(h1, 0x01000193);
    }
    const expectedDeviceHash = h1 >>> 0;
    const counterBytes = new Uint8Array(4);
    new DataView(counterBytes.buffer).setUint32(0, counter, false);

    for (let i = 0; i < 4; i++) {
      const expected = counterBytes[i] ^ ((expectedDeviceHash >> (24 - i * 8)) & 0xff);
      expect(iv[8 + i]).toBe(expected);
    }
  });

  it('advances the internal counter via nextCounter()', () => {
    expect(service.nextCounter()).toBe(0);
    expect(service.nextCounter()).toBe(1);
    expect(service.nextCounter()).toBe(2);
  });
});

describe('CryptoService.buildAAD', () => {
  let service: CryptoService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(CryptoService);
  });

  it('joins fields with 0x1F separator', () => {
    const aad = service.buildAAD(TEST_USER_ID, TEST_ITEM_ID, TEST_SERVICE_NAME);
    const sepPositions: number[] = [];
    for (let i = 0; i < aad.length; i++) {
      if (aad[i] === AAD_SEPARATOR) sepPositions.push(i);
    }
    expect(sepPositions.length).toBe(2);
  });

  it('matches the canonical byte layout', () => {
    const aad = service.buildAAD('u', 'i', 's');
    const expected = new Uint8Array([
      ...new TextEncoder().encode('u'),
      AAD_SEPARATOR,
      ...new TextEncoder().encode('i'),
      AAD_SEPARATOR,
      ...new TextEncoder().encode('s'),
    ]);
    expect(Array.from(aad)).toEqual(Array.from(expected));
  });

  it('normalizes Unicode to NFC', () => {
    const nfd = 'e\u0301';
    const nfc = '\u00e9';
    const aadNfd = service.buildAAD(nfd, 'x', 'y');
    const aadNfc = service.buildAAD(nfc, 'x', 'y');
    expect(Array.from(aadNfd)).toEqual(Array.from(aadNfc));
  });

  it('encodes fields as UTF-8', () => {
    const aad = service.buildAAD('café', 'item', 'serviço');
    const userBytes = new TextEncoder().encode('café'.normalize('NFC'));
    for (let i = 0; i < userBytes.length; i++) {
      expect(aad[i]).toBe(userBytes[i]);
    }
  });
});

describe('CryptoService.encryptBlob / decryptBlob', () => {
  let service: CryptoService;
  let key: CryptoKey;

  beforeEach(async () => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(CryptoService);
    key = await service.deriveKey(TEST_PASSWORD, TEST_SALT);
  });

  it('round-trips an object through encrypt → decrypt', async () => {
    const data = { v: 'my-secret-password' };
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    const blob = await service.encryptBlob(
      data,
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );

    const decrypted = await service.decryptBlob(
      blob,
      key,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );
    expect(decrypted).toEqual(data);
  });

  it('produces a base64 string', async () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    const blob = await service.encryptBlob(
      { v: 'test' },
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );
    expect(typeof blob).toBe('string');
    expect(() => atob(blob)).not.toThrow();
  });

  it('blob starts with version byte 0x01', async () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    const blob = await service.encryptBlob(
      { v: 'test' },
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );
    const raw = Uint8Array.from(atob(blob), (c) => c.charCodeAt(0));
    expect(raw[0]).toBe(VERSION_BYTE);
  });

  it('blob contains the IV in bytes 1–12', async () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 42);
    const blob = await service.encryptBlob(
      { v: 'test' },
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );
    const raw = Uint8Array.from(atob(blob), (c) => c.charCodeAt(0));
    const extractedIv = raw.subarray(1, 1 + IV_LENGTH);
    expect(Array.from(extractedIv)).toEqual(Array.from(iv));
  });

  it('throws when IV is not 12 bytes', async () => {
    await expect(
      service.encryptBlob(
        { v: 'test' },
        key,
        new Uint8Array(11),
        TEST_USER_ID,
        TEST_ITEM_ID,
        TEST_SERVICE_NAME,
      ),
    ).rejects.toThrow('IV must be 12 bytes');
  });

  it('decryption fails with wrong AAD (userId mismatch)', async () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    const blob = await service.encryptBlob(
      { v: 'secret' },
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );

    await expect(
      service.decryptBlob(blob, key, 'wrong-user', TEST_ITEM_ID, TEST_SERVICE_NAME),
    ).rejects.toThrow('Decryption failed');
  });

  it('decryption fails with wrong AAD (serviceName mismatch)', async () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    const blob = await service.encryptBlob(
      { v: 'secret' },
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );

    await expect(
      service.decryptBlob(blob, key, TEST_USER_ID, TEST_ITEM_ID, 'wrong-service'),
    ).rejects.toThrow('Decryption failed');
  });

  it('decryption fails with wrong key', async () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    const blob = await service.encryptBlob(
      { v: 'secret' },
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );

    const wrongKey = await service.deriveKey(
      TEST_PASSWORD,
      hexToBytes('ff0102030405060708090a0b0c0d0e0f'),
    );
    await expect(
      service.decryptBlob(blob, wrongKey, TEST_USER_ID, TEST_ITEM_ID, TEST_SERVICE_NAME),
    ).rejects.toThrow('Decryption failed');
  });

  it('throws on unsupported blob version', async () => {
    const iv = service.generateIV(TEST_DEVICE_ID, 0);
    const realBlob = await service.encryptBlob(
      { v: 'test' },
      key,
      iv,
      TEST_USER_ID,
      TEST_ITEM_ID,
      TEST_SERVICE_NAME,
    );
    const raw = Uint8Array.from(atob(realBlob), (c) => c.charCodeAt(0));
    raw[0] = 0x02;
    const tampered = btoa(String.fromCharCode(...raw));

    await expect(
      service.decryptBlob(tampered, key, TEST_USER_ID, TEST_ITEM_ID, TEST_SERVICE_NAME),
    ).rejects.toThrow('Unsupported blob version');
  });

  it('throws on truncated blob (no version byte)', async () => {
    const empty = btoa('');
    await expect(
      service.decryptBlob(empty, key, TEST_USER_ID, TEST_ITEM_ID, TEST_SERVICE_NAME),
    ).rejects.toThrow('Blob too short');
  });

  it('throws on truncated blob (too short for IV + tag)', async () => {
    const short = new Uint8Array([VERSION_BYTE, 1, 2, 3, 4, 5]);
    const shortB64 = btoa(String.fromCharCode(...short));
    await expect(
      service.decryptBlob(shortB64, key, TEST_USER_ID, TEST_ITEM_ID, TEST_SERVICE_NAME),
    ).rejects.toThrow('Blob too short');
  });
});

describe('CryptoService.generateSalt', () => {
  let service: CryptoService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(CryptoService);
  });

  it('produces a 16-byte salt', () => {
    const salt = service.generateSalt();
    expect(salt.length).toBe(SALT_LENGTH);
  });

  it('produces unique salts', () => {
    const salts = new Set<string>();
    for (let i = 0; i < 50; i++) {
      salts.add(bytesToHex(service.generateSalt()));
    }
    expect(salts.size).toBe(50);
  });
});
