import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { LoginVerifyComponent } from './login-verify.component';
import { AuthService } from './auth.service';

@NgModule({
  imports: [CommonModule],
  declarations: [LoginVerifyComponent],
  providers: [AuthService],
  exports: [LoginVerifyComponent],
})
export class AuthModule {}
