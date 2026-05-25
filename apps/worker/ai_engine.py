"""
ai_engine.py — Gemini-powered AI processing for each TaskMode.

Modes:
  EXPLAIN  → Read-only. Answers questions about code / concepts.
  PLAN     → Generates a step-by-step implementation plan for a feature.
  EXECUTE  → (Phase 3) Actionable AI. Returns a structured code change plan
             and creates a simulated pull request with full file contents.
"""

from google import genai
from google.genai import types as genai_types
from config import settings

# Instantiate once at module load
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


MODEL = "gemini-2.0-flash"  # Fast, cost-effective; swap to gemini-1.5-pro for deeper reasoning


# ── Security: Sensitive path filter ─────────────────────────────────────────
# These patterns are NEVER passed to the AI — not in the file tree, not as
# file content. This prevents secret leakage even if the user asks for it.

import re as _re

_BLOCKED_PATTERNS = [
    r"^\.env$",
    r"^\.env\.",            # .env.local, .env.production, etc.
    r".*\.pem$",
    r".*\.key$",
    r".*\.p12$",
    r".*\.pfx$",
    r".*\.secret$",
    r".*\.cer$",
    r".*id_rsa.*",
    r".*id_ed25519.*",
    r"^secrets/",
    r"^\.secrets/",
    r"^credentials/",
    r".*password.*\.txt$",
    r".*token.*\.txt$",
]

_BLOCKED_COMPILED = [_re.compile(p, _re.IGNORECASE) for p in _BLOCKED_PATTERNS]


def _is_sensitive(path: str) -> bool:
    """Return True if the file path matches any blocked pattern."""
    for pattern in _BLOCKED_COMPILED:
        if pattern.search(path):
            return True
    return False


# ── System prompt templates ──────────────────────────────────────────────────

_SYSTEM_BASE = """You are Telecode, an expert AI coding assistant embedded inside Telegram.
You are helping a developer who is away from their computer and wants to continue coding.
Be concise, practical, and always structure your output clearly.
Use markdown formatting (headers, code blocks, bullet lists) so Telegram can render it well."""

_SYSTEM_EXPLAIN = _SYSTEM_BASE + """

Your current mode is EXPLAIN.
The user wants to understand code, a concept, or get a quick answer.
- Keep responses under 400 words unless complexity demands more.
- Use code blocks with language hints for all code examples.
- End with a one-line "Key takeaway: ..." summary."""

_SYSTEM_SEARCH = _SYSTEM_BASE + """

Your current mode is SEARCH.
Your goal is to look at the repository file tree and help the user find where specific logic or features are implemented.

Provide a helpful, organized analysis:
1. **🔍 Direct Matches**: The exact files (with paths) where the requested logic likely resides.
2. **🔗 Related Files**: Other files (configs, tests, or imports) that might be affected or provide useful context.
3. **💡 Reasoning**: A brief, conversational explanation of why these files are relevant and how they interact.

Keep the response focused and under 250 words. If multiple paths are possible, mention the most likely one first."""

_SYSTEM_PLAN = _SYSTEM_BASE + """

Your current mode is PLAN.
The user wants a structured implementation plan for a new feature or change.
Output format MUST be:

## 🎯 Goal
One sentence summary of what will be built.

## 📋 Implementation Steps
Numbered list of concrete tasks. Each task should be atomic enough to be done in one commit.

## 🏗️ Files to Create / Modify
List of files with a brief note on what changes.

## ⚠️ Considerations
Key risks, gotchas, or dependencies to be aware of.

## ✅ Definition of Done
How to verify the feature is working correctly."""

