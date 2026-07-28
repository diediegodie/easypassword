import { Injectable } from '@angular/core';

export const VERSION_BYTE = 0x01;
export const IV_LENGTH = 12;
export const TAG_LENGTH = 16;
export const SALT_LENGTH = 16;
export const PBKDF2_ITERATIONS = 310_000;
export const DERIVED_KEY_LENGTH = 32;
export const AAD_SEPARATOR = 0x1f;

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return bytes;
}

export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function normalizeToNFCBytes(value: string): Uint8Array {
  const normalized = value.normalize('NFC');
  return new TextEncoder().encode(normalized);
}

@Injectable({ providedIn: 'root' })
export class CryptoService {
  private counter = 0;

  async deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
    if (salt.length !== SALT_LENGTH) {
      throw new Error(`Salt must be ${SALT_LENGTH} bytes`);
    }

    const keyMaterial = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(password),
      { name: 'PBKDF2' },
      false,
      ['deriveKey'],
    );

    return crypto.subtle.deriveKey(
      {
        name: 'PBKDF2',
        salt: salt as BufferSource,
        iterations: PBKDF2_ITERATIONS,
        hash: 'SHA-256',
      },
      keyMaterial,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt'],
    );
  }

  generateIV(deviceId: string, counter: number): Uint8Array {
    if (counter < 0 || counter > 0xffffffff) {
      throw new Error('Counter must be a 32-bit unsigned integer');
    }

    const iv = new Uint8Array(IV_LENGTH);

    crypto.getRandomValues(iv.subarray(0, 8));

    const deviceHash = this.deviceHash(deviceId);
    const counterBytes = new Uint8Array(4);
    const view = new DataView(counterBytes.buffer);
    view.setUint32(0, counter, false);

    for (let i = 0; i < 4; i++) {
      iv[8 + i] = counterBytes[i] ^ deviceHash[i];
    }

    this.counter = counter + 1;
    return iv;
  }

  nextCounter(): number {
    return this.counter++;
  }

  buildAAD(userId: string, itemId: string, serviceName: string): Uint8Array {
    const sep = new Uint8Array([AAD_SEPARATOR]);
    const user = normalizeToNFCBytes(userId);
    const item = normalizeToNFCBytes(itemId);
    const service = normalizeToNFCBytes(serviceName);

    const result = new Uint8Array(
      user.length + sep.length + item.length + sep.length + service.length,
    );
    let offset = 0;
    result.set(user, offset);
    offset += user.length;
    result.set(sep, offset);
    offset += sep.length;
    result.set(item, offset);
    offset += item.length;
    result.set(sep, offset);
    offset += sep.length;
    result.set(service, offset);

    return result;
  }

  async encryptBlob(
    data: object,
    key: CryptoKey,
    iv: Uint8Array,
    userId: string,
    itemId: string,
    serviceName: string,
  ): Promise<string> {
    if (iv.length !== IV_LENGTH) {
      throw new Error(`IV must be ${IV_LENGTH} bytes`);
    }

    const plaintext = new TextEncoder().encode(JSON.stringify(data));
    const aad = this.buildAAD(userId, itemId, serviceName);

    const ciphertextBuf = await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: iv as BufferSource,
        additionalData: aad as BufferSource,
        tagLength: TAG_LENGTH * 8,
      },
      key,
      plaintext as BufferSource,
    );

    const ciphertextTag = new Uint8Array(ciphertextBuf);

    const blob = new Uint8Array(1 + IV_LENGTH + ciphertextTag.length);
    blob[0] = VERSION_BYTE;
    blob.set(iv, 1);
    blob.set(ciphertextTag, 1 + IV_LENGTH);

    return bytesToBase64(blob);
  }

  async decryptBlob(
    blob: string,
    key: CryptoKey,
    userId: string,
    itemId: string,
    serviceName: string,
  ): Promise<object> {
    const data = base64ToBytes(blob);

    if (data.length < 1) {
      throw new Error('Blob too short');
    }

    const version = data[0];
    if (version !== VERSION_BYTE) {
      throw new Error(`Unsupported blob version: ${version}`);
    }

    if (data.length < 1 + IV_LENGTH + TAG_LENGTH) {
      throw new Error('Blob too short for IV and tag');
    }

    const iv = data.subarray(1, 1 + IV_LENGTH);
    const ciphertextTag = data.subarray(1 + IV_LENGTH);
    const aad = this.buildAAD(userId, itemId, serviceName);

    let plaintextBuf: ArrayBuffer;
    try {
      plaintextBuf = await crypto.subtle.decrypt(
        {
          name: 'AES-GCM',
          iv: iv as BufferSource,
          additionalData: aad as BufferSource,
          tagLength: TAG_LENGTH * 8,
        },
        key,
        ciphertextTag as BufferSource,
      );
    } catch {
      throw new Error('Decryption failed: authentication tag mismatch');
    }

    const plaintext = new TextDecoder().decode(plaintextBuf);
    return JSON.parse(plaintext);
  }

  generateSalt(): Uint8Array {
    const salt = new Uint8Array(SALT_LENGTH);
    crypto.getRandomValues(salt);
    return salt;
  }

  private deviceHash(deviceId: string): Uint8Array {
    let h1 = 0x811c9dc5;
    for (let i = 0; i < deviceId.length; i++) {
      h1 ^= deviceId.charCodeAt(i);
      // FNV prime
      h1 = Math.imul(h1, 0x01000193);
    }
    const bytes = new Uint8Array(4);
    const view = new DataView(bytes.buffer);
    view.setUint32(0, h1 >>> 0, false);
    return bytes;
  }
}
