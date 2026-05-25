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

        # 2. Call AI (Autonomous agent loop for execute/fix, or standard one-shot for explain/plan/search)
        pr_url: Optional[str] = None
        diff_summary: Optional[str] = None
        confidence_score: Optional[int] = None
        risk_level: Optional[str] = None
        risk_analysis: Optional[str] = None

        if req.mode in [TaskMode.EXECUTE, TaskMode.FIX]:
            from agent_loop import run_agent_loop
            from stream_manager import StreamManager
            from memory_client import SemanticMemoryClient
            
            print(f"[Worker] Querying semantic memory for task {task_id}...")
            memories_context = None
            try:
                memory_client = SemanticMemoryClient()
                memories_context = await memory_client.search_memories(req.prompt, req.repo_full_name or "")
            except Exception as mem_err:
                print(f"[Worker] Failed to query semantic memory: {mem_err}")
                
            # Combine traditional context and semantic memories
            combined_context = ""
            if req.session_context:
                combined_context += f"## Previous Session Context:\n{req.session_context}\n\n"
            if memories_context:
                combined_context += f"{memories_context}\n\n"
            combined_context = combined_context.strip() or None

            print(f"[Worker] Dispatching autonomous agent loop for task {task_id}...")
            stream_manager = StreamManager(
                bot_token=bot_token or "",
                chat_id=chat_id,
                task_id=task_id,
                user_id=user_id,
                server_url=settings.server_url
            )
            
            ai_result = await run_agent_loop(
                task_id=task_id,
                goal=req.prompt,
                repo_full_name=req.repo_full_name or "",
                github_token=req.github_token or "",
                base_branch=req.repo_default_branch or "main",
                session_context=combined_context,
                stream_manager=stream_manager
            )
            
            result_text = ai_result["result"]
            branch_name = ai_result["branch_name"]
            pr_url = ai_result["pr_url"]
            modified_files = ai_result.get("modified_files", [])
            
            if modified_files:
                file_lines = []
                for path in modified_files:
                    file_lines.append(f"  {path}")
                diff_summary = f"📝 {len(modified_files)} file{'s' if len(modified_files) != 1 else ''} changed:\n" + "\n".join(file_lines)
                
            if ai_result["status"] == "COMPLETED" or pr_url:
                confidence_score = 95
                risk_level = "LOW"
                risk_analysis = "Agent autonomously compiled and verified all changes in isolated sandbox environment."
                
                # Write to semantic memory card
                try:
                    decisions_summary = f"Files Modified: {', '.join(modified_files) if modified_files else 'None'}\nResult: {result_text}"
                    await memory_client.add_memory(
                        task_id=task_id,
                        repo_name=req.repo_full_name or "",
                        goal=req.prompt,
                        decisions=decisions_summary
                    )
                except Exception as mem_save_err:
                    print(f"[Worker] Failed to save completion memory card: {mem_save_err}")
            else:
                # Agent loop failed or couldn't create PR
                raise Exception(f"Autonomous agent failed to generate a pull request. Output:\n{result_text}")
        else:
            # Plan, Search, Explain modes run the traditional one-shot generation
            ai_result = await process_task(
                mode=req.mode.value,
                prompt=req.prompt,
                repo_full_name=req.repo_full_name,
                repo_default_branch=req.repo_default_branch,
                github_token=req.github_token,
                session_context=req.session_context,
            )
            result_text = ai_result["result"]
            branch_name = ai_result.get("branch_name")
            confidence_score = ai_result.get("confidence_score")
            risk_level = ai_result.get("risk_level")
            risk_analysis = ai_result.get("risk_analysis")
            
            # Simple fallback files list for explain/plan if present in one-shot
            files = ai_result.get("files", [])
            if files:
                file_lines = []
                for f in files:
                    path = f.get("path", "?")
                    file_lines.append(f"  {path}")
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
