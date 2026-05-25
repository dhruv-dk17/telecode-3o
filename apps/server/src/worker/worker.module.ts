import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { WorkerService } from './worker.service';
import { PrismaModule } from '../prisma/prisma.module';

@Module({
  imports: [HttpModule, PrismaModule],
  providers: [WorkerService],
  exports: [WorkerService],
})
export class WorkerModule {}