_SYSTEM_EXECUTE = _SYSTEM_BASE + """

Your current mode is EXECUTE.
The user wants you to implement a code change. 
You must produce:
1. A detailed explanation of what you are changing and why.
2. A branch name starting with `telecode/`.
3. A concise commit message.
4. A JSON block containing the changes.

Output structure:
---
[Your detailed explanation here]

**Branch:** `telecode/short-description`
**Commit:** `feat: description`

```json
{
  "branch": "telecode/short-description",
  "commit": "feat: description",
  "confidence_score": 85,
  "risk_level": "LOW",
  "risk_analysis": "Brief 1-2 sentence explanation of what could go wrong and how to mitigate it.",
  "files": [
    {
      "path": "path/to/file.ts",
      "content": "FULL file content here. NO TRUNCATION. NO '...'"
    }
  ]
}
```

CRITICAL: 
- ALWAYS provide the FULL content of the file. 
- If you are modifying an existing file, you MUST include all its original content plus your changes. 
- Use valid JSON. Double check your quotes and braces.
- confidence_score: integer 0-100 (how confident you are the change is correct).
- risk_level: one of LOW, MEDIUM, or HIGH.
- risk_analysis: a concise 1-2 sentence plain-text risk summary."""

_SYSTEM_FIX = _SYSTEM_BASE + """

Your current mode is FIX.
The user wants you to fix a bug or an error in the code.
You must produce:
1. A brief analysis of the cause of the bug.
2. A detailed explanation of the fix.
3. A branch name starting with `telecode/fix-`.
4. A concise commit message starting with `fix:`.
5. A JSON block containing the changes.

Output structure:
---
[Your analysis and fix explanation here]

**Branch:** `telecode/fix-description`
**Commit:** `fix: description`

```json
{
  "branch": "telecode/fix-description",
  "commit": "fix: description",
  "confidence_score": 90,
  "risk_level": "LOW",
  "risk_analysis": "Brief 1-2 sentence explanation of potential side effects or edge cases.",
  "files": [
    {
      "path": "path/to/file.ts",
      "content": "FULL file content here. NO TRUNCATION. NO '...'"
    }
  ]
}
```

CRITICAL: 
- ALWAYS provide the FULL content of the file. 
- If you are modifying an existing file, you MUST include all its original content plus your changes. 
- Use valid JSON. Double check your quotes and braces.
- confidence_score: integer 0-100 (how confident you are the fix is correct).
- risk_level: one of LOW, MEDIUM, or HIGH.
- risk_analysis: a concise 1-2 sentence plain-text risk summary."""


def _extract_json(text: str) -> dict | None:
    """Helper to extract and parse the first JSON block from text."""
    import json
    import re

    # 1. Try to find content within ```json ... ``` blocks
    json_blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    
    # 2. If no fenced blocks, try to find the largest { ... } block
    if not json_blocks:
        json_blocks = re.findall(r"(\{.*?\})", text, re.DOTALL)

    if not json_blocks:
        return None

    # Try to parse the largest block found (usually the one with the actual data)
    # Sort by length descending
    json_blocks.sort(key=len, reverse=True)

    for block in json_blocks:
        try:
            # Clean up common AI artifacts
            cleaned = block.strip()
            # Remove trailing commas if present (invalid JSON)
            cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            continue
            
    return None


def _build_context(repo_full_name: str | None, repo_branch: str | None) -> str:
    if not repo_full_name:
        return "No repository is currently connected."
    return (
        f"Repository: {repo_full_name}\n"
        f"Default branch: {repo_branch or 'main'}"
    )


# ── Public interface ─────────────────────────────────────────────────────────

