"""
main.py — Telecode AI Worker (FastAPI)

Endpoints:
  GET  /health          — liveness probe
  POST /process         — receive a task from the NestJS server, run AI, report back
  POST /process/echo    — dev endpoint: echoes the prompt without calling Gemini
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse

from config import settings
from models import ProcessTaskRequest, TaskMode
from ai_engine import process_task
from server_client import mark_in_progress, mark_completed, mark_failed
from telegram_notifier import send_result
from github_client import GitHubClient
import httpx



# ─── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Telecode Worker starting on port {settings.worker_port}")
    print(f"   Server URL : {settings.server_url}")
    print(f"   Gemini key : {'set' if settings.gemini_api_key else 'NOT SET'}")
    yield
    print("Worker shutting down")


app = FastAPI(
    title="Telecode AI Worker",
    description="Python FastAPI worker that processes coding tasks via Gemini.",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _verify_secret(x_worker_secret: str | None) -> None:
    if x_worker_secret != settings.worker_secret:
        raise HTTPException(status_code=401, detail="Invalid worker secret")


# ─── Session memory helper ────────────────────────────────────────────────────

async def _append_session(
    user_id: str,
    mode: str,
    prompt: str,
    result_summary: str,
    branch: str | None,
) -> None:
    """Persist a completed task summary to the server's session memory store."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.server_url}/bot/session/append",
                json={
                    "userId": user_id,
                    "mode": mode,
                    "prompt": prompt,
                    "result_summary": result_summary,
                    "branch": branch,
                },
            )
    except Exception as e:
        print(f"[Session] Failed to append session memory: {e}")


# ─── Background task runner ───────────────────────────────────────────────────

async def _run_task(req: ProcessTaskRequest, bot_token: str, chat_id: str) -> None:
    """
    Full pipeline:
      1. Mark task IN_PROGRESS on the server
      2. Call Gemini
      3. Mark COMPLETED / FAILED on the server
      4. Push result to Telegram
    """
    task_id = req.task_id
    user_id = req.user_id

    try:
        # 1. Mark in progress
        await mark_in_progress(task_id, user_id)

        # 2. Call AI
        ai_result = await process_task(
            mode=req.mode.value,
            prompt=req.prompt,
            repo_full_name=req.repo_full_name,
            repo_default_branch=req.repo_default_branch,
            github_token=req.github_token,
            session_context=req.session_context,
        )

        result_text: str = ai_result["result"]
        branch_name: str | None = ai_result.get("branch_name")
        commit_message: str = ai_result.get("commit_message", "feat: telecode update")
        files: list[dict] = ai_result.get("files", [])
        confidence_score: int | None = ai_result.get("confidence_score")
        risk_level: str | None = ai_result.get("risk_level")
        risk_analysis: str | None = ai_result.get("risk_analysis")

        # 3. If EXECUTE/FIX and we have files, push to GitHub
        pr_url: str | None = None
        if req.mode in [TaskMode.EXECUTE, TaskMode.FIX] and files and req.repo_full_name:
            gh = GitHubClient(token=req.github_token)
            try:
                # Create branch
                branch_to_use = branch_name or f"telecode/task-{task_id}"
                await gh.create_branch(
                    repo_full_name=req.repo_full_name,
                    base_branch=req.repo_default_branch or "main",
                    new_branch=branch_to_use
                )
                
                # Commit files
                await gh.commit_files(
                    repo_full_name=req.repo_full_name,
                    branch=branch_to_use,
                    files=files,
                    commit_message=commit_message
                )

                # Create PR
                pr_url = await gh.create_pull_request(
                    repo_full_name=req.repo_full_name,
                    title=commit_message,
                    body=f"Telecode AI generated changes for task {task_id}.\n\n{result_text[:500]}...",
                    head=branch_to_use,
                    base=req.repo_default_branch or "main"
                )
                
                # In Phase 3, we don't append to result_text manually anymore.
                # The send_result function handles the PR link display.
                pass
                
            except Exception as gh_err:
                print(f"[Worker] GitHub operation failed: {gh_err}")
                result_text += f"\n\nWarning: Could not push to GitHub: {str(gh_err)}"

        # Phase D: Build a compact diff summary card for Telegram
        diff_summary: str | None = None
        if files:
            file_lines = []
            for f in files:
                path = f.get("path", "?")
                content = f.get("content", "")
                line_count = content.count("\n") + 1
                file_lines.append(f"  {path} (~{line_count} lines)")
            diff_summary = f"📝 {len(files)} file{'s' if len(files) != 1 else ''} changed:\n" + "\n".join(file_lines)


        # 4. Mark completed
        await mark_completed(
            task_id, user_id,
            result=result_text,
            branch_name=branch_name,
        )

        # 4b. Write session memory entry so future tasks have context
        await _append_session(
            user_id=user_id,
            mode=req.mode.value,
            prompt=req.prompt,
            result_summary=result_text[:200].replace('\n', ' '),
            branch=branch_name,
        )

        # 5. Notify user via Telegram
        if bot_token and chat_id:
            await send_result(
                bot_token=bot_token,
                chat_id=chat_id,
                task_mode=req.mode.value,
                result=result_text,
                branch_name=branch_name,
                pr_url=pr_url,
                confidence_score=confidence_score,
                risk_level=risk_level,
                risk_analysis=risk_analysis,
                diff_summary=diff_summary,
            )

    except Exception as exc:
        error_msg = str(exc)
        print(f"[Worker] Task {task_id} failed: {error_msg}")
        try:
            await mark_failed(task_id, user_id, error_msg)
            if bot_token and chat_id:
                await send_result(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    task_mode=req.mode.value,
                    result=f"Task failed: {error_msg}",
                )
        except Exception as notify_err:
            print(f"[Worker] Failed to notify failure: {notify_err}")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "worker": "telecode-ai-worker",
        "gemini_configured": bool(settings.gemini_api_key),
    }


