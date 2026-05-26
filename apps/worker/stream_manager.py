"""
stream_manager.py — Real-time progress streaming for Telecode agent.
Posts and edits Telegram messages live, and streams updates to NestJS.
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

import httpx
import html
import asyncio
from typing import List, Dict, Optional


class StreamManager:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        task_id: str,
        user_id: str,
        server_url: str
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.task_id = task_id
        self.user_id = user_id
        self.server_url = server_url
        self.goal = ""
        self.telegram_message_id = None
        self.steps: Dict[int, Dict] = {}  # Format: { step_num: { "label": str, "status": str } }

    async def initialize_stream(self, goal: str) -> None:
        """Sends the initial progress card to Telegram and posts start status to NestJS."""
        self.goal = goal
        print(f"[Stream] Initializing progress stream for goal: '{goal}'")
        
        # Build initial Telegram card
        escaped_goal = html.escape(goal)
        initial_text = (
            f"🤖 <b>Telecode — Autonomous Run</b>\n\n"
            f"🎯 <b>Goal:</b> <i>{escaped_goal}</i>\n\n"
            f"⏳ Starting agent loop sandboxing..."
        )

        # 1. Post to Telegram
        if self.bot_token and self.chat_id:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json={
                        "chat_id": self.chat_id,
                        "text": initial_text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    })
                    if resp.status_code == 200:
                        data = resp.json()
                        self.telegram_message_id = data.get("result", {}).get("message_id")
                        print(f"[Stream] Telegram status card created (Msg ID: {self.telegram_message_id})")
                    else:
                        print(f"[Stream] Telegram initialization failed: {resp.text}")
            except Exception as e:
                print(f"[Stream] Telegram connection error: {e}")

        # 2. Post progress event to NestJS server
        await self._post_to_server(
            step=0,
            label="Starting autonomous loop",
            status="IN_PROGRESS"
        )

    async def update_step(self, step_num: int, label: str, status: str, output: str = "") -> None:
        """
        Updates a specific execution step, edits the live Telegram card,
        and streams the event to the NestJS server.
        
        status options: "IN_PROGRESS", "COMPLETED", "FAILED"
        """
        # Save step detail
        self.steps[step_num] = {
            "label": label,
            "status": status
        }
        
        print(f"[Stream] Step {step_num} -> {status}: {label}")

        # 1. Edit Telegram Progress Card
        if self.bot_token and self.chat_id and self.telegram_message_id:
            card_text = self._build_telegram_card()
            url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json={
                        "chat_id": self.chat_id,
                        "message_id": self.telegram_message_id,
                        "text": card_text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    })
                    if resp.status_code != 200:
                        print(f"[Stream] Telegram edit error: {resp.text}")
            except Exception as e:
                print(f"[Stream] Telegram edit connection error: {e}")

        # 2. Send event to NestJS Server
        await self._post_to_server(
            step=step_num,
            label=label,
            status=status,
            output=output
        )

    async def finish_stream(self, summary: str, success: bool = True) -> None:
        """Closes the stream and prints a final concluding step to all endpoints."""
        status = "COMPLETED" if success else "FAILED"
        print(f"[Stream] Stream finished with status: {status}")
        
        await self._post_to_server(
            step=999,  # Concluding step code
            label=summary,
            status=status
        )

    def _build_telegram_card(self) -> str:
        """Constructs a beautiful, dynamic, multiline step list for Telegram HTML."""
        escaped_goal = html.escape(self.goal)
        lines = [
            f"🤖 <b>Telecode — Autonomous Run</b>\n",
            f"🎯 <b>Goal:</b> <i>{escaped_goal}</i>\n",
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        ]

        # Sort and render steps
        for step_num in sorted(self.steps.keys()):
            step_info = self.steps[step_num]
            lbl = html.escape(step_info["label"])
            stat = step_info["status"]
            
            icon = "⏳"
            if stat == "COMPLETED":
                icon = "✅"
            elif stat == "FAILED":
                icon = "❌"
                
            lines.append(f"{icon} <b>Step {step_num}:</b> {lbl}\n")

        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━")
        return "".join(lines)

    async def _post_to_server(self, step: int, label: str, status: str, output: str = "") -> None:
        """Helper to POST progress status to the NestJS server."""
        payload = {
            "userId": self.user_id,
            "taskId": self.task_id,
            "step": step,
            "label": label,
            "status": status,
            "output": output
        }
        url = f"{self.server_url}/bot/progress"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 201 and resp.status_code != 200:
                    print(f"[Stream] Server dispatch failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            print(f"[Stream] Server connection error: {e}")

    async def request_safety_approval(self, tool_name: str, tool_args: dict) -> None:
        """Sends an inline keyboard message to Telegram asking for approval."""
        if not (self.bot_token and self.chat_id):
            return
        
        args_str = ", ".join([f"{k}={v}" for k, v in tool_args.items()])
        escaped_args = html.escape(args_str)
        
        text = (
            f"⚠️ <b>High-Risk Action Blocked</b>\n\n"
            f"The AI requested to execute a high-risk tool call:\n"
            f"• <b>Tool:</b> <code>{tool_name}</code>\n"
            f"• <b>Args:</b> <code>{escaped_args}</code>\n\n"
            f"Please approve or deny this action to continue."
        )
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✅ Approve", "callback_data": f"approve_task:{self.task_id}"},
                        {"text": "❌ Deny", "callback_data": f"deny_task:{self.task_id}"}
                    ]
                ]
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    print(f"[Stream] Failed to send safety approval prompt: {resp.text}")
        except Exception as e:
            print(f"[Stream] Safety approval prompt connection error: {e}")
