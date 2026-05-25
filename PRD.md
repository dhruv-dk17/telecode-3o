# Telecode — Telegram-Based AI Coding Continuity Platform
## Product Requirements Document (PRD) v1.0

**Author:** David / Antigravity AI  
**Date:** May 2026  
**Status:** Draft / Review  

---

## 1. Executive Summary

### Product Vision
**Telecode** is a Telegram-first AI coding continuity platform designed for developers, indie hackers, and startup founders. It enables "vibe coding"—the ability to continue software development from anywhere using natural language.

By bridging the gap between desktop IDEs and mobile accessibility, Telecode allows users to capture momentum instantly. It is not a replacement for Cursor or VS Code, but an **ambient command layer** that synchronizes repository-aware AI agents with local development environments.

### Core Value Proposition
> “Capture coding momentum instantly from mobile without needing your laptop.”

---

## 2. Problem Statement

### The Gap in Development Flow
Developers often experience bursts of inspiration or identify critical bugs while away from their primary workstation. Current mobile coding solutions (GitHub Mobile, mobile IDEs, remote desktops) suffer from high friction, poor UX, or lack of repository context.

**The Pain Point:** Loss of development flow. Ideas are forgotten or disconnected from the codebase, leading to stalled momentum.

---

## 3. Product Positioning

| **What Telecode IS** | **What Telecode IS NOT** |
| :--- | :--- |
| AI coding continuity platform | Full mobile IDE |
| Telegram-native coding agent | GitHub clone |
| Async software development system | Remote desktop application |
| Repo-aware AI engineering assistant | General-purpose AI assistant |

---

## 4. Target Users
1.  **Indie Hackers:** High-frequency ideators building side projects.
2.  **Startup Founders:** Semi-technical users managing rapid iterations.
3.  **Vibe Coders:** Developers who leverage AI for high-level architectural changes.
4.  **Solo Developers:** Users seeking to accelerate development during "off-laptop" hours.

---

## 5. System Architecture & Components

### 5.1 High-Level Flow
`Telegram Bot` ➔ `API Gateway` ➔ `AI Orchestration Layer` ➔ `Repository Workspace Engine` ➔ `GitHub` ➔ `VS Code Extension Sync`

### 5.2 Core Components
*   **Telegram Interface Layer:** Handles natural language input (text/voice), displays diffs, and delivers status notifications.
*   **AI Agent Layer:** Powered by models like Claude (strongest for repo-aware edits). Responsible for mapping architecture, generating patches, and creating commits.
*   **Repository Workspace Engine:** Uses isolated Docker containers to clone repos, run validations, and perform edits without risking production stability.
*   **GitHub Integration:** Manages OAuth, branch creation (prefix: `feature/ai-task-xxxx`), and PR management.
*   **VS Code Extension:** The "continuity bridge" that detects remote AI commits and restores session context when the user returns to their laptop.

---

## 6. Operational Modes

To ensure trust and safety, Telecode operates in four distinct modes:

1.  **Explain Mode (Read-only):** Locates files, summarizes architecture, and answers technical questions without modifying code.
2.  **Plan Mode (Strategic):** Generates implementation strategies and identifies risks without execution.
3.  **Execute Mode (Actionable):** Modifies files, creates branches/commits, and runs validations. **Requires explicit approval for high-risk changes.**
4.  **Autonomous Mode (Future):** Long-running tasks with minimal supervision (multi-step workflows).

---

## 7. Core Features (MVP)

### 7.1 GitHub & Repo Management
*   Secure OAuth login.
*   Repository browsing and connection.
*   Branch-based execution (never edits `main` directly).

### 7.2 AI Interaction
*   Natural language prompts for features, bugs, and refactors.
*   Session memory: The agent remembers repo structure and previous tasks.
*   Diff previews: Lightweight summaries of changes before merging.

### 7.3 Trust & Safety
*   **Confidence Scoring:** AI estimates the risk and confidence level of proposed changes.
*   **Undo System:** Simple `/undo-last-task` command to revert state.
*   **Sandboxed Execution:** All validation and editing occur in ephemeral environments.

---

## 8. Technical Stack (Recommended)
*   **Interface:** Telegram Bot API (Telegraf.js).
*   **Backend:** Node.js (NestJS) + Python (LangGraph for AI orchestration).
*   **Database:** PostgreSQL (Supabase) + pgvector for memory/embeddings.
*   **Infrastructure:** Docker containers on Railway, Fly.io, or AWS.
*   **Preview Deployments:** Vercel/Netlify integration for instant UI feedback.

---

