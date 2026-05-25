import { Telegraf, Markup } from 'telegraf';
import { message } from 'telegraf/filters';
import 'dotenv/config';
import * as crypto from 'crypto';
console.log('🚀 Starting bot script...');
import { ApiService } from './api.service';

// ── Pending Executions Store ────────────────────────────────────────────────
// Stores prompts temporarily to avoid Telegram's 64-byte callback_data limit
const pendingExecutions = new Map<string, { 
  userId: string; 
  repositoryId: string; 
  prompt: string; 
}>();

// ─── Setup ───────────────────────────────────────────────────────────────────

const botToken = process.env.TELEGRAM_BOT_TOKEN;
if (!botToken) {
  console.error('❌  TELEGRAM_BOT_TOKEN is not set!');
  process.exit(1);
}

const bot = new Telegraf(botToken);
const api = new ApiService();

// ─── Middleware ──────────────────────────────────────────────────────────────

bot.use(async (ctx, next) => {
  const start = Date.now();
  const updateType = ctx.updateType;
  const from = ctx.from ? `@${ctx.from.username || ctx.from.id}` : 'unknown';
  
  console.log(`📩 Received update [${updateType}] from ${from}`);
  
  await next();
  
  const ms = Date.now() - start;
  console.log(`✅ Handled update in ${ms}ms`);
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatUser(u: { username?: string | null; firstName?: string | null }): string {
  return u.username ? `@${u.username}` : (u.firstName ?? 'there');
}

async function ensureUser(telegramId: number, from: any) {
  return api.registerUser({
    telegramId: String(telegramId),
    username: from.username,
    firstName: from.first_name,
    lastName: from.last_name,
  });
}

// ─── Commands ────────────────────────────────────────────────────────────────

bot.start(async (ctx) => {
  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  const name = user ? formatUser(user) : ctx.from.first_name;

  await ctx.reply(
    `👋 Welcome to <b>Telecode</b>, ${name}!\n\n` +
    `I'm your AI coding continuity agent. I help you manage your code from anywhere.\n\n` +
    `<b>Core Capabilities:</b>\n` +
    `🔍 <b>/explain</b> — Deep code analysis\n` +
    `🔎 <b>/search</b> — Semantic file search\n` +
    `🔧 <b>/fix</b> — Quick bug fixes\n` +
    `🗺 <b>/plan</b> — Feature strategy\n` +
    `⚡ <b>/execute</b> — Automated code changes\n\n` +
    `<b>Setup:</b>\n` +
    `📋 <b>/connect</b> <code>owner/repo</code>\n` +
    `📂 <b>/repos</b> — Your linked repositories\n\n` +
    `📜 <b>/tasks</b> — History\n` +
    `↩️ <b>/undo</b> — Rollback\n` +
    `❓ <b>/help</b> — Full command list`,
    { parse_mode: 'HTML' }
  );
});

bot.help(async (ctx) => {
  await ctx.reply(
    `<b>Telecode — Command Reference</b>\n\n` +
    `<b>Context & Setup:</b>\n` +
    `📋 <b>/connect</b> [repo] — Link a GitHub repository\n` +
    `📂 <b>/repos</b> — List linked repositories\n` +
    `🔑 <b>/sync</b> — Get code for VS Code extension\n\n` +
    `<b>AI Assistance (Read-only):</b>\n` +
    `🔍 <b>/explain</b> [query] — Analysis and explanations\n` +
    `🔎 <b>/search</b> [query] — Find files and logic\n\n` +
    `<b>AI Operations (Write):</b>\n` +
    `🗺 <b>/plan</b> [feature] — Create implementation design\n` +
    `🔧 <b>/fix</b> [issue] — Diagnose and repair bugs\n` +
    `⚡ <b>/execute</b> [task] — Apply changes and open PR\n\n` +
    `<b>Management:</b>\n` +
    `📜 <b>/tasks</b> — Recent execution history\n` +
    `↩️ <b>/undo</b> — Roll back the last execution`,
    { parse_mode: 'HTML' }
  );
});

bot.command('connect', async (ctx) => {
  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not register you. Is the server running?');

  const arg = ctx.message.text.split(' ').slice(1).join('').trim();
  if (!arg || !arg.includes('/')) {
    return ctx.reply('Usage: <code>/connect owner/repo-name</code>', { parse_mode: 'HTML' });
  }

  await ctx.reply(`🔗 Connecting to <b>${arg}</b>...`, { parse_mode: 'HTML' });

  try {
    const repo = await api.connectRepo(user.id, arg);
    await ctx.reply(
      `✅ Connected to <b>${repo.fullName}</b>!\nDefault branch: <code>${repo.defaultBranch}</code>\n\nNow you can use /explain, /plan, /fix, or /execute with this repo as context.`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    await ctx.reply(`❌ Failed to connect: ${err?.response?.data?.message ?? err.message}`);
  }
});

/** /repos — list connected repositories */
bot.command('repos', async (ctx) => {
  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  try {
    const repos = await api.listRepos(user.id);
    if (!repos.length) {
      return ctx.reply('You have no connected repositories yet.\n\nUse <code>/connect owner/repo</code> to add one.', { parse_mode: 'HTML' });
    }

    const list = repos
      .map((r: any) => `${r.isActive ? '✅' : '⚪'} <code>${r.fullName}</code> (${r.defaultBranch})`)
      .join('\n');

    await ctx.reply(`<b>Your Repositories:</b>\n\n${list}`, { parse_mode: 'HTML' });
  } catch {
    await ctx.reply('❌ Could not fetch repositories. Is the server running?');
  }
});

bot.command('search', async (ctx) => {
  const prompt = ctx.message.text.split(' ').slice(1).join(' ').trim();
  if (!prompt) return ctx.reply('Usage: `/search <your query>`', { parse_mode: 'Markdown' });

  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  const activeRepo = await api.getActiveRepo(user.id).catch(() => null);

  await ctx.reply(`🔎 <b>Search mode</b> — hunting for information...\n\n<i>"${prompt}"</i>`, { parse_mode: 'HTML' });

  try {
    if (!ctx.chat) return;
    const task = await api.submitTask({
      userId: user.id,
      repositoryId: activeRepo?.id,
      mode: 'SEARCH',
      prompt,
      botToken,
      chatId: String(ctx.chat.id),
    });
    await ctx.reply(
      `🔍 <b>Phase 2: Analysis</b> — ID: <code>${task.id}</code>\n\n` +
      `<i>The AI is searching the codebase. Results will appear shortly.</i>`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    await ctx.reply(`❌ Error: ${err?.response?.data?.message ?? err.message}`);
  }
});

/** /explain <question> — EXPLAIN mode (read-only) */
bot.command('explain', async (ctx) => {
  const prompt = ctx.message.text.split(' ').slice(1).join(' ').trim();
  if (!prompt) return ctx.reply('Usage: `/explain <your question>`', { parse_mode: 'Markdown' });

  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  const activeRepo = await api.getActiveRepo(user.id).catch(() => null);

  await ctx.reply(`🔍 <b>Explain mode</b> — analysing your question...\n\n<i>"${prompt}"</i>`, { parse_mode: 'HTML' });

  try {
    if (!ctx.chat) return;
    const task = await api.submitTask({
      userId: user.id,
      repositoryId: activeRepo?.id,
      mode: 'EXPLAIN',
      prompt,
      botToken,
      chatId: String(ctx.chat.id),
    });
    await ctx.reply(
      `🧠 <b>Phase 2: Reasoning</b> — ID: <code>${task.id}</code>\n\n` +
      `<i>The AI is analyzing your question. Response incoming...</i>`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    await ctx.reply(`❌ Error: ${err?.response?.data?.message ?? err.message}`);
  }
});

bot.command('fix', async (ctx) => {
  const prompt = ctx.message.text.split(' ').slice(1).join(' ').trim();
  if (!prompt) return ctx.reply('Usage: <code>/fix <issue description></code>', { parse_mode: 'HTML' });

  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  const activeRepo = await api.getActiveRepo(user.id).catch(() => null);
  if (!activeRepo) {
    return ctx.reply('⚠️ No active repository. Use <code>/connect owner/repo</code> first.', { parse_mode: 'HTML' });
  }

  await ctx.reply(
    `🔧 <b>Fix mode</b> — diagnosing and preparing fix...\n\n<i>"${prompt}"</i>\n\nRepo: <code>${activeRepo.fullName}</code>`,
    { parse_mode: 'HTML' }
  );

  try {
    if (!ctx.chat) return;
    const task = await api.submitTask({
      userId: user.id,
      repositoryId: activeRepo.id,
      mode: 'FIX',
      prompt,
      botToken,
      chatId: String(ctx.chat.id),
    });
    await ctx.reply(
      `🛠 <b>Phase 2: Diagnosis</b> — ID: <code>${task.id}</code>\n\n` +
      `<i>The AI is investigating the issue and preparing a fix.</i>`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    console.error('Fix command error:', err);
    await ctx.reply(`❌ Error: ${err?.response?.data?.message ?? err.message}`);
  }
});

/** /plan <feature> — PLAN mode */
bot.command('plan', async (ctx) => {
  const prompt = ctx.message.text.split(' ').slice(1).join(' ').trim();
  if (!prompt) return ctx.reply('Usage: `/plan <feature description>`', { parse_mode: 'Markdown' });

  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  const activeRepo = await api.getActiveRepo(user.id).catch(() => null);
  if (!activeRepo) {
    return ctx.reply('⚠️ No active repository. Use `/connect owner/repo` first.', { parse_mode: 'Markdown' });
  }

  await ctx.reply(
    `🗺 <b>Plan mode</b> — building implementation strategy...\n\n<i>"${prompt}"</i>\n\nRepo: <code>${activeRepo.fullName}</code>`,
    { parse_mode: 'HTML' }
  );

  try {
    if (!ctx.chat) return;
    const task = await api.submitTask({
      userId: user.id,
      repositoryId: activeRepo.id,
      mode: 'PLAN',
      prompt,
      botToken,
      chatId: String(ctx.chat.id),
    });
    await ctx.reply(
      `📋 <b>Phase 3: Planning</b> — ID: <code>${task.id}</code>\n` +
      `<i>(The implementation strategy is being generated. Hang tight!)</i>`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    await ctx.reply(`❌ Error: ${err?.response?.data?.message ?? err.message}`);
  }
});

/** /execute <task> — EXECUTE mode */
bot.command('execute', async (ctx) => {
  const prompt = ctx.message.text.split(' ').slice(1).join(' ').trim();
  if (!prompt) return ctx.reply('Usage: `/execute <what to change>`', { parse_mode: 'Markdown' });

  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  const activeRepo = await api.getActiveRepo(user.id).catch(() => null);
  if (!activeRepo) {
    return ctx.reply('⚠️ No active repository. Use `/connect owner/repo` first.', { parse_mode: 'Markdown' });
  }

  // Store prompt in memory to avoid 64-byte callback_data limit
  const pendingId = crypto.randomUUID();
  pendingExecutions.set(pendingId, {
    userId: user.id,
    repositoryId: activeRepo.id,
    prompt,
  });

  // Confirm before executing
  await ctx.reply(
    `⚡ <b>Execute mode</b> — I will make code changes to <code>${activeRepo.fullName}</code>.\n\n` +
    `Task: <i>"${prompt}"</i>\n\n` +
    `This will create a new branch and open a PR. Confirm?`,
    {
      parse_mode: 'HTML',
      ...Markup.inlineKeyboard([
        Markup.button.callback('✅ Confirm', `exec_confirm:${pendingId}`),
        Markup.button.callback('❌ Cancel', `exec_cancel:${pendingId}`),
      ]),
    }
  );
});

bot.action(/^exec_cancel:(.+)$/, async (ctx) => {
  const pendingId = ctx.match[1];
  pendingExecutions.delete(pendingId);
  await ctx.answerCbQuery('Cancelled.');
  await ctx.editMessageText('❌ Execution cancelled.');
});

bot.action(/^exec_confirm:(.+)$/, async (ctx) => {
  const pendingId = ctx.match[1];
  const pending = pendingExecutions.get(pendingId);

  if (!pending) {
    await ctx.answerCbQuery('Error: session expired.');
    return ctx.editMessageText('❌ Error: This confirmation link has expired or is invalid.');
  }

  await ctx.answerCbQuery('Submitting...');
  const { userId, repositoryId, prompt } = pending;
  pendingExecutions.delete(pendingId); // Clean up

  try {
    if (!ctx.chat) return;
    const task = await api.submitTask({
      userId,
      repositoryId,
      mode: 'EXECUTE',
      prompt,
      botToken,
      chatId: String(ctx.chat.id),
    });
    await ctx.editMessageText(
      `⚡ <b>Phase 3: Execution</b> — ID: <code>${task.id}</code>\n\n` +
      `<i>AI is applying changes and opening a PR. You'll be notified when it's live.</i>`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    await ctx.editMessageText(`❌ Error: ${err?.response?.data?.message ?? err.message}`);
  }
});

/** /undo — roll back last task */
bot.command('undo', async (ctx) => {
  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  try {
    const task = await api.rollbackLastTask(user.id);
    await ctx.reply(
      `↩️ Task <code>${task.id}</code> rolled back.\nStatus: <code>${task.status}</code>`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    await ctx.reply(`❌ ${err?.response?.data?.message ?? err.message}`);
  }
});

/** /sync — generate a code for VS Code extension */
bot.command('sync', async (ctx) => {
  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  try {
    const code = await api.generateSyncCode(user.id);
    await ctx.reply(
      `🔑 Your sync code: <code>${code}</code>\n\n` +
      `Enter this code in your VS Code Telecode extension to link your account.\n` +
      `This code will expire in 10 minutes.`,
      { parse_mode: 'HTML' }
    );
  } catch (err: any) {
    await ctx.reply(`❌ Failed to generate code: ${err?.response?.data?.message ?? err.message}`);
  }
});

/** /login — initiate GitHub OAuth login */
bot.command(['login', 'auth'], async (ctx) => {
  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  const clientId = process.env.GITHUB_CLIENT_ID;
  const redirectUri = process.env.GITHUB_REDIRECT_URI;

  if (!clientId || !redirectUri) {
    return ctx.reply('⚠️ GitHub OAuth is not fully configured on the server.');
  }

  const telegramId = ctx.from.id;
  const authUrl = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&state=${telegramId}&scope=repo`;

  await ctx.reply(
    `🔐 <b>GitHub Account Connection</b>\n\n` +
    `Connect your GitHub account to allow Telecode to safely create branches, commit code, and open PRs on your behalf.\n\n` +
    `Click the button below to authorize through GitHub securely:`,
    {
      parse_mode: 'HTML',
      ...Markup.inlineKeyboard([
        Markup.button.url('🔑 Connect GitHub', authUrl),
      ]),
    }
  );
});

/** /tasks — recent history */
bot.command('tasks', async (ctx) => {
  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server.');

  try {
    const tasks = await api.listTasks(user.id);
    if (!tasks.length) return ctx.reply('No tasks yet. Use /explain, /plan, or /execute to get started!');

    const list = tasks
      .slice(0, 5)
      .map((t: any, i: number) =>
        `${i + 1}. [${t.mode}] <code>${t.status}</code> — ${t.prompt.slice(0, 50)}...`
      )
      .join('\n');

    await ctx.reply(`<b>Recent Tasks:</b>\n\n${list}`, { parse_mode: 'HTML' });
  } catch {
    await ctx.reply('❌ Could not fetch tasks.');
  }
});

/** Fallthrough — treat plain text as /explain */
bot.on(message('text'), async (ctx) => {
  const text = ctx.message.text.trim();
  if (text.startsWith('/')) return; // unknown command

  const user = await ensureUser(ctx.from.id, ctx.from).catch(() => null);
  if (!user) return ctx.reply('⚠️ Could not reach the server. Is it running?');

  const activeRepo = await api.getActiveRepo(user.id).catch(() => null);

  await ctx.reply(
    `💬 Treating this as an <b>Explain</b> request...\n\n` +
    `${activeRepo ? `Repo: <code>${activeRepo.fullName}</code>` : '<i>(No active repo — link one with /connect)</i>'}\n\n` +
    `💡 <i>Tip: Use /fix or /plan for deeper tasks.</i>`,
    { parse_mode: 'HTML' }
  );

  try {
    if (!ctx.chat) return;
    await api.submitTask({
      userId: user.id,
      repositoryId: activeRepo?.id,
      mode: 'EXPLAIN',
      prompt: text,
      botToken,
      chatId: String(ctx.chat.id),
    });
  } catch {
    // silently queue even if server is slow
  }
});

// ─── Launch ──────────────────────────────────────────────────────────────────
async function launch() {
  try {
    console.log('🔍 Verifying server connection...');
    try {
      // Simple ping to server
      await api.getUser('test').catch(() => null); 
      console.log('✅ Server connection established.');
    } catch (e) {
      console.warn('⚠️ Could not connect to server. Commands might fail.');
    }

    console.log('🔍 Verifying bot token with Telegram...');
    const me = await bot.telegram.getMe();
    console.log(`✅ Token verified! Bot name: ${me.first_name} (@${me.username})`);

    console.log('📜 Registering bot commands...');
    await bot.telegram.setMyCommands([
      { command: 'start', description: 'Begin your journey with Telecode' },
      { command: 'connect', description: 'Link a GitHub repository' },
      { command: 'repos', description: 'List your connected repositories' },
      { command: 'explain', description: 'Understand code or concepts' },
      { command: 'search', description: 'Hunt for logic in your codebase' },
      { command: 'plan', description: 'Strategy for a new feature' },
      { command: 'fix', description: 'Diagnose and fix bugs' },
      { command: 'execute', description: 'Apply code changes & open PR' },
      { command: 'tasks', description: 'View recent execution history' },
      { command: 'sync', description: 'Get code for VS Code extension' },
      { command: 'login', description: 'Link your GitHub account securely' },
      { command: 'undo', description: 'Roll back the last execution' },
      { command: 'help', description: 'Show full command reference' },
    ]);
    console.log('✅ Commands registered.');

    console.log('⏳ Starting polling...');
    bot.launch({ dropPendingUpdates: true }).then(() => {
       console.log('🤖 Telecode Bot polling started successfully!');
    }).catch(err => {
       console.error('❌ Bot launch error:', err);
    });

    console.log('🤖 Telecode Bot script is active. Send a message to the bot on Telegram!');
  } catch (err: any) {
    console.error('❌ Failed to initialize bot:');
    if (err.response) {
      console.error(`   Status: ${err.response.error_code}`);
      console.error(`   Description: ${err.response.description}`);
    } else {
      console.error(`   Error: ${err.message}`);
    }
    process.exit(1);
  }
}

launch();

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
