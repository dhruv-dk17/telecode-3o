import {
  Controller,
  Post,
  Get,
  Body,
  Param,
  HttpCode,
  HttpStatus,
  Query,
  Res,
  Sse,
  MessageEvent,
} from '@nestjs/common';
import * as express from 'express';
import axios from 'axios';
import { Observable } from 'rxjs';
import { map, filter } from 'rxjs/operators';
import { UsersService } from './users/users.service';
import { RepositoriesService } from './repositories/repositories.service';
import { TasksService, CreateTaskDto } from './tasks/tasks.service';
import { WorkerService } from './worker/worker.service';
import { SyncCodesService } from './users/sync-codes.service';
import { SessionsService } from './sessions/sessions.service';
import { ProgressService } from './progress/progress.service';
import { TaskMode, TaskStatus } from '@prisma/client';


// ── DTOs ────────────────────────────────────────────────────────────────────

export class RegisterUserDto {
  telegramId: string;
  username?: string;
  firstName?: string;
  lastName?: string;
}

export class ConnectRepoDto {
  userId: string;
  fullName: string;          // "owner/repo"
  defaultBranch?: string;
}

export class SubmitTaskDto {
  userId: string;
  repositoryId?: string;
  mode: TaskMode;
  prompt: string;
  botToken: string;   // Required for worker to push results
  chatId: string;     // Required for worker to push results
}

export class UpdateTaskDto {
  status: TaskStatus;
  result?: string;
  branchName?: string;
  prUrl?: string;
}

// ── Controller ───────────────────────────────────────────────────────────────

@Controller('bot')
export class BotController {
  constructor(
    private readonly users: UsersService,
    private readonly repos: RepositoriesService,
    private readonly tasks: TasksService,
    private readonly worker: WorkerService,
    private readonly syncCodes: SyncCodesService,
    private readonly sessions: SessionsService,
    private readonly progressService: ProgressService,
  ) {}

  // ─ Users ─────────────────────────────────────────────────────────────────

  /** Called on every /start — idempotent user upsert */
  @Post('users/register')
  @HttpCode(HttpStatus.OK)
  async register(@Body() dto: RegisterUserDto) {
    const user = await this.users.findOrCreate({
      telegramId: dto.telegramId,
      username: dto.username,
      firstName: dto.firstName,
      lastName: dto.lastName,
    });
    return { user };
  }

  @Get('users/:telegramId')
  async getUser(@Param('telegramId') telegramId: string) {
    const user = await this.users.findByTelegramId(telegramId);
    return { user };
  }

  // ─ Repositories ──────────────────────────────────────────────────────────

  @Post('repos/connect')
  @HttpCode(HttpStatus.OK)
  async connectRepo(@Body() dto: ConnectRepoDto) {
    const repo = await this.repos.connect(
      dto.userId,
      dto.fullName,
      dto.defaultBranch,
    );
    return { repo };
  }

  @Get('repos/:userId')
  async listRepos(@Param('userId') userId: string) {
    const repos = await this.repos.findAllForUser(userId);
    return { repos };
  }

  @Get('repos/:userId/active')
  async activeRepo(@Param('userId') userId: string) {
    const repo = await this.repos.findActiveForUser(userId);
    return { repo };
  }

  // ─ Tasks ─────────────────────────────────────────────────────────────────

  @Post('tasks')
  @HttpCode(HttpStatus.CREATED)
  async submitTask(@Body() dto: SubmitTaskDto) {
    const task = await this.tasks.create({
      userId: dto.userId,
      repositoryId: dto.repositoryId,
      mode: dto.mode,
      prompt: dto.prompt,
    });

    let repoFullName: string | undefined;
    let repoDefaultBranch: string | undefined;

    if (dto.repositoryId) {
      const repo = await this.repos.findById(dto.repositoryId);
      if (repo) {
        repoFullName = repo.fullName;
        repoDefaultBranch = repo.defaultBranch;
      }
    }

    // Fetch session memory for this user to inject into AI context
    const sessionContext = await this.sessions.getContextString(dto.userId);

    // Fire and forget: dispatch to AI worker
    this.worker.dispatch({
      task,
      repoFullName,
      repoDefaultBranch,
      botToken: dto.botToken,
      chatId: dto.chatId,
      sessionContext,
    });

    return { task };
  }

  @Get('tasks/:userId')
  async listTasks(@Param('userId') userId: string) {
    const tasks = await this.tasks.findAllForUser(userId);
    return { tasks };
  }

  @Get('tasks/token/:apiToken')
  async listTasksByToken(@Param('apiToken') apiToken: string) {
    const user = await this.users.findByApiToken(apiToken);
    if (!user) {
      return { tasks: [] };
    }
    const tasks = await this.tasks.findAllForUser(user.id);
    return { tasks };
  }

  @Get('tasks/:userId/last')
  async lastTask(@Param('userId') userId: string) {
    const task = await this.tasks.getLastTask(userId);
    return { task };
  }

