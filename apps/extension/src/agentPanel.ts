import * as vscode from 'vscode';
import axios from 'axios';

export class AgentPanelProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'telecode-agent';
  private _view?: vscode.WebviewView;

  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    context: vscode.WebviewViewResolveContext,
    token: vscode.CancellationToken,
  ): void | Thenable<void> {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

    // Handle messages sent from the Webview (e.g. steering input)
    webviewView.webview.onDidReceiveMessage(async (message) => {
      switch (message.command) {
        case 'steer':
          await this._handleSteerInput(message.text);
          break;
      }
    });
  }

  /**
   * Posts a progress stream event straight to the Webview.
   */
  public handleProgressEvent(event: any): void {
    if (this._view) {
      this._view.show(true); // Focus the sidebar view automatically
      this._view.webview.postMessage({ type: 'progress', event });
    }
  }

  private async _handleSteerInput(text: string): Promise<void> {
    // 1. Get auth token
    const token = await vscode.commands.executeCommand<string | undefined>('telecode.getToken');
    if (!token) {
      vscode.window.showErrorMessage('❌ You must be connected to Telecode to send corrections.');
      return;
    }

    // 2. We also need the current active task ID.
    // Let's retrieve the latest task for this user from the server
    const apiUrl = vscode.workspace.getConfiguration('telecode').get<string>('apiUrl') || 'http://localhost:3005/api';
    try {
      const tasksResp = await axios.get(`${apiUrl}/bot/tasks/token/${token}`);
      const activeTasks = tasksResp.data.tasks || [];
      const activeTask = activeTasks.find((t: any) => t.status === 'IN_PROGRESS');
      
      if (!activeTask) {
        vscode.window.showWarningMessage('⚠️ No active running task found to steer.');
        return;
      }

      // 3. Post steer correction
      await axios.post(`${apiUrl}/bot/tasks/${activeTask.id}/steer`, {
        userId: activeTask.userId,
        text,
      });

      vscode.window.showInformationMessage(`💡 Steering correction sent: "${text}"`);
      
      if (this._view) {
        this._view.webview.postMessage({ 
          type: 'steer_acknowledged', 
          text 
        });
      }
    } catch (e: any) {
      vscode.window.showErrorMessage(`❌ Failed to send steering instruction: ${e.message}`);
    }
  }

  private _getHtmlForWebview(webview: vscode.Webview): string {
    return `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Autonomous Agent Panel</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
        <style>
          :root {
            --bg-color: #0f131a;
            --card-bg: rgba(255, 255, 255, 0.03);
            --card-border: rgba(255, 255, 255, 0.07);
            --accent-glow: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
            --accent-glow-failed: linear-gradient(135deg, #f857a6 0%, #ff5858 100%);
            --text-main: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-dim: #4b5563;
          }

          body {
            margin: 0;
            padding: 16px;
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            display: flex;
            flex-direction: column;
            height: 100vh;
            box-sizing: border-box;
            overflow-x: hidden;
          }

          .header {
            margin-bottom: 20px;
          }

          .title {
            font-size: 20px;
            font-weight: 800;
            margin: 0 0 6px 0;
            background: linear-gradient(to right, #ffffff, #9ca3af);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
          }

          .goal-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 12px 14px;
            font-size: 14px;
            line-height: 1.5;
            color: var(--text-secondary);
            margin-bottom: 20px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(8px);
          }

          .goal-label {
            font-weight: 600;
            color: #38bdf8;
            margin-bottom: 4px;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
          }

          .steps-container {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 20px;
            padding-right: 4px;
          }

          .step-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 12px;
            display: flex;
            flex-direction: column;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            animation: slideIn 0.4s ease forwards;
          }

          .step-header {
            display: flex;
            align-items: center;
            gap: 10px;
          }

          .step-icon {
            font-size: 16px;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
          }

          .step-info {
            flex: 1;
          }

          .step-title {
            font-size: 13px;
            font-weight: 600;
          }

          .step-status {
            font-size: 10px;
            color: var(--text-secondary);
            margin-top: 2px;
          }

          .step-output-btn {
            background: none;
            border: none;
            color: #38bdf8;
            font-size: 11px;
            cursor: pointer;
            padding: 4px 0 0 0;
            text-align: left;
            font-family: inherit;
            outline: none;
          }

          .step-output {
            display: none;
            margin-top: 8px;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 8px;
            font-family: monospace;
            font-size: 11px;
            color: #a7f3d0;
            white-space: pre-wrap;
            max-height: 160px;
            overflow-y: auto;
          }

          /* Steer Input Console */
          .steer-console {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 12px;
            box-shadow: 0 -8px 32px rgba(0,0,0,0.4);
            backdrop-filter: blur(16px);
            margin-top: auto;
          }

          .steer-header {
            font-size: 12px;
            font-weight: 600;
            color: #38bdf8;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
          }

          .steer-input-wrapper {
            display: flex;
            gap: 8px;
          }

          .steer-textarea {
            flex: 1;
            height: 36px;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            color: var(--text-main);
            padding: 8px 12px;
            font-size: 13px;
            font-family: inherit;
            resize: none;
            outline: none;
            transition: border-color 0.2s;
          }

          .steer-textarea:focus {
            border-color: #38bdf8;
          }

          .steer-btn {
            background: var(--accent-glow);
            border: none;
            border-radius: 8px;
            color: #0f131a;
            font-weight: 600;
            padding: 0 16px;
            font-size: 13px;
            cursor: pointer;
            transition: opacity 0.2s;
            outline: none;
          }

          .steer-btn:hover {
            opacity: 0.9;
          }

          .steer-btn:active {
            opacity: 0.8;
          }

          .steer-history {
            font-size: 11px;
            color: #eab308;
            margin-top: 8px;
            font-style: italic;
          }

          @keyframes slideIn {
            from { transform: translateY(10px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
          }

          /* Scrollbar styling */
          ::-webkit-scrollbar {
            width: 4px;
          }
          ::-webkit-scrollbar-track {
            background: rgba(0,0,0,0.1);
          }
          ::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.1);
            border-radius: 2px;
          }
        </style>
      </head>
      <body>
        <div class="header">
          <h2 class="title">Telecode Agent</h2>
        </div>

        <div id="goal-container" style="display: none;">
          <div class="goal-card">
            <div class="goal-label">Current Goal</div>
            <div id="goal-text"></div>
          </div>
        </div>

        <div class="steps-container" id="steps">
          <div style="text-align: center; margin-top: 40px; color: var(--text-dim); font-size: 14px;">
            🤖 Awaiting task execution stream...
          </div>
        </div>

        <div class="steer-console" id="steer-panel" style="display: none;">
          <div class="steer-header">
            <span>💡</span> Interactive Steering Console
          </div>
          <div class="steer-input-wrapper">
            <textarea class="steer-textarea" id="steer-input" placeholder="Type a correction mid-task..."></textarea>
            <button class="steer-btn" id="steer-send-btn">Send</button>
          </div>
          <div id="steer-notif" class="steer-history" style="display: none;"></div>
        </div>

        <script>
          const vscode = acquireVsCodeApi();
          const stepsContainer = document.getElementById('steps');
          const goalContainer = document.getElementById('goal-container');
          const goalText = document.getElementById('goal-text');
          const steerPanel = document.getElementById('steer-panel');
          const steerInput = document.getElementById('steer-input');
          const steerSendBtn = document.getElementById('steer-send-btn');
          const steerNotif = document.getElementById('steer-notif');

          const stepElements = {};

          window.addEventListener('message', event => {
            const message = event.data;
            if (message.type === 'progress') {
              const { step, label, status, output } = message.event;
              
              if (step === 0) {
                // Task started! Clear container
                stepsContainer.innerHTML = '';
                goalContainer.style.display = 'block';
                goalText.innerText = message.event.label.replace('Starting autonomous loop for: ', '') || 'Active task';
                steerPanel.style.display = 'block';
                steerNotif.style.display = 'none';
                return;
              }

              if (step === 999) {
                // Completed run!
                const finishDiv = document.createElement('div');
                finishDiv.style.textAlign = 'center';
                finishDiv.style.margin = '20px 0';
                finishDiv.style.fontSize = '13px';
                finishDiv.style.color = status === 'COMPLETED' ? '#34d399' : '#f87171';
                finishDiv.innerText = status === 'COMPLETED' ? '✅ Run completed successfully!' : '❌ Run failed.';
                stepsContainer.appendChild(finishDiv);
                steerPanel.style.display = 'none';
                return;
              }

              // Update or append step
              if (stepElements[step]) {
                updateStepElement(step, label, status, output);
              } else {
                createStepElement(step, label, status, output);
              }
            } else if (message.type === 'steer_acknowledged') {
              steerNotif.style.display = 'block';
              steerNotif.innerText = '💡 Active steering instruction: "' + message.text + '"';
            }
          });

          steerSendBtn.addEventListener('click', () => {
            const text = steerInput.value.trim();
            if (text) {
              vscode.postMessage({ command: 'steer', text });
              steerInput.value = '';
            }
          });

          function createStepElement(stepNum, label, status, output) {
            const card = document.createElement('div');
            card.className = 'step-card';
            card.id = 'step-' + stepNum;

            const icon = getStatusIcon(status);
            
            card.innerHTML = \`
              <div class="step-header">
                <div class="step-icon" id="icon-\${stepNum}">\${icon}</div>
                <div class="step-info">
                  <div class="step-title">Step \${stepNum}: <span id="label-&num;\${stepNum}">\${label}</span></div>
                  <div class="step-status" id="status-\${stepNum}">\${status}</div>
                </div>
              </div>
              <button class="step-output-btn" id="btn-\${stepNum}" style="display: none;">Show execution logs</button>
              <div class="step-output" id="output-\${stepNum}"></div>
            \`;

            stepsContainer.appendChild(card);
            stepsContainer.scrollTop = stepsContainer.scrollHeight;
            stepElements[stepNum] = card;

            if (output) {
              updateOutput(stepNum, output);
            }
          }

          function updateStepElement(stepNum, label, status, output) {
            const labelEl = document.getElementById('label-&num;' + stepNum) || document.getElementById('step-' + stepNum).querySelector('.step-title span');
            const statusEl = document.getElementById('status-' + stepNum);
            const iconEl = document.getElementById('icon-' + stepNum);

            if (labelEl) labelEl.innerText = label;
            if (statusEl) statusEl.innerText = status;
            if (iconEl) iconEl.innerHTML = getStatusIcon(status);

            if (output) {
              updateOutput(stepNum, output);
            }
          }

          function updateOutput(stepNum, output) {
            const btn = document.getElementById('btn-' + stepNum);
            const outputEl = document.getElementById('output-' + stepNum);

            if (btn && outputEl) {
              btn.style.display = 'block';
              outputEl.innerText = output;

              btn.onclick = () => {
                if (outputEl.style.display === 'block') {
                  outputEl.style.display = 'none';
                  btn.innerText = 'Show execution logs';
                } else {
                  outputEl.style.display = 'block';
                  btn.innerText = 'Hide execution logs';
                }
              };
            }
          }

          function getStatusIcon(status) {
            switch (status) {
              case 'COMPLETED': return '✅';
              case 'FAILED': return '❌';
              default: return '⏳';
            }
          }
        </script>
      </body>
      </html>
    `;
  }
}
