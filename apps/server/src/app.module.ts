import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { PrismaModule } from './prisma/prisma.module';
import { UsersModule } from './users/users.module';
import { RepositoriesModule } from './repositories/repositories.module';
import { TasksModule } from './tasks/tasks.module';
import { WorkerModule } from './worker/worker.module';
import { SessionsModule } from './sessions/sessions.module';
import { ProgressModule } from './progress/progress.module';
import { BotController } from './bot.controller';

@Module({
  imports: [
    PrismaModule,
    UsersModule,
    RepositoriesModule,
    TasksModule,
    WorkerModule,
    SessionsModule,
    ProgressModule,
  ],
  controllers: [AppController, BotController],
  providers: [AppService],
})
export class AppModule {}

