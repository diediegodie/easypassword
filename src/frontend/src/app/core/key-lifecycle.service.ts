import { Injectable, signal, computed } from '@angular/core';
import { CryptoService } from './crypto.service';
import { SecureStorageService, StoredKeyMaterial } from './secure-storage.service';

export interface KeyState {
  hasKey: boolean;
  keyVersion: number;
  rotating: boolean;
  derivedAt: string | null;
}

@Injectable({ providedIn: 'root' })
export class KeyLifecycleService {
  private cachedKey: CryptoKey | null = null;
  private cachedKeyVersion = 1;

  readonly keyState = signal<KeyState>({
    hasKey: false,
    keyVersion: 1,
    rotating: false,
    derivedAt: null,
  });

  readonly hasKey = computed(() => this.keyState().hasKey);

  constructor(
    private readonly crypto: CryptoService,
    private readonly storage: SecureStorageService,
  ) {}

  async unlock(password: string): Promise<CryptoKey> {
    let material = await this.storage.getKeyMaterial();

    if (material === null) {
      const salt = this.crypto.generateSalt();
      const key = await this.crypto.deriveKey(password, salt);
      material = {
        salt: this.bytesToBase64(salt),
        derivedKey: '',
        keyVersion: 1,
        createdAt: new Date().toISOString(),
        rotatedAt: null,
      };
      await this.storage.storeKeyMaterial(material);
      this.setKey(key, material.keyVersion);
      return key;
    }

    const salt = this.base64ToBytes(material.salt);
    const key = await this.crypto.deriveKey(password, salt);
    this.setKey(key, material.keyVersion);
    return key;
  }

  async rotateKey(password: string): Promise<CryptoKey> {
    this.keyState.update((s) => ({ ...s, rotating: true }));

    try {
      const oldMaterial = await this.storage.getKeyMaterial();
      const newSalt = this.crypto.generateSalt();
      const newKey = await this.crypto.deriveKey(password, newSalt);

      const material: StoredKeyMaterial = {
        salt: this.bytesToBase64(newSalt),
        derivedKey: '',
        keyVersion: (oldMaterial?.keyVersion ?? 1) + 1,
        createdAt: oldMaterial?.createdAt ?? new Date().toISOString(),
        rotatedAt: new Date().toISOString(),
      };

      await this.storage.storeKeyMaterial(material);
      this.setKey(newKey, material.keyVersion);
      return newKey;
    } finally {
      this.keyState.update((s) => ({ ...s, rotating: false }));
    }
  }

  getKey(): CryptoKey {
    if (this.cachedKey === null) {
      throw new Error('Key not derived — call unlock() first');
    }
    return this.cachedKey;
  }

  getKeyVersion(): number {
    return this.cachedKeyVersion;
  }

  isRotationNeeded(serverKeyVersion: number): boolean {
    return serverKeyVersion > this.cachedKeyVersion;
  }

  async lock(): Promise<void> {
    this.cachedKey = null;
    this.cachedKeyVersion = 1;
    this.keyState.set({
      hasKey: false,
      keyVersion: 1,
      rotating: false,
      derivedAt: null,
    });
  }

  async purge(): Promise<void> {
    await this.lock();
    await this.storage.deleteKeyMaterial();
  }

  private setKey(key: CryptoKey, version: number): void {
    this.cachedKey = key;
    this.cachedKeyVersion = version;
    this.keyState.set({
      hasKey: true,
      keyVersion: version,
      rotating: false,
      derivedAt: new Date().toISOString(),
    });
  }

  private bytesToBase64(bytes: Uint8Array): string {
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  private base64ToBytes(b64: string): Uint8Array {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }
}
