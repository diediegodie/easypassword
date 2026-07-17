import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { VaultComponent } from './vault.component';
import { VaultService } from './vault.service';

@NgModule({
  imports: [CommonModule],
  declarations: [VaultComponent],
  providers: [VaultService],
  exports: [VaultComponent],
})
export class VaultModule {}
