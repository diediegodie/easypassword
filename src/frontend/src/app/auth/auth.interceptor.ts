import { Injectable } from '@angular/core';
import {
  HttpEvent,
  HttpHandler,
  HttpInterceptor,
  HttpRequest,
  HttpResponse,
  HttpErrorResponse,
} from '@angular/common/http';
import { Router } from '@angular/router';
import { catchError, filter, map, Observable, throwError } from 'rxjs';
import { setReauthenticationRequired } from './auth-state';

const REAUTHENTICATION_CODE = 'ReauthenticationRequired';
const ACCESS_TOKEN_HEADER = 'Authorization';

@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  constructor(private readonly router: Router) {}

  intercept(req: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    const request = req;

    return next.handle(request).pipe(
      map((event) => {
        if (event instanceof HttpResponse) {
          return event;
        }
        return event;
      }),
      catchError((error: HttpErrorResponse) => this.handleError(error)),
    );
  }

  private handleError(error: HttpErrorResponse): Observable<never> {
    if (
      error.status === 401 &&
      error.error?.code === REAUTHENTICATION_CODE &&
      error.error?.detail?.includes('inactivity')
    ) {
      setReauthenticationRequired();
      this.router.navigate(['/auth/login/verify']);
      return throwError(() => error);
    }

    return throwError(() => error);
  }
}
