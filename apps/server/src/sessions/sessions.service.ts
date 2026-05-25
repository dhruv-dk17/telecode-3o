import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

export interface SessionMemoryEntry {
  mode: string;
  prompt: string;
  result_summary: string;
  branch?: string;
  timestamp: string;
}

export interface SessionContext {
  tasks: SessionMemoryEntry[];
}

const MAX_SESSION_ENTRIES = 10; // Keep last 10 tasks in memory

@Injectable()
export class SessionsService {
  constructor(private prisma: PrismaService) {}

  /**
   * Returns the current session context as a formatted string for AI injection.
   * Returns null if no session exists or session is empty.
   */
  async getContextString(userId: string): Promise<string | null> {
    const session = await this.prisma.session.findFirst({
      where: { userId },
      orderBy: { updatedAt: 'desc' },
    });

    if (!session) return null;

    let ctx: SessionContext;
    try {
      ctx = JSON.parse(session.context) as SessionContext;
    } catch {
      return null;
    }

    if (!ctx.tasks || ctx.tasks.length === 0) return null;

    // Format for AI: compact numbered list of recent tasks
    const lines = ctx.tasks
      .slice(-MAX_SESSION_ENTRIES)
      .map((t, i) => {
        const parts = [
          `${i + 1}. [${t.mode}] ${t.prompt.substring(0, 80)}${t.prompt.length > 80 ? '…' : ''}`,
          `   Result: ${t.result_summary}`,
        ];
        if (t.branch) parts.push(`   Branch: ${t.branch}`);
        parts.push(`   Time: ${t.timestamp}`);
        return parts.join('\n');
      })
      .join('\n\n');

    return lines;
  }

  /**
   * Appends a completed task to the user's session memory.
   * Creates the session record if it doesn't exist yet.
   */
  async appendEntry(userId: string, entry: SessionMemoryEntry): Promise<void> {
    const existing = await this.prisma.session.findFirst({
      where: { userId },
      orderBy: { updatedAt: 'desc' },
    });

    let ctx: SessionContext = { tasks: [] };

    if (existing) {
      try {
        ctx = JSON.parse(existing.context) as SessionContext;
      } catch {
        ctx = { tasks: [] };
      }

      // Trim to keep only last N entries
      if (ctx.tasks.length >= MAX_SESSION_ENTRIES) {
        ctx.tasks = ctx.tasks.slice(-MAX_SESSION_ENTRIES + 1);
      }

      ctx.tasks.push(entry);

      await this.prisma.session.update({
        where: { id: existing.id },
        data: { context: JSON.stringify(ctx) },
      });
    } else {
      ctx.tasks.push(entry);

      await this.prisma.session.create({
        data: {
          userId,
          context: JSON.stringify(ctx),
        },
      });
    }
  }
}
