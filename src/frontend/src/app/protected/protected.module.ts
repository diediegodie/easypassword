import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { ProtectedComponent } from './protected.component';

@NgModule({
  imports: [CommonModule],
  declarations: [ProtectedComponent],
  exports: [ProtectedComponent],
})
export class ProtectedModule {}
