import { Module, Global } from '@nestjs/common';
import { ProgressService } from './progress.service';

@Global()
@Module({
  providers: [ProgressService],
  exports: [ProgressService],
})
export class ProgressModule {}
