import axios, { AxiosInstance } from 'axios';
import { TaskMode } from './types';

/**
 * ApiService — HTTP client for the Telecode NestJS server.
 * All bot commands funnel through here.
 */
export class ApiService {
  private http: AxiosInstance;

  constructor(baseURL?: string) {
    this.http = axios.create({
      baseURL: baseURL ?? process.env.SERVER_URL ?? 'http://localhost:3001/api',
      timeout: 10_000,
    });
  }

  // ─── Users ────────────────────────────────────────────────────────────────

  async registerUser(data: {
    telegramId: string;
    username?: string;
    firstName?: string;
    lastName?: string;
  }) {
    const res = await this.http.post('/bot/users/register', data);
    return res.data.user;
  }

  async getUser(telegramId: string) {
    const res = await this.http.get(`/bot/users/${telegramId}`);
    return res.data.user;
  }

  // ─── Repositories ────────────────────────────────────────────────────────

  async connectRepo(userId: string, fullName: string, defaultBranch = 'main') {
    const res = await this.http.post('/bot/repos/connect', {
      userId,
      fullName,
      defaultBranch,
    });
    return res.data.repo;
  }

  async listRepos(userId: string) {
    const res = await this.http.get(`/bot/repos/${userId}`);
    return res.data.repos;
  }

  async getActiveRepo(userId: string) {
    const res = await this.http.get(`/bot/repos/${userId}/active`);
    return res.data.repo;
  }

  // ─── Tasks ───────────────────────────────────────────────────────────────

  async submitTask(data: {
    userId: string;
    repositoryId?: string;
    mode: TaskMode;
    prompt: string;
    botToken: string;
    chatId: string;
  }) {
    const res = await this.http.post('/bot/tasks', data);
    return res.data.task;
  }

  async listTasks(userId: string) {
    const res = await this.http.get(`/bot/tasks/${userId}`);
    return res.data.tasks;
  }

  async getLastTask(userId: string) {
    const res = await this.http.get(`/bot/tasks/${userId}/last`);
    return res.data.task;
  }

  async rollbackLastTask(userId: string) {
    const lastTask = await this.getLastTask(userId);
    if (!lastTask) throw new Error('No tasks found to roll back');
    const res = await this.http.post(`/bot/tasks/${lastTask.id}/rollback`, {
      userId,
    });
    return res.data.task;
  }

  async generateSyncCode(userId: string) {
    const res = await this.http.post('/bot/sync/generate', { userId });
    return res.data.code;
  }

  async approveTask(taskId: string, approved: boolean) {
    const res = await this.http.post(`/bot/tasks/${taskId}/approve`, {
      userId: 'bot-override',
      approved,
    });
    return res.data;
  }
}
