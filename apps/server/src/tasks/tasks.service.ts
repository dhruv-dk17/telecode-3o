import { Injectable, NotFoundException, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { Task, TaskMode, TaskStatus } from '@prisma/client';
import axios from 'axios';

export interface CreateTaskDto {
  userId: string;
  repositoryId?: string;
  mode: TaskMode;
  prompt: string;
}

@Injectable()
export class TasksService {
  constructor(private prisma: PrismaService) {}

  async create(dto: CreateTaskDto): Promise<Task> {
    return this.prisma.task.create({
      data: {
        userId: dto.userId,
        repositoryId: dto.repositoryId,
        mode: dto.mode,
        prompt: dto.prompt,
        status: TaskStatus.PENDING,
      },
    });
  }

  async findAllForUser(userId: string, limit = 10): Promise<Task[]> {
    return this.prisma.task.findMany({
      where: { userId },
      orderBy: { createdAt: 'desc' },
      take: limit,
    });
  }

  async findOne(id: string, userId: string): Promise<Task> {
    const task = await this.prisma.task.findFirst({ where: { id, userId } });
    if (!task) throw new NotFoundException('Task not found');
    return task;
  }

  async updateStatus(
    id: string,
    userId: string,
    status: TaskStatus,
    result?: string,
    branchName?: string,
    prUrl?: string,
  ): Promise<Task> {
    await this.findOne(id, userId); // verify ownership
    return this.prisma.task.update({
      where: { id },
      data: { status, result, branchName, prUrl },
    });
  }

  private readonly logger = new Logger(TasksService.name);

  async rollback(id: string, userId: string): Promise<Task> {
    const task = await this.findOne(id, userId);
    if (task.status !== TaskStatus.COMPLETED) {
      throw new Error('Only completed tasks can be rolled back');
    }

    // Fetch user token and repository details for GitHub API calls
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    const githubToken = user?.githubToken;

    if (githubToken && task.repositoryId) {
      const repo = await this.prisma.repository.findUnique({
        where: { id: task.repositoryId },
      });

      if (repo) {
        const [owner, repoName] = repo.fullName.split('/');
        const headers = {
          Authorization: `token ${githubToken}`,
          Accept: 'application/vnd.github+json',
        };

        // 1. Close the Pull Request if one was created
        if (task.prUrl) {
          // Extract PR number from URL: .../pulls/123
          const prNumberMatch = task.prUrl.match(/\/pulls\/(\d+)/);
          if (prNumberMatch) {
            const prNumber = prNumberMatch[1];
            try {
              await axios.patch(
                `https://api.github.com/repos/${owner}/${repoName}/pulls/${prNumber}`,
                { state: 'closed' },
                { headers },
              );
              this.logger.log(`✅ Closed PR #${prNumber} for task ${id}`);
            } catch (err: any) {
              this.logger.warn(`⚠️ Could not close PR #${prNumber}: ${err.message}`);
            }
          }
        }

        // 2. Delete the feature branch if one was created
        if (task.branchName) {
          try {
            await axios.delete(
              `https://api.github.com/repos/${owner}/${repoName}/git/refs/heads/${task.branchName}`,
              { headers },
            );
            this.logger.log(`✅ Deleted branch '${task.branchName}' for task ${id}`);
          } catch (err: any) {
            this.logger.warn(`⚠️ Could not delete branch '${task.branchName}': ${err.message}`);
          }
        }
      }
    } else {
      this.logger.warn(`Rollback for task ${id}: no GitHub token or repository — skipping GitHub API calls.`);
    }

    return this.prisma.task.update({
      where: { id },
      data: { status: TaskStatus.ROLLED_BACK },
    });
  }

  async getLastTask(userId: string): Promise<Task | null> {
    return this.prisma.task.findFirst({
      where: { userId },
      orderBy: { createdAt: 'desc' },
    });
  }
}