@app.post("/process")
async def process(
    req: ProcessTaskRequest,
    background_tasks: BackgroundTasks,
    x_worker_secret: str | None = Header(default=None),
    x_bot_token: str | None = Header(default=None),
    x_chat_id: str | None = Header(default=None),
):
    """
    Dispatched by the NestJS server when a new Task is created.
    Returns 202 immediately; processing happens in the background.
    
    Headers:
      X-Worker-Secret  — shared secret for auth
      X-Bot-Token      — Telegram bot token for push notification
      X-Chat-Id        — Telegram chat ID to reply to
    """
    _verify_secret(x_worker_secret)

    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY not configured on the worker."
        )

    background_tasks.add_task(
        _run_task,
        req,
        x_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        x_chat_id or "",
    )

    return JSONResponse(
        status_code=202,
        content={
            "message": "Task accepted",
            "task_id": req.task_id,
            "mode": req.mode.value,
        },
    )


@app.post("/process/echo")
async def process_echo(
    req: ProcessTaskRequest,
    x_worker_secret: str | None = Header(default=None),
):
    """
    Dev/test endpoint — echoes the request without calling Gemini.
    Useful for testing the bot → server → worker pipeline.
    """
    _verify_secret(x_worker_secret)

    echo_result = (
        f"🔊 *Echo Mode* (dev)\n\n"
        f"**Task ID:** `{req.task_id}`\n"
        f"**Mode:** `{req.mode.value}`\n"
        f"**Prompt:** {req.prompt}\n"
        f"**Repo:** {req.repo_full_name or 'none'}\n\n"
        f"_(Gemini not called — this is an echo response)_"
    )

    return {
        "task_id": req.task_id,
        "result": echo_result,
        "mode": req.mode.value,
        "status": "COMPLETED",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.worker_port, reload=True)
