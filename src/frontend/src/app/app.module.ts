import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule, HTTP_INTERCEPTORS } from '@angular/common/http';
import { RouterModule } from '@angular/router';
import { ReactiveFormsModule } from '@angular/forms';
import { AppComponent } from './app.component';
import { LoginVerifyComponent } from './auth/login-verify.component';
import { ReauthToastComponent } from './auth/reauth-toast.component';
import { VaultComponent } from './vault.component';
import { appRoutes } from './app.routes';
import { ReauthInterceptor } from './core/reauth.interceptor';

@NgModule({
  declarations: [AppComponent, LoginVerifyComponent, ReauthToastComponent, VaultComponent],
  imports: [BrowserModule, HttpClientModule, ReactiveFormsModule, RouterModule.forRoot(appRoutes)],
  providers: [
    {
      provide: HTTP_INTERCEPTORS,
      useClass: ReauthInterceptor,
      multi: true,
    },
  ],
  bootstrap: [AppComponent],
})
export class AppModule {}