  @Post('tasks/:id/update')
  @HttpCode(HttpStatus.OK)
  async updateTask(
    @Param('id') id: string,
    @Body() dto: UpdateTaskDto & { userId: string },
  ) {
    const task = await this.tasks.updateStatus(
      id,
      dto.userId,
      dto.status,
      dto.result,
      dto.branchName,
      dto.prUrl,
    );
    return { task };
  }

  @Post('tasks/:id/rollback')
  @HttpCode(HttpStatus.OK)
  async rollbackTask(
    @Param('id') id: string,
    @Body() body: { userId: string },
  ) {
    const task = await this.tasks.rollback(id, body.userId);
    return { task };
  }

  // ─ Session Memory ──────────────────────────────────────────────────────────

  /**
   * Called by the Python worker after a task completes to persist session memory.
   * Body: { userId, mode, prompt, result_summary, branch? }
   */
  @Post('session/append')
  @HttpCode(HttpStatus.OK)
  async appendSession(
    @Body()
    body: {
      userId: string;
      mode: string;
      prompt: string;
      result_summary: string;
      branch?: string;
    },
  ) {
    await this.sessions.appendEntry(body.userId, {
      mode: body.mode,
      prompt: body.prompt,
      result_summary: body.result_summary,
      branch: body.branch,
      timestamp: new Date().toISOString(),
    });
    return { ok: true };
  }

  /** Returns the user's current session memory (for debugging). */
  @Get('session/:userId')
  async getSession(@Param('userId') userId: string) {
    const context = await this.sessions.getContextString(userId);
    return { context };
  }

  @Post('sync/generate')
  @HttpCode(HttpStatus.OK)
  async generateSyncCode(@Body() body: { userId: string }) {
    const code = await this.syncCodes.generate(body.userId);
    return { code };
  }

  @Post('sync/exchange')
  @HttpCode(HttpStatus.OK)
  async exchangeSyncCode(@Body() body: { code: string }) {
    const result = await this.syncCodes.validateAndExchange(body.code);
    if (!result) {
      return { error: 'Invalid or expired code' };
    }

    const { apiToken, user } = result;

    // Notify user via Telegram bot
    const botToken = process.env.TELEGRAM_BOT_TOKEN;
    if (botToken && user.telegramId) {
      try {
        await axios.post(`https://api.telegram.org/bot${botToken}/sendMessage`, {
          chat_id: user.telegramId,
          text: `✅ <b>Sync Successful!</b>\n\nYour VS Code extension is now connected to this account. You can start sending tasks from your editor.`,
          parse_mode: 'HTML',
        });
      } catch (err) {
        console.error('Failed to send Telegram notification:', err.response?.data || err.message);
      }
    }

    return { apiToken };
  }

