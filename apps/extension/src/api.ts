import axios from 'axios';
import * as vscode from 'vscode';

export class TelecodeApi {
  private baseUrl: string;

  constructor() {
    this.baseUrl = vscode.workspace.getConfiguration('telecode').get('apiUrl') || 'http://localhost:3005/api';
  }

  async exchangeCode(code: string): Promise<string | null> {
    try {
      const response = await axios.post(`${this.baseUrl}/bot/sync/exchange`, { code });
      return response.data.apiToken || null;
    } catch (error) {
      console.error('Telecode API Error (Exchange):', error);
      return null;
    }
  }

  async getTasks(token: string): Promise<any[]> {
    try {
      const response = await axios.get(`${this.baseUrl}/bot/tasks/token/${token}`);
      return response.data.tasks || [];
    } catch (error) {
      console.error('Telecode API Error (GetTasks):', error);
      return [];
    }
  }

  /**
   * Returns the most recently COMPLETED task for the user, or null.
   * Used by the auto-sync poller to detect new AI-generated changes.
   */
  async getLatestCompletedTask(token: string): Promise<any | null> {
    try {
      const tasks: any[] = await this.getTasks(token);
      const completed = tasks.filter(t => t.status === 'COMPLETED');
      if (completed.length === 0) return null;
      // Tasks are returned in desc order; first completed is most recent
      return completed[0];
    } catch (error) {
      console.error('Telecode API Error (GetLatestCompleted):', error);
      return null;
    }
  }
}
