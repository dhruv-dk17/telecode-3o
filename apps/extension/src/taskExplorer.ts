import * as vscode from 'vscode';
import { TelecodeApi } from './api';
import { AuthManager } from './auth';

export class TaskExplorerProvider implements vscode.TreeDataProvider<TaskItem> {
  private _onDidChangeTreeData: vscode.EventEmitter<TaskItem | undefined | void> = new vscode.EventEmitter<TaskItem | undefined | void>();
  readonly onDidChangeTreeData: vscode.Event<TaskItem | undefined | void> = this._onDidChangeTreeData.event;

  private api: TelecodeApi;

  constructor(private auth: AuthManager) {
    this.api = new TelecodeApi();
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TaskItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: TaskItem): Promise<TaskItem[]> {
    if (element) {
      return [];
    }

    const token = await this.auth.getToken();
    if (!token) {
      return [new TaskItem('Not connected. Use "Telecode: Connect" to sign in.', vscode.TreeItemCollapsibleState.None)];
    }

    const tasks = await this.api.getTasks(token);
    if (tasks.length === 0) {
      return [new TaskItem('No active tasks found.', vscode.TreeItemCollapsibleState.None)];
    }

    return tasks.map(t => new TaskItem(
      `${t.mode}: ${t.prompt.substring(0, 30)}...`,
      vscode.TreeItemCollapsibleState.None,
      {
        command: 'telecode.viewTask',
        title: 'View Task',
        arguments: [t]
      },
      t.status
    ));
  }
}

class TaskItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly command?: vscode.Command,
    public readonly status?: string
  ) {
    super(label, collapsibleState);
    this.tooltip = `${this.label} (${this.status})`;
    this.description = this.status;
    
    if (this.status === 'COMPLETED') {
      this.iconPath = new vscode.ThemeIcon('check');
    } else if (this.status === 'IN_PROGRESS') {
      this.iconPath = new vscode.ThemeIcon('sync~spin');
    } else if (this.status === 'ROLLED_BACK') {
      this.iconPath = new vscode.ThemeIcon('discard');
    } else if (this.status === 'FAILED') {
      this.iconPath = new vscode.ThemeIcon('error');
    } else {
      this.iconPath = new vscode.ThemeIcon('circle-outline');
    }
  }

  contextValue = 'taskItem';
}
