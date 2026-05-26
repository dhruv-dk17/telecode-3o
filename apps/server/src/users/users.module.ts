import { Module } from '@nestjs/common';
import { UsersService } from './users.service';
import { SyncCodesService } from './sync-codes.service';
import { GithubOAuthService } from './github-oauth.service';

import { PrismaModule } from '../prisma/prisma.module';

@Module({
  imports: [PrismaModule],
  providers: [UsersService, SyncCodesService, GithubOAuthService],
  exports: [UsersService, SyncCodesService, GithubOAuthService],
})
export class UsersModule {}
