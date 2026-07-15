import { Routes } from '@angular/router';
import { LoginVerifyComponent } from './auth/login-verify.component';
import { VaultComponent } from './vault.component';

export const appRoutes: Routes = [
  {
    path: 'auth/login/verify',
    component: LoginVerifyComponent,
  },
  {
    path: 'vault',
    component: VaultComponent,
  },
  {
    path: '',
    redirectTo: 'vault',
    pathMatch: 'full',
  },
  {
    path: '**',
    redirectTo: 'vault',
  },
];
