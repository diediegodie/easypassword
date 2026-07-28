import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { CryptoService } from '../core/crypto.service';
import { KeyLifecycleService } from '../core/key-lifecycle.service';
import { SessionState } from '../core/session.state';

export interface VaultItemPlaintext {
  id: string;
  service_name: string;
  login_name: string;
  password: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface VaultItem {
  id: string;
  service_name: string;
  login_name: string;
  password_blob: string;
  notes_blob?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateVaultItemRequest {
  service_name: string;
  login_name: string;
  password: string;
  notes?: string;
}

export interface UpdateVaultItemRequest {
  service_name?: string;
  login_name?: string;
  password?: string;
  notes?: string;
}

@Injectable({ providedIn: 'root' })
export class VaultService {
  constructor(
    private readonly http: HttpClient,
    private readonly crypto: CryptoService,
    private readonly keyLifecycle: KeyLifecycleService,
    private readonly sessionState: SessionState,
  ) {}

  async list(): Promise<VaultItemPlaintext[]> {
    this.requireSession();
    const items = await firstValueFrom(this.http.get<VaultItem[]>('/api/v1/vault'));
    return Promise.all(items.map((item) => this.decryptItem(item)));
  }

  async create(payload: CreateVaultItemRequest): Promise<VaultItemPlaintext> {
    const { userId, deviceId } = this.requireSession();

    const itemId = '';
    const key = this.keyLifecycle.getKey();
    const iv = this.crypto.generateIV(deviceId, this.crypto.nextCounter());

    const passwordBlob = await this.crypto.encryptBlob(
      { v: payload.password },
      key,
      iv,
      userId,
      itemId,
      payload.service_name,
    );

    let notesBlob: string | undefined;
    if (payload.notes) {
      const notesIv = this.crypto.generateIV(deviceId, this.crypto.nextCounter());
      notesBlob = await this.crypto.encryptBlob(
        { v: payload.notes },
        key,
        notesIv,
        userId,
        itemId,
        payload.service_name,
      );
    }

    const encryptedPayload: Partial<VaultItem> = {
      service_name: payload.service_name,
      login_name: payload.login_name,
      password_blob: passwordBlob,
      notes_blob: notesBlob,
    };

    const created = await firstValueFrom(
      this.http.post<VaultItem>('/api/v1/vault', encryptedPayload),
    );
    return this.decryptItem(created);
  }

  async update(id: string, payload: UpdateVaultItemRequest): Promise<VaultItemPlaintext> {
    const { userId, deviceId } = this.requireSession();
    const key = this.keyLifecycle.getKey();

    const encryptedPayload: Partial<VaultItem> = {};

    if (payload.service_name !== undefined) {
      encryptedPayload.service_name = payload.service_name;
    }
    if (payload.login_name !== undefined) {
      encryptedPayload.login_name = payload.login_name;
    }

    const serviceNameForAad = payload.service_name ?? '';

    if (payload.password !== undefined) {
      const iv = this.crypto.generateIV(deviceId, this.crypto.nextCounter());
      encryptedPayload.password_blob = await this.crypto.encryptBlob(
        { v: payload.password },
        key,
        iv,
        userId,
        id,
        serviceNameForAad,
      );
    }

    if (payload.notes !== undefined) {
      const iv = this.crypto.generateIV(deviceId, this.crypto.nextCounter());
      encryptedPayload.notes_blob = await this.crypto.encryptBlob(
        { v: payload.notes },
        key,
        iv,
        userId,
        id,
        serviceNameForAad,
      );
    }

    const updated = await firstValueFrom(
      this.http.put<VaultItem>(`/api/v1/vault/${id}`, encryptedPayload),
    );
    return this.decryptItem(updated);
  }

  async delete(id: string): Promise<{ status: string }> {
    return firstValueFrom(this.http.delete<{ status: string }>(`/api/v1/vault/${id}`));
  }

  private async decryptItem(item: VaultItem): Promise<VaultItemPlaintext> {
    const { userId } = this.requireSession();
    const key = this.keyLifecycle.getKey();

    const password = await this.decryptField(
      item.password_blob,
      key,
      userId,
      item.id,
      item.service_name,
    );

    let notes: string | undefined;
    if (item.notes_blob) {
      notes = await this.decryptField(item.notes_blob, key, userId, item.id, item.service_name);
    }

    return {
      id: item.id,
      service_name: item.service_name,
      login_name: item.login_name,
      password,
      notes,
      created_at: item.created_at,
      updated_at: item.updated_at,
    };
  }

  private async decryptField(
    blob: string,
    key: CryptoKey,
    userId: string,
    itemId: string,
    serviceName: string,
  ): Promise<string> {
    const decrypted = await this.crypto.decryptBlob(blob, key, userId, itemId, serviceName);
    const obj = decrypted as { v: string };
    return obj.v;
  }

  private requireSession(): { userId: string; deviceId: string } {
    const userId = this.sessionState.userId();
    const deviceId = this.sessionState.deviceId();

    if (!userId || !deviceId) {
      throw new Error('User session not active — cannot perform vault operations');
    }

    if (!this.keyLifecycle.hasKey()) {
      throw new Error('Encryption key not unlocked — call KeyLifecycleService.unlock() first');
    }

    return { userId, deviceId };
  }
}