  @Get('github/callback')
  async githubCallback(
    @Query('code') code: string,
    @Query('state') state: string, // state contains telegramId
    @Res() res: express.Response,
  ) {
    const clientId = process.env.GITHUB_CLIENT_ID || 'Ov23liz6u286u286u286';
    const clientSecret = process.env.GITHUB_CLIENT_SECRET || 'github_pat_11AAAAAAA_BBBBBBBBB';

    try {
      if (!code || !state) {
        throw new Error('Missing code or state parameter');
      }

      // 1. Exchange OAuth code for access token
      const tokenResponse = await axios.post(
        'https://github.com/login/oauth/access_token',
        {
          client_id: clientId,
          client_secret: clientSecret,
          code,
        },
        {
          headers: {
            Accept: 'application/json',
          },
        },
      );

      const accessToken = tokenResponse.data.access_token;
      if (!accessToken) {
        throw new Error(`Failed to exchange code: ${JSON.stringify(tokenResponse.data)}`);
      }

      // 2. Fetch authenticated GitHub user details
      const userResponse = await axios.get('https://api.github.com/user', {
        headers: {
          Authorization: `token ${accessToken}`,
        },
      });

      const githubLogin = userResponse.data.login;

      // 3. Save githubToken and githubLogin to User in DB
      await this.users.updateGithubToken(state, accessToken, githubLogin);

      // 4. Notify user via Telegram Bot
      const botToken = process.env.TELEGRAM_BOT_TOKEN;
      if (botToken) {
        try {
          await axios.post(`https://api.telegram.org/bot${botToken}/sendMessage`, {
            chat_id: state,
            text: `✅ <b>GitHub Linked successfully!</b>\n\nConnected as: <code>@${githubLogin}</code>.\nYou can now run /plan, /fix, and /execute commands on your repositories securely!`,
            parse_mode: 'HTML',
          });
        } catch (botErr: any) {
          console.error('Failed to notify user on Telegram:', botErr.message);
        }
      }

      // 5. Send highly premium HTML Success page response
      res.setHeader('Content-Type', 'text/html');
      res.send(`
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Telecode Auth Success</title>
          <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
          <style>
            body {
              margin: 0;
              padding: 0;
              font-family: 'Outfit', sans-serif;
              background: linear-gradient(135deg, #0e121a 0%, #151a24 100%);
              color: #f3f4f6;
              display: flex;
              justify-content: center;
              align-items: center;
              min-height: 100vh;
              overflow: hidden;
            }
            .card {
              background: rgba(255, 255, 255, 0.03);
              backdrop-filter: blur(16px);
              border: 1px solid rgba(255, 255, 255, 0.08);
              border-radius: 24px;
              padding: 48px 32px;
              text-align: center;
              box-shadow: 0 20px 40px rgba(0,0,0,0.4);
              max-width: 440px;
              width: 100%;
              transform: translateY(20px);
              animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
            }
            .icon-wrapper {
              width: 80px;
              height: 80px;
              margin: 0 auto 24px auto;
              background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
              border-radius: 50%;
              display: flex;
              align-items: center;
              justify-content: center;
              font-size: 36px;
              box-shadow: 0 10px 20px rgba(79, 172, 254, 0.3);
              animation: popIn 0.6s 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275) both;
            }
            h1 {
              font-size: 28px;
              font-weight: 800;
              margin: 0 0 12px 0;
              background: linear-gradient(to right, #ffffff, #9ca3af);
              -webkit-background-clip: text;
              -webkit-text-fill-color: transparent;
            }
            p {
              font-size: 16px;
              color: #9ca3af;
              line-height: 1.6;
              margin: 0 0 24px 0;
            }
            .username {
              font-family: monospace;
              background: rgba(255, 255, 255, 0.06);
              border: 1px solid rgba(255, 255, 255, 0.1);
              padding: 8px 16px;
              border-radius: 8px;
              color: #38bdf8;
              font-size: 15px;
            }
            .close-tip {
              font-size: 13px;
              color: #6b7280;
              margin-top: 36px;
            }
            @keyframes fadeInUp {
              to {
                transform: translateY(0);
                opacity: 1;
              }
            }
            @keyframes popIn {
              from { transform: scale(0); opacity: 0; }
              to { transform: scale(1); opacity: 1; }
            }
          </style>
        </head>
        <body>
          <div class="card">
            <div class="icon-wrapper">🎉</div>
            <h1>Authentication Successful!</h1>
            <p>Your GitHub account has been connected securely.</p>
            <span class="username">@${githubLogin}</span>
            <p class="close-tip">You can close this tab and return to Telegram now.</p>
          </div>
        </body>
        </html>
      `);
    } catch (err: any) {
      console.error('GitHub callback failed:', err.message);
      res.setHeader('Content-Type', 'text/html');
      res.status(500).send(`
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <title>Auth Error</title>
          <style>
            body { background: #0e121a; color: #ef4444; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; }
            .error-card { background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.2); padding: 32px; border-radius: 12px; max-width: 400px; text-align: center; }
          </style>
        </head>
        <body>
          <div class="error-card">
            <h2>⚠️ Connection Failed</h2>
            <p>${err.message}</p>
          </div>
        </body>
        </html>
      `);
    }
  }

  // ─ Streaming Progress ──────────────────────────────────────────────────────

  @Post('progress')
  @HttpCode(HttpStatus.CREATED)
  async emitProgress(
    @Body()
    body: {
      userId: string;
      taskId: string;
      step: number;
      label: string;
      status: 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
      output?: string;
    },
  ) {
    this.progressService.emitProgress(body);
    return { ok: true };
  }

  @Post('tasks/:id/steer')
  @HttpCode(HttpStatus.OK)
  async postSteer(
    @Param('id') id: string,
    @Body() body: { userId: string; text: string },
  ) {
    this.progressService.setSteering(id, body.text);
    return { ok: true };
  }

  @Get('tasks/:id/steer')
  async getSteer(@Param('id') id: string) {
    const text = this.progressService.getAndClearSteering(id);
    return { steer: text };
  }

  @Post('tasks/:id/approve')
  @HttpCode(HttpStatus.OK)
  async postApprove(
    @Param('id') id: string,
    @Body() body: { userId: string; approved: boolean },
  ) {
    this.progressService.setApproval(id, body.approved);
    return { ok: true };
  }

  @Get('tasks/:id/approval')
  async getApproval(@Param('id') id: string) {
    const approved = this.progressService.getAndClearApproval(id);
    return { approved };
  }

  @Sse('progress/stream/:token')
  async streamProgress(@Param('token') token: string): Promise<Observable<MessageEvent>> {
    const user = await this.users.findByApiToken(token);
    const userId = user ? user.id : 'invalid';
    return this.progressService.getProgressStream().pipe(
      filter((event) => event.userId === userId),
      map((event) => ({
        data: event,
      } as MessageEvent)),
    );
  }
}
