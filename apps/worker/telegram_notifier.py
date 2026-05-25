"""
telegram_notifier.py — Push AI results back to the user via the Telegram Bot API.

The worker calls this after completing a task so the user gets their answer
directly in the chat — even if they've closed the app.
"""

import httpx
from config import settings


_BOT_BASE = f"https://api.telegram.org/bot{'{token}'}/sendMessage"


async def send_result(
    bot_token: str,
    chat_id: str | int,
    task_mode: str,
    result: str,
    branch_name: str | None = None,
    pr_url: str | None = None,
    confidence_score: int | None = None,
    risk_level: str | None = None,
    risk_analysis: str | None = None,
    diff_summary: str | None = None,
) -> bool:
    """
    Send the AI result back to the user's Telegram chat.
    Returns True on success.
    """
    mode_emoji = {"EXPLAIN": "🔍", "PLAN": "🗺", "EXECUTE": "⚡", "FIX": "🛠", "SEARCH": "🔎"}.get(task_mode, "🤖")
    mode_label = {"EXPLAIN": "Explanation", "PLAN": "Plan", "EXECUTE": "Execution Result", "FIX": "Bug Fix", "SEARCH": "Search Results"}.get(task_mode, "Result")

    import html
    
    # Escape result to prevent HTML parsing errors
    escaped_result = html.escape(result)
    
    # AI output is Markdown. Converting Markdown to Telegram HTML.
    import re
    
    # 1. Code blocks: ```lang\ncode\n``` -> <pre><code class="language-lang">code</code></pre>
    formatted_result = re.sub(
        r'```(\w*)\n?(.*?)\n?```', 
        r'<pre><code class="language-\1">\2</code></pre>', 
        escaped_result, 
        flags=re.DOTALL
    )
    
    # 2. Inline code: `code` -> <code>code</code>
    formatted_result = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', formatted_result)
    
    # 3. Bold: **text** -> <b>text</b>
    formatted_result = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', formatted_result)
    
    # 4. Italic: *text* -> <i>text</i>
    formatted_result = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', r'<i>\1</i>', formatted_result)
    
    # 5. Links: [text](url) -> <a href="url">text</a>
    formatted_result = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', formatted_result)
    
    header = f"{mode_emoji} <b>Telecode — {mode_label}</b>\n\n"
    footer = ""

    if branch_name:
        footer += f"\n\n🌿 Branch: <code>{html.escape(branch_name)}</code>"
    if pr_url:
        footer += f"\n🔗 <a href=\"{html.escape(pr_url)}\">View Pull Request</a>"

    # ── Diff Summary (EXECUTE / FIX only) ─────────────────────────────────
    if task_mode in ["EXECUTE", "FIX"] and diff_summary:
        footer += f"\n\n<pre>{html.escape(diff_summary)}</pre>"

    # ── AI Analysis Card (EXECUTE / FIX only) ────────────────────────────────
    if task_mode in ["EXECUTE", "FIX"] and (confidence_score is not None or risk_level):
        footer += "\n\n" + _build_analysis_card(confidence_score, risk_level, risk_analysis)

    full_message = header + formatted_result + footer
    
    # Telegram messages max 4096 chars
    chunks = _split_message(full_message, max_len=4000)

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async with httpx.AsyncClient(timeout=15.0) as client:
        for chunk in chunks:
            try:
                resp = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })
                resp.raise_for_status()
            except Exception as e:
                print(f"[Telegram] Failed to send chunk: {e}")
                # Log response if possible
                if 'resp' in locals() and resp:
                    print(f"[Telegram] Error response: {resp.text}")
                return False

    return True


def _build_analysis_card(
    confidence_score: int | None,
    risk_level: str | None,
    risk_analysis: str | None,
) -> str:
    """
    Build a beautifully formatted AI Analysis Card for Telegram HTML.
    Shows a confidence gauge bar and a color-coded risk badge.
    """
    import html
    lines = ["━━━━━━━━━━━━━━━━━━━━━━━"]
    lines.append("🧠 <b>AI Analysis</b>")

    # Confidence score bar
    if confidence_score is not None:
        score = max(0, min(100, confidence_score))
        filled = round(score / 10)  # 0-10 blocks
        empty = 10 - filled
        if score >= 80:
            bar_emoji = "🟢"
        elif score >= 50:
            bar_emoji = "🟡"
        else:
            bar_emoji = "🔴"
        bar = "█" * filled + "░" * empty
        lines.append(f"\n{bar_emoji} <b>Confidence:</b> {score}%")
        lines.append(f"<code>[{bar}]</code>")

    # Risk badge
    if risk_level:
        risk_badge = {
            "LOW":    "🟢 LOW",
            "MEDIUM": "🟡 MEDIUM",
            "HIGH":   "🔴 HIGH",
        }.get(risk_level.upper(), f"⚪ {risk_level}")
        lines.append(f"\n⚠️ <b>Risk Level:</b> {risk_badge}")

    # Risk analysis text
    if risk_analysis:
        lines.append(f"\n📋 {html.escape(risk_analysis)}")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """
    Split long messages into Telegram-safe chunks while respecting HTML tags.
    Maintains a stack of open tags to close them at the end of a chunk and 
    reopen them at the start of the next.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    import re
    tag_pattern = re.compile(r"<(/?)([a-z1-6]+)(?:\s+[^>]*)?>", re.IGNORECASE)

    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
            
        # Find best split point (newline preferred)
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1 or split_at < max_len * 0.7:
            split_at = text.rfind(" ", 0, max_len)
        if split_at == -1:
            split_at = max_len
            
        chunk = text[:split_at]
        
        # Track open tags in this chunk
        open_tags = [] # stores (tag_name, full_opening_tag)
        for match in tag_pattern.finditer(chunk):
            is_closing = bool(match.group(1))
            tag_name = match.group(2).lower()
            full_tag = match.group(0)
            
            if is_closing:
                if open_tags and open_tags[-1][0] == tag_name:
                    open_tags.pop()
            else:
                # Tags that don't need closing
                if tag_name not in ["br", "hr", "img", "input", "meta", "link"]:
                    open_tags.append((tag_name, full_tag))
        
        # Close open tags in reverse order for this chunk
        if open_tags:
            for tag_name, _ in reversed(open_tags):
                chunk += f"</{tag_name}>"
        
        chunks.append(chunk)
        
        # Prepare the next part of text
        remaining = text[split_at:]
        if open_tags:
            # Prepend opening tags to the next part in original order
            opening_prefix = "".join([tag[1] for tag in open_tags])
            remaining = opening_prefix + remaining
            
        text = remaining.lstrip("\n")
        
    return chunks
