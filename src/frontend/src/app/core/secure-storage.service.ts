import { Injectable } from '@angular/core';

const DB_NAME = 'easypassword';
const DB_VERSION = 1;
const STORE_NAME = 'crypto-keys';
const KEY_RECORD_ID = 'master-key';

export interface StoredKeyMaterial {
  salt: string;
  derivedKey: string;
  keyVersion: number;
  createdAt: string;
  rotatedAt: string | null;
}

export type Platform = 'web' | 'ios' | 'android';

function detectPlatform(): Platform {
  const g = globalThis as unknown as { capacitor?: { getPlatform?: () => string } };
  if (typeof g.capacitor?.getPlatform === 'function') {
    const platform = g.capacitor.getPlatform();
    if (platform === 'ios') return 'ios';
    if (platform === 'android') return 'android';
  }
  return 'web';
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };
  });
}

function idbGet(db: IDBDatabase, key: string): Promise<StoredKeyMaterial | null> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const request = store.get(key);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result ?? null);
  });
}

function idbPut(db: IDBDatabase, key: string, value: StoredKeyMaterial): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const request = store.put({ id: key, ...value });
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

function idbDelete(db: IDBDatabase, key: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const request = store.delete(key);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}

@Injectable({ providedIn: 'root' })
export class SecureStorageService {
  private readonly platform: Platform;

  constructor() {
    this.platform = detectPlatform();
  }

  get currentPlatform(): Platform {
    return this.platform;
  }

  async storeKeyMaterial(material: StoredKeyMaterial): Promise<void> {
    switch (this.platform) {
      case 'web':
        await this.storeWeb(material);
        break;
      case 'ios':
        await this.storeNative('ios', material);
        break;
      case 'android':
        await this.storeNative('android', material);
        break;
    }
  }

  async getKeyMaterial(): Promise<StoredKeyMaterial | null> {
    switch (this.platform) {
      case 'web':
        return this.getWeb();
      case 'ios':
        return this.getNative('ios');
      case 'android':
        return this.getNative('android');
      default:
        return null;
    }
  }

  async deleteKeyMaterial(): Promise<void> {
    switch (this.platform) {
      case 'web':
        await this.deleteWeb();
        break;
      case 'ios':
        await this.deleteNative('ios');
        break;
      case 'android':
        await this.deleteNative('android');
        break;
    }
  }

  async hasKeyMaterial(): Promise<boolean> {
    const material = await this.getKeyMaterial();
    return material !== null;
  }

  private async storeWeb(material: StoredKeyMaterial): Promise<void> {
    const db = await openDB();
    await idbPut(db, KEY_RECORD_ID, material);
    db.close();
  }

  private async getWeb(): Promise<StoredKeyMaterial | null> {
    const db = await openDB();
    try {
      return await idbGet(db, KEY_RECORD_ID);
    } finally {
      db.close();
    }
  }

  private async deleteWeb(): Promise<void> {
    const db = await openDB();
    try {
      await idbDelete(db, KEY_RECORD_ID);
    } finally {
      db.close();
    }
  }

  // Native (iOS Keychain / Android Keystore via Capacitor)
  private async storeNative(platform: Platform, material: StoredKeyMaterial): Promise<void> {
    const SecureStorage = await this.loadNativePlugin();
    const json = JSON.stringify(material);
    await SecureStorage.set({ key: KEY_RECORD_ID, value: json });
    void platform;
  }

  private async getNative(platform: Platform): Promise<StoredKeyMaterial | null> {
    const SecureStorage = await this.loadNativePlugin();
    try {
      const result = await SecureStorage.get({ key: KEY_RECORD_ID });
      return JSON.parse(result.value) as StoredKeyMaterial;
    } catch {
      return null;
    }
    void platform;
  }

  private async deleteNative(platform: Platform): Promise<void> {
    const SecureStorage = await this.loadNativePlugin();
    await SecureStorage.remove({ key: KEY_RECORD_ID });
    void platform;
  }

  private async loadNativePlugin(): Promise<{
    set: (opts: { key: string; value: string }) => Promise<void>;
    get: (opts: { key: string }) => Promise<{ value: string }>;
    remove: (opts: { key: string }) => Promise<void>;
  }> {
    try {
      // @ts-ignore — optional native-only dependency, not installed in web builds
      const mod = await import('@capacitor/secure-storage');
      return mod.SecureStorage;
    } catch {
      // Fallback: use IndexedDB even on "native" if plugin missing
      return {
        set: async (opts) => {
          const db = await openDB();
          await idbPut(db, opts.key, JSON.parse(opts.value));
          db.close();
        },
        get: async (opts) => {
          const db = await openDB();
          try {
            const result = await idbGet(db, opts.key);
            return { value: result ? JSON.stringify(result) : '' };
          } finally {
            db.close();
          }
        },
        remove: async (opts) => {
          const db = await openDB();
          try {
            await idbDelete(db, opts.key);
          } finally {
            db.close();
          }
        },
      };
    }
  }
}
