import * as vscode from 'vscode';
import { AuthManager } from './auth';
import { TaskExplorerProvider } from './taskExplorer';
import { TelecodeApi } from './api';

// ── Auto-sync polling ──────────────────────────────────────────────────────
// Polls the server every 30 seconds when authenticated.
// When a new COMPLETED task is detected, shows a VS Code notification
// with action buttons to view the PR or pull the branch.

const POLL_INTERVAL_MS = 30_000;
const LAST_SEEN_TASK_KEY = 'telecode_last_seen_task_id';

function startAutoSync(
  context: vscode.ExtensionContext,
  auth: AuthManager,
  api: TelecodeApi,
  explorer: TaskExplorerProvider,
): vscode.Disposable {
  const interval = setInterval(async () => {
    const token = await auth.getToken();
    if (!token) return;

    const task = await api.getLatestCompletedTask(token);
    if (!task) return;

    const lastSeenId = context.globalState.get<string>(LAST_SEEN_TASK_KEY);

    // Only notify if this is a task we haven't seen before
    if (task.id === lastSeenId) return;

    // Persist so we don't re-notify on the next poll
    await context.globalState.update(LAST_SEEN_TASK_KEY, task.id);

    // Refresh the sidebar
    explorer.refresh();

    // Build a friendly summary
    const modeName = task.mode?.toLowerCase() ?? 'task';
    const branch = task.branchName ? `telecode/${task.branchName.split('/').pop()}` : null;
    const prUrl: string | undefined = task.prUrl;

    const message = branch
      ? `🤖 Telecode: New AI changes ready on \`${branch}\``
      : `🤖 Telecode: ${modeName} task completed`;

    // Show notification with contextual action buttons
    const actions: string[] = [];
    if (prUrl) actions.push('View Pull Request');
    if (branch) actions.push('Checkout Branch');

    const selected = await vscode.window.showInformationMessage(message, ...actions);

    if (selected === 'View Pull Request' && prUrl) {
      vscode.env.openExternal(vscode.Uri.parse(prUrl));
    }

    if (selected === 'Checkout Branch' && branch) {
      const terminal = vscode.window.createTerminal({ name: 'Telecode Sync' });
      terminal.show();
      terminal.sendText(`git fetch origin && git checkout ${task.branchName}`);
    }
  }, POLL_INTERVAL_MS);

  // Return a disposable so VS Code can clean up on deactivate
  return new vscode.Disposable(() => clearInterval(interval));
}


// ── Extension entry point ─────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
  console.log('Telecode extension activated');

  const auth = new AuthManager(context);
  const api = new TelecodeApi();
  const taskExplorerProvider = new TaskExplorerProvider(auth);

  vscode.window.registerTreeDataProvider('telecode-tasks', taskExplorerProvider);

  // ── Commands ─────────────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('telecode.connect', async () => {
      const success = await auth.connect();
      if (success) {
        taskExplorerProvider.refresh();
        // Clear last seen so we don't skip the first completed task
        await context.globalState.update(LAST_SEEN_TASK_KEY, undefined);
      }
    }),

    vscode.commands.registerCommand('telecode.disconnect', async () => {
      await auth.disconnect();
      taskExplorerProvider.refresh();
    }),

    vscode.commands.registerCommand('telecode.refreshTasks', () => {
      taskExplorerProvider.refresh();
    }),

    vscode.commands.registerCommand('telecode.viewTask', (task: any) => {
      const info = [
        `Mode: ${task.mode}`,
        `Status: ${task.status}`,
        `Prompt: ${task.prompt}`,
        task.branchName ? `Branch: ${task.branchName}` : null,
      ].filter(Boolean).join('\n');

      vscode.window.showInformationMessage(`Task Details:\n${info}`);
      if (task.prUrl) {
        vscode.env.openExternal(vscode.Uri.parse(task.prUrl));
      }
    }),
  );

  // ── Auto-sync: start polling if already authenticated ────────────────────
  auth.isAuthenticated().then(isAuth => {
    if (isAuth) {
      taskExplorerProvider.refresh();
      const syncDisposable = startAutoSync(context, auth, api, taskExplorerProvider);
      context.subscriptions.push(syncDisposable);
    }
  });
}

export function deactivate() {}