## 9. Success Metrics
*   **Primary:** Daily Active Users (DAU), tasks completed, and "Desktop Continuation Rate" (how often mobile tasks are resumed/finalized on desktop).
*   **Health:** Task success percentage, rollback frequency, and merge conflict rate.

---

## 10. Product Review & Analysis (Antigravity Insights)

### 10.1 Strategic Strengths
*   **Messaging-Native:** Telegram's lightweight nature is superior to a dedicated app for "quick bursts" of coding activity.
*   **Continuity over Coding:** Positioning the product as a "continuity bridge" rather than a "mobile IDE" avoids the stigma of poor mobile coding experiences.
*   **Context Management:** The emphasis on vector memory and repo indexing is critical. Without this, token costs and hallucinations would kill the product.

### 10.2 Technical Risks & Recommendations
*   **The "Cold Start" Problem:** Cloning a large repo into a container for a tiny edit might be slow. 
    *   *Recommendation:* Maintain "Warm" cached volumes for active user repositories.
*   **Context Window Limits:** Large projects exceed context windows. 
    *   *Recommendation:* Implement a robust "Map-Reduce" approach for repo scanning, creating a permanent `ARCHITECTURE.md` summary that the AI always reads.
*   **Validation Pipeline:** Relying solely on AI to write code is dangerous.
    *   *Recommendation:* Enforce strict `npm test` or `go test` cycles within the sandbox before the user ever sees the "task completed" notification.

### 10.3 Competitive Differentiator
The **VS Code Extension Sync** is the "Killer Feature." Without it, Telecode is just a bot. With it, it becomes an integrated part of a professional developer's life.

---

## 11. Security Model (Critical)
*   **Branch Isolation:** Enforced at the API level.
*   **Secret Protection:** Automated filtering of `.env` and sensitive keys from AI context.
*   **Scoped Permissions:** Least-privilege GitHub tokens (only repo write, no admin access).

---

## 12. Telecode v2.0: The Autonomous Agent Bridge (Manus AI Era)

Telecode v2.0 upgrades the system from a single-prompt generator into an autonomous agent orchestrator. Instead of merely writing code and sending it to GitHub, the AI acts as an autonomous loop—planning, acting in a sandbox, observing results, and correcting build or test issues before pushing verified changes.

### 12.1 The Bridge Mental Model
Rather than building AI models or developer sandboxes from scratch, Telecode acts as the "orchestration nervous system" connecting existing, high-fidelity components:
*   **AI Planner:** Google Gemini (migrated to `gemini-3-flash-preview` for native Tool Calling / Function Calling).
*   **Sandbox execution:** Ephemeral cloud containers via **E2B.dev** with a resilient **local sandbox fallback** using sub-process separation in the workstation's `/scratch/sandbox/` folder.
*   **Version Control:** GitHub API for automated, non-destructive branches and PR creation.
*   **Human Control Centers:** Telegram Bot (mobile control) and Antigravity IDE Live Webview Panel (desktop sync).

### 12.2 The 8-Bridge Component Architecture

1.  **Bridge 1 — Gemini Function Calling (Tool Registry):** Exposes atomic functions (`read_file`, `write_file`, `run_command`, `search_codebase`, `search_web`, `create_pull_request`) to Gemini. Gemini invokes these directly as JSON-formatted tool calls.
2.  **Bridge 2 — Sandbox Execution Environment:** Executes command tools and writes files in a highly isolated, ephemeral environment, completely protecting the user's primary project state.
3.  **Bridge 3 — Agentic Loop (Plan ➔ Act ➔ Observe ➔ Repeat):** An execution controller that handles Gemini responses, executes requested tool functions, feeds outcomes back into chat history, and loops until the task is successfully implemented and verified.
4.  **Bridge 4 — Streaming Progress:** Real-time progress updates pushed to Telegram (editing status cards live) and streamed over WebSockets to active IDE panels.
5.  **Bridge 5 — IDE Live Panel:** A VS Code/Antigravity extension webview panel displaying real-time agent thoughts, diff Hunks with single-click accept/reject controls, and interactive steering.
6.  **Bridge 6 — Semantic Memory:** Seamless Postgres vector database (pgvector / Supabase) integration keeping a dynamic index of historical goals, solutions, and codebase layouts.
7.  **Bridge 7 — Web Research Tool:** Integration of Tavily API to let the agent autonomously research documentation and API modifications.
8.  **Bridge 8 — Risk-Gated Approvals:** Safeguard mechanisms pausing execution for HIGH-risk actions (e.g. key structural deletions, credentials writing, external API calls with monetary costs) to await user verification.

