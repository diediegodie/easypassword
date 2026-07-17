import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

export interface VaultItem {
  id: string;
  service_name: string;
  login_name: string;
  password_blob: string;
  notes_blob?: string;
  created_at: string;
  updated_at: string;
}

@Injectable({ providedIn: 'root' })
export class VaultService {
  constructor(private readonly http: HttpClient) {}

  list(): Observable<VaultItem[]> {
    return this.http.get<VaultItem[]>('/api/v1/vault');
  }

  create(payload: Partial<VaultItem>): Observable<VaultItem> {
    return this.http.post<VaultItem>('/api/v1/vault', payload);
  }

  update(id: string, payload: Partial<VaultItem>): Observable<VaultItem> {
    return this.http.put<VaultItem>(`/api/v1/vault/${id}`, payload);
  }

  delete(id: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`/api/v1/vault/${id}`);
  }
}