async def process_task(
    mode: str,
    prompt: str,
    repo_full_name: str | None = None,
    repo_default_branch: str | None = None,
    github_token: str | None = None,
    session_context: str | None = None,
) -> dict:
    """
    Send the task to Gemini and return a structured result dict.
    Returns: { "result": str, "branch_name": str | None, "confidence_score": int | None, ... }
    """
    client = _get_client()

    system_map = {
        "EXPLAIN": _SYSTEM_EXPLAIN,
        "PLAN": _SYSTEM_PLAN,
        "EXECUTE": _SYSTEM_EXECUTE,
        "SEARCH": _SYSTEM_SEARCH,
        "FIX": _SYSTEM_FIX,
    }
    system_instruction = system_map.get(mode, _SYSTEM_EXPLAIN)

    # ─── Context Injection ────────────────────────────────────────────────────
    gh = None
    if repo_full_name:
        from github_client import GitHubClient
        gh = GitHubClient(token=github_token)
        
        # 1. Always provide the file tree if we have a repo
        file_tree = []
        try:
            raw_tree = await gh.get_file_tree(repo_full_name, repo_default_branch)
            # 🔒 Security: strip sensitive files from what the AI ever sees
            blocked = [f for f in raw_tree if _is_sensitive(f)]
            file_tree = [f for f in raw_tree if not _is_sensitive(f)]
            if blocked:
                print(f"[Security] Blocked {len(blocked)} sensitive file(s) from AI context: {blocked}")
        except Exception as e:
            print(f"❌ Failed to fetch file tree for context: {str(e)}")
        
        tree_str = "\n".join(file_tree) if file_tree else "Unavailable"
        prompt = f"Codebase Structure:\n```\n{tree_str}\n```\n\n{prompt}"

        # 2. Automatically fetch high-priority files (README, package.json, etc.)
        high_priority = ["README.md", "package.json", "requirements.txt", "main.py", "index.ts"]
        existing_high_priority = [f for f in high_priority if f in file_tree]  # already filtered
        
        # 3. Detect files mentioned in the prompt
        import re
        # Improved regex to catch paths like apps/server/src/main.ts or ./src/utils.js
        mentioned_files = re.findall(r"(?:(?:\./|/)?[\w\-]+(?:/[\w\-]+)*\.(?:ts|js|py|md|json|html|css|prisma|graphql|yml|yaml|txt))", prompt)
        
        # Combine, deduplicate, and filter out any sensitive paths the user may have explicitly named
        candidate_files = list(set(existing_high_priority + [f.lstrip("./") for f in mentioned_files if f.lstrip("./") in file_tree]))
        files_to_read = [f for f in candidate_files if not _is_sensitive(f)]
        skipped = [f for f in candidate_files if _is_sensitive(f)]
        if skipped:
            print(f"[Security] Blocked explicit fetch of sensitive file(s): {skipped}")
        
        if files_to_read:
            print(f"[AI Context] Fetching {len(files_to_read)} files for context: {files_to_read}")
            context_files = []
            for file_path in files_to_read:
                content = await gh.get_file_content(repo_full_name, file_path, repo_default_branch or "main")
                if content:
                    context_files.append(f"File: `{file_path}`\nContent:\n```\n{content}\n```")
            
            if context_files:
                files_str = "\n\n".join(context_files)
                prompt = f"Relevant File Context:\n{files_str}\n\n---\n\n{prompt}"

    # ─── Session Memory Injection ─────────────────────────────────────────────
    if session_context:
        prompt = f"## 🧠 Previous Session Memory\n{session_context}\n\n---\n\n{prompt}"

    context = _build_context(repo_full_name, repo_default_branch)
    user_message = f"{context}\n\n---\n\n{prompt}"

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.4,
            max_output_tokens=4096, # Increased for code generation
        ),
    )

    result_text = response.text or "_(No response generated)_"

    # Extract suggested branch name from EXECUTE responses
    branch_name: str | None = None
    files_to_commit: list[dict] = []
    commit_message: str = "feat: telecode update"

    confidence_score: int | None = None
    risk_level: str | None = None
    risk_analysis: str | None = None

    if mode in ["EXECUTE", "FIX"]:
        import re
        data = _extract_json(result_text)
        if data:
            branch_name = data.get("branch")
            commit_message = data.get("commit", commit_message)
            files_to_commit = data.get("files", [])
            # Extract new confidence/risk fields
            raw_score = data.get("confidence_score")
            if isinstance(raw_score, (int, float)):
                confidence_score = int(raw_score)
            risk_level = data.get("risk_level")  # LOW | MEDIUM | HIGH
            risk_analysis = data.get("risk_analysis")

        # Fallback for branch name if JSON parsing failed or was incomplete
        if not branch_name:
            match = re.search(r"`(telecode/[^\s`]+)`", result_text)
            if match:
                branch_name = match.group(1)

    return {
        "result": result_text,
        "branch_name": branch_name,
        "commit_message": commit_message,
        "files": files_to_commit,
        "confidence_score": confidence_score,
        "risk_level": risk_level,
        "risk_analysis": risk_analysis,
    }
