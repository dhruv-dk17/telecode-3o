import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { Task } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';

export interface DispatchOptions {
  task: Task;
  repoFullName?: string;
  repoDefaultBranch?: string;
  botToken: string;
  chatId: string;
  sessionContext?: string | null;
}


@Injectable()
export class WorkerService {
  private readonly logger = new Logger(WorkerService.name);
  private readonly workerUrl = process.env.WORKER_URL ?? 'http://localhost:8000';
  private readonly workerSecret = process.env.WORKER_SECRET ?? 'telecode-worker-secret-change-in-prod';

  constructor(
    private readonly http: HttpService,
    private readonly prisma: PrismaService,
  ) {}

  async dispatch(opts: DispatchOptions): Promise<boolean> {
    const { task, repoFullName, repoDefaultBranch, botToken, chatId, sessionContext } = opts;

    const user = await this.prisma.user.findUnique({
      where: { id: task.userId },
      select: { githubToken: true },
    });

    const payload = {
      task_id: task.id,
      user_id: task.userId,
      mode: task.mode,
      prompt: task.prompt,
      repo_full_name: repoFullName ?? null,
      repo_default_branch: repoDefaultBranch ?? null,
      github_token: user?.githubToken ?? null,
      session_context: sessionContext ?? null,
    };

    let retries = 3;
    while (retries > 0) {
      try {
        this.logger.debug(`Dispatching task ${task.id} to worker at ${this.workerUrl}... Payload: ${JSON.stringify(payload)}`);
        const response = await firstValueFrom(
          this.http.post(`${this.workerUrl}/process`, payload, {
            headers: {
              'X-Worker-Secret': this.workerSecret,
              'X-Bot-Token': botToken,
              'X-Chat-Id': chatId,
            },
            timeout: 10_000,
          }),
        );
        this.logger.log(`✅ Successfully dispatched task ${task.id} (${task.mode}) to worker. Status: ${response.status}`);
        return true;

      } catch (err: any) {
        retries--;
        const status = err?.response?.status;
        const message = err?.response?.data?.message || err?.message;
        this.logger.warn(
          `⚠️ Failed to dispatch task ${task.id} to worker (Status: ${status}, Retries left: ${retries}): ${message}`,
        );
        if (retries > 0) {
          await new Promise((resolve) => setTimeout(resolve, 2000 * (3 - retries)));
        }
      }
    }
    return false;
  }

  async healthCheck(): Promise<boolean> {
    try {
      this.logger.debug(`Checking worker health at ${this.workerUrl}/health...`);
      const res = await firstValueFrom(
        this.http.get(`${this.workerUrl}/health`, { timeout: 5_000 }),
      );
      const isOk = res.data?.status === 'ok';
      if (isOk) {
        this.logger.log(`🟢 Worker health check passed`);
      } else {
        this.logger.warn(`🔴 Worker health check failed: Unexpected status ${res.data?.status}`);
      }
      return isOk;
    } catch (err: any) {
      this.logger.error(`🔴 Worker health check failed: ${err.message}`);
      return false;
    }
  }
}
