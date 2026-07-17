import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { ReauthToastComponent } from './reauth-toast.component';

@NgModule({
  imports: [CommonModule],
  declarations: [ReauthToastComponent],
  exports: [ReauthToastComponent],
})
export class SharedModule {}
