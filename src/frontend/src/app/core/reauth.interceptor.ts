import { Injectable } from '@angular/core';
import {
  HttpErrorResponse,
  HttpEvent,
  HttpHandler,
  HttpInterceptor,
  HttpRequest,
} from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, catchError, throwError } from 'rxjs';
import { SessionState } from './session.state';

interface ReauthErrorBody {
  detail?: string;
  code?: string;
}

@Injectable({ providedIn: 'root' })
export class ReauthInterceptor implements HttpInterceptor {
  constructor(
    private readonly router: Router,
    private readonly sessionState: SessionState,
  ) {}

  intercept(req: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    const token = this.sessionState.accessToken();
    const authReq =
      token && !req.headers.has('Authorization')
        ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
        : req;

    return next.handle(authReq).pipe(
      catchError((error: unknown) => {
        if (error instanceof HttpErrorResponse) {
          if (error.status === 401) {
            const body = error.error as ReauthErrorBody;
            const code = body?.code;
            if (code === 'ReauthenticationRequired') {
              const reason = /inactivity/i.test(body?.detail ?? '') ? 'inactivity' : 'expired';
              this.sessionState.requireReauthentication(reason, body?.detail);
              this.router.navigate(['/auth/login/verify'], { queryParams: { from: req.url } });
            }
          }
        }
        return throwError(() => error);
      }),
    );
  }
}
