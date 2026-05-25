import * as http from 'http';
import * as https from 'https';
import * as vscode from 'vscode';

export class TelecodeSseClient {
  private outputChannel: vscode.OutputChannel;
  private req: any = null;

  private progressListener: ((event: any) => void) | null = null;

  constructor() {
    this.outputChannel = vscode.window.createOutputChannel('Telecode Live Progress');
  }

  onProgress(listener: (event: any) => void): void {
    this.progressListener = listener;
  }

  connect(apiUrl: string, token: string): void {
    this.disconnect();
    
    const streamUrl = `${apiUrl}/bot/progress/stream/${token}`;
    this.outputChannel.appendLine(`[SSE] Connecting to Telecode live progress stream...`);
    
    const client = streamUrl.startsWith('https') ? https : http;
    
    try {
      this.req = client.get(streamUrl, (res) => {
        this.outputChannel.appendLine(`[SSE] Connection established.`);
        this.outputChannel.show(true); // Focus the live progress panel immediately
        
        let buffer = '';
        
        res.on('data', (chunk) => {
          buffer += chunk.toString();
          
          const lines = buffer.split('\n');
          // Keep the last incomplete block in the buffer
          buffer = lines.pop() || '';
          
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data:')) {
              try {
                const dataStr = trimmed.substring(5).trim();
                if (dataStr) {
                  const event = JSON.parse(dataStr);
                  this.handleProgressEvent(event);
                }
              } catch (err) {
                // Ignore incomplete JSON chunks
              }
            }
          }
        });
        
        res.on('end', () => {
          this.outputChannel.appendLine(`[SSE] Progress stream closed by server.`);
        });
      });
      
      this.req.on('error', (err: any) => {
        this.outputChannel.appendLine(`[SSE] Connection error: ${err.message}`);
      });
    } catch (e: any) {
      this.outputChannel.appendLine(`[SSE] Failed to establish connection: ${e.message}`);
    }
  }

  disconnect(): void {
    if (this.req) {
      this.req.destroy();
      this.req = null;
    }
  }

  private handleProgressEvent(event: any): void {
    if (this.progressListener) {
      try {
        this.progressListener(event);
      } catch (e) {
        console.error('Error forwarding progress event:', e);
      }
    }
    const { step, label, status, output } = event;
    
    let icon = '⏳';
    if (status === 'COMPLETED') icon = '✅';
    if (status === 'FAILED') icon = '❌';
    
    if (step === 0) {
      this.outputChannel.appendLine(`\n🤖 Telecode Autonomous Run: Started`);
      this.outputChannel.appendLine(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    } else if (step === 999) {
      this.outputChannel.appendLine(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
      this.outputChannel.appendLine(`${icon} Concluded: ${label}\n`);
    } else {
      this.outputChannel.appendLine(`${icon} [Step ${step}] ${label} (${status})`);
      if (output && status === 'COMPLETED') {
        const indented = output
          .split('\n')
          .map((line: string) => `   | ${line}`)
          .join('\n');
        this.outputChannel.appendLine(indented);
      }
    }
  }
}
export const sseClient = new TelecodeSseClient();
