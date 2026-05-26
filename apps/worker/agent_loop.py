"""
agent_loop.py — The core state machine driving autonomous agent execution.
Implements Plan -> Act -> Observe -> Repeat using Gemini 3 function calling.
"""

import sys
# Force stdout/stderr to use UTF-8 on Windows to prevent UnicodeEncodeError with emojis
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import os
import asyncio
from google import genai
from google.genai import types as genai_types
from config import settings
from ai_engine import generate_content_with_fallback
from sandbox_client import SandboxClient
from tools import get_all_tools


SYSTEM_INSTRUCTION = """You are Telecode v2.0, a fully autonomous coding agent bridge.
Your goal is to satisfy the user's request by autonomously planning, exploring the codebase, modifying files, running validations, and creating a Pull Request.

Work sequentially using these rules:
1. EXPLORE: Begin by listing files or searching the codebase to understand where logic lives. Never write code blindly.
2. READ: Read files to understand structural patterns, imports, and variables.
3. WRITE: Implement your proposed changes carefully. Ensure robust typing and error handling.
4. VALIDATE: ALWAYS run appropriate build or test commands (e.g. npm run build, pytest, go test) in the sandbox after writing files.
5. FIX: If compilation or tests fail, read the errors and fix the files. Loop until it compiles successfully and tests are green.
6. DELIVER: Once the implementation is verified to be correct, compile-checked, and test-verified, call `create_pull_request` to commit your work and create a PR. Do not call this tool until you are certain the build passes.
7. FINISH: After the PR is successfully created, explain your final changes to the user and conclude your run.

Think step by step. Call tools one at a time to observe their results before making subsequent calls.
"""


def analyze_tool_risk(tool_name: str, args: dict) -> str:
    """
    Analyzes the tool and its arguments to determine risk level.
    Returns "HIGH" or "LOW".
    """
    if tool_name == "run_command":
        cmd = args.get("command", "").lower()
        # Destructive or high-risk command strings
        destructive_keywords = [
            "rm ", "rmdir", "delete", "destroy", "purge", "kill", "format", 
            "sudo", "su ", "chmod", "chown", "passwd", "useradd", "userdel",
            "curl ", "wget ", "ssh", "scp", "ftp", "docker", "systemctl",
            "shutdown", "reboot", "init 0", "mv ", "dd ", "mkfs", "parted"
        ]
        if any(kw in cmd for kw in destructive_keywords):
            return "HIGH"
            
    elif tool_name == "write_file":
        path = args.get("path", "").lower()
        # Modifying key credentials, configuration, or environment files
        sensitive_paths = [
            ".env", "config.json", "settings.json", "credentials", "id_rsa", 
            "id_dsa", ".pem", ".key", "auth", "token", "password",
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "requirements.txt",
            ".eslintrc", "tsconfig.json", "webpack.config", "vite.config", 
            "Dockerfile", "docker-compose", "nginx", "apache"
        ]
        if any(sp in path for sp in sensitive_paths):
            return "HIGH"
            
    elif tool_name == "create_pull_request":
        # Pull request creation is always a significant action
        return "HIGH"
        
    return "LOW"


async def run_agent_loop(
    task_id: str,
    goal: str,
    repo_full_name: str,
    github_token: str,
    base_branch: str = "main",
    session_context: str | None = None,
    max_steps: int = 15,
    stream_manager = None,
    gemini_api_key: str | None = None
) -> dict:
    """
    Runs the autonomous execution loop to achieve the specified goal.
    Returns a result payload with status, final description, and PR details.
    """
    print(f"[Agent] Starting agent loop for goal: '{goal}' on {repo_full_name} ({base_branch})")
    
    # 0. Initialize dynamic stream manager if provided
    if stream_manager:
        await stream_manager.initialize_stream(goal)
    
    # 1. Initialize sandbox
    sandbox = SandboxClient(repo_full_name=repo_full_name, github_token=github_token, base_branch=base_branch)
    await sandbox.initialize()
    
    # 2. Setup tools
    tools_list, tools_map = get_all_tools(
        sandbox=sandbox,
        repo_full_name=repo_full_name,
        github_token=github_token,
        base_branch=base_branch
    )
    
    client = genai.Client(api_key=gemini_api_key or settings.gemini_api_key)
    
    # Track the ongoing session history
    contents = []
    
    # Append context and goal to prompt
    prompt = goal
    if session_context:
        prompt = f"## Previous Session Memory\n{session_context}\n\n---\n\nGoal: {prompt}"
        
    contents.append(
        genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)]
        )
    )
    
    step = 0
    final_text = ""
    pr_url = None
    branch_name = None
    
    try:
        while step < max_steps:
            step += 1
            print(f"[Agent] --- Step {step}/{max_steps} ---")
            
            # Check for steering inputs (mid-course correction)
            if task_id and settings.server_url:
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=3.0) as http_client:
                        steer_resp = await http_client.get(f"{settings.server_url}/bot/tasks/{task_id}/steer")
                        if steer_resp.status_code == 200:
                            steer_data = steer_resp.json()
                            steer_text = steer_data.get("steer")
                            if steer_text:
                                print(f"[Agent] Received steering correction: '{steer_text}'")
                                if stream_manager:
                                    await stream_manager.update_step(step, f"💡 Steering: \"{steer_text}\"", "COMPLETED")
                                contents.append(
                                    genai_types.Content(
                                        role="user",
                                        parts=[
                                            genai_types.Part.from_text(
                                                text=f"System Alert: The user provided a mid-course correction. Adjust your plan immediately to satisfy this request:\n\n\"{steer_text}\""
                                            )
                                        ]
                                    )
                                )
                except Exception as steer_err:
                    print(f"[Agent] Failed to check steering: {steer_err}")

            if stream_manager:
                await stream_manager.update_step(step, "Planning next action...", "IN_PROGRESS")
            
            response, model_used = await generate_content_with_fallback(
                client=client,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=tools_list,
                    temperature=0.2,
                    max_output_tokens=4096,
                ),
            )
            print(f"[Agent] Gemini response generated by model: {model_used}")
            
            # Save final/intermediate model explanations
            if response.text:
                final_text += f"\n\n{response.text}"
                print(f"[Agent Thoughts]: {response.text}")
                
            # If no function calls, the model is providing a final text answer
            if not response.function_calls:
                print("[Agent] No further tool calls requested. Stopping.")
                break
                
            # Model has requested tool calls
            print(f"[Agent] Tool call requested: {[fc.name for fc in response.function_calls]}")
            
            # Create a turn matching the model's tool calls
            model_parts = []
            for fc in response.function_calls:
                model_parts.append(
                    genai_types.Part(
                        function_call=genai_types.FunctionCall(
                            name=fc.name,
                            args=fc.args
                        )
                    )
                )
            contents.append(genai_types.Content(role="model", parts=model_parts))
            
            # Execute the tool calls sequentially
            response_parts = []
            for fc in response.function_calls:
                tool_name = fc.name
                tool_args = fc.args or {}
                
                print(f"[Agent] Executing tool: '{tool_name}' with args: {tool_args}")
                
                # Check safety & risk level
                risk_level = analyze_tool_risk(tool_name, tool_args)
                is_allowed = True
                
                if risk_level == "HIGH" and task_id and settings.server_url:
                    print(f"[Agent] High-risk tool detected: {tool_name}. Awaiting safety approval...")
                    if stream_manager:
                        await stream_manager.request_safety_approval(tool_name, tool_args)
                        await stream_manager.update_step(
                            step,
                            f"⚠️ Awaiting safety approval in Telegram for high-risk action: {tool_name}",
                            "IN_PROGRESS"
                        )
                    
                    # Poll for approval
                    import time
                    approved = None
                    start_time = time.time()
                    timeout_limit = 300  # 5 minutes timeout
                    
                    while time.time() - start_time < timeout_limit:
                        try:
                            import httpx
                            async with httpx.AsyncClient(timeout=3.0) as http_client:
                                app_resp = await http_client.get(f"{settings.server_url}/bot/tasks/{task_id}/approval")
                                if app_resp.status_code == 200:
                                    app_data = app_resp.json()
                                    status_val = app_data.get("approved")
                                    if status_val is True:
                                        approved = True
                                        break
                                    elif status_val is False:
                                        approved = False
                                        break
                        except Exception as poll_err:
                            print(f"[Agent] Failed to poll approval status: {poll_err}")
                        await asyncio.sleep(2)
                    
                    if approved is True:
                        print("[Agent] Safety approval GRANTED.")
                        if stream_manager:
                            await stream_manager.update_step(step, f"✅ Approved: executing {tool_name}", "IN_PROGRESS")
                    else:
                        is_allowed = False
                        action_term = "denied" if approved is False else "timed out"
                        print(f"[Agent] Safety approval {action_term.upper()}. Blocking execution.")
                        tool_output = f"Error: Action was blocked by the user ({action_term}). Please propose a safer alternative or finish your execution."
                        if stream_manager:
                            await stream_manager.update_step(step, f"❌ Blocked: user {action_term} {tool_name}", "FAILED")
                
                if is_allowed:
                    if stream_manager:
                        args_str = ", ".join([f"{k}={v}" for k, v in tool_args.items()])
                        await stream_manager.update_step(step, f"Executing: {tool_name}({args_str})", "IN_PROGRESS")
                    
                    # Execute the bound function
                    if tool_name in tools_map:
                        try:
                            # Clean args to match signature (avoid internal parameters)
                            tool_func = tools_map[tool_name]
                            tool_output = await tool_func(**tool_args)
                        except Exception as err:
                            tool_output = f"Error executing tool: {str(err)}"
                    else:
                        tool_output = f"Error: Tool '{tool_name}' is not registered in Telecode."
                
                print(f"[Agent] Tool result output snippet: {str(tool_output)[:120]}...")
                if stream_manager and is_allowed:
                    await stream_manager.update_step(step, f"Finished: {tool_name}", "COMPLETED", output=str(tool_output))
                
                # Feed the output back to the model history
                response_parts.append(
                    genai_types.Part(
                        function_response=genai_types.FunctionResponse(
                            name=tool_name,
                            response={"result": tool_output}
                        )
                    )
                )
                
            contents.append(genai_types.Content(role="user", parts=response_parts))
            
            # Check if PR was created
            if getattr(sandbox, "pr_url", None):
                pr_url = sandbox.pr_url
                branch_name = sandbox.branch_name
                print(f"[Agent] PR created successfully: {pr_url}")
                # We do not immediately stop; let the model conclude its response.
                
        if step >= max_steps:
            print("[Agent] Reached maximum allowed loop steps.")
            final_text += "\n\n_(Task reached execution step limit)_"
            
    except Exception as exc:
        print(f"[Agent] Agent loop encountered error: {exc}")
        final_text += f"\n\n❌ Execution error: {str(exc)}"
        
    finally:
        # Collect modified files before clean up
        modified_files_list = list(sandbox.modified_files)
        # 3. Clean up sandbox
        await sandbox.cleanup()
        
        # Conclude streaming progress
        if stream_manager:
            success = pr_url is not None
            summary = f"Pull request created successfully: {pr_url}" if success else "Agent run complete (no PR generated)."
            await stream_manager.finish_stream(summary, success=success)
        
    return {
        "result": final_text.strip(),
        "branch_name": branch_name,
        "pr_url": pr_url,
        "modified_files": modified_files_list,
        "status": "COMPLETED" if pr_url else "FAILED"
    }
