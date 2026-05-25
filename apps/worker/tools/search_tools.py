"""
search_tools.py — Codebase search and Tavily-powered web research tools.
"""

import os
import httpx
from sandbox_client import SandboxClient


def get_search_tools(sandbox: SandboxClient, repo_full_name: str = ""):
    """Returns codebase, web search, and semantic memory tools bound to the sandbox."""

    async def search_codebase(query: str) -> str:
        """
        Recursively search the repository codebase for files containing the query string or matching the filename.

        Args:
            query: The search term or filename keyword to look for.

        Returns:
            A list of matching relative file paths and occurrences.
        """
        print(f"[Search Tool] Searching codebase for: '{query}'")
        
        # Native, safe python script execution in the sandbox to keep it platform independent
        search_script = f"""
import os
query = {repr(query)}.lower()
matches = []

# Excluded directories
excluded_dirs = {{'node_modules', '.git', 'dist', '.venv', 'build', '__pycache__', 'scratch'}}

for root, dirs, files in os.walk('.'):
    # Prune excluded directories
    dirs[:] = [d for d in dirs if d not in excluded_dirs]
    
    for file in files:
        rel_path = os.path.relpath(os.path.join(root, file), '.')
        # Avoid search in sensitive paths
        if any(pat in rel_path.lower() for pat in ['.env', '.pem', '.key', '.secret']):
            continue
            
        if query in file.lower():
            matches.append(f"File match: {rel_path}")
            continue
            
        try:
            with open(rel_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().lower()
                if query in content:
                    # Count occurrences
                    count = content.count(query)
                    matches.append(f"Content match: {rel_path} ({count} occurrences)")
        except Exception:
            pass

print('\\n'.join(matches[:25]))
"""
        try:
            stdout, stderr, exit_code = await sandbox.run_command(f"python -c {repr(search_script)}")
            if exit_code != 0:
                # Fallback to local walk if python fails inside the sandbox
                if not sandbox.is_e2b and sandbox.workspace_dir:
                    return _local_search_fallback(sandbox.workspace_dir, query)
                return f"Search command failed: {stderr}"
                
            res = stdout.strip()
            return res if res else "No matches found in the codebase."
        except Exception as e:
            return f"Error executing codebase search: {str(e)}"

    async def search_web(query: str) -> str:
        """
        Search the web for up-to-date documentation, API examples, and error resolutions.
        Use this when working with third-party libraries or when encountering unknown errors.

        Args:
            query: The search query string.

        Returns:
            Top web search results with snippets and source URLs.
        """
        tavily_api_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_api_key:
            return "Web search is currently disabled because TAVILY_API_KEY is not set."

        print(f"[Search Tool] Performing web search for: '{query}'")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_api_key,
                        "query": query,
                        "max_results": 3,
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    return "No web search results found."

                output = []
                for idx, r in enumerate(results, 1):
                    output.append(f"{idx}. {r['title']}\n   URL: {r['url']}\n   Snippet: {r['content']}")
                return "\n\n".join(output)
        except Exception as e:
            return f"Error executing web search: {str(e)}"

    async def search_memory(query: str) -> str:
        """
        Search the semantic memory database for historical decisions, architectural choices,
        and past task implementations in this repository. Use this to maintain consistency
        with prior work or find patterns for recurring tasks.

        Args:
            query: The semantic search query description.

        Returns:
            A list of relevant historical memories and implementation decisions.
        """
        from memory_client import SemanticMemoryClient
        try:
            client = SemanticMemoryClient()
            res = await client.search_memories(query, repo_full_name)
            return res
        except Exception as e:
            return f"Error executing memory search: {str(e)}"

    return [search_codebase, search_web, search_memory]


def _local_search_fallback(workspace_dir: str, query: str) -> str:
    """Helper for searching local directory when shell execution fails."""
    matches = []
    query = query.lower()
    excluded = {'node_modules', '.git', 'dist', '.venv', 'build', '__pycache__', 'scratch'}
    
    for root, dirs, files in os.walk(workspace_dir):
        dirs[:] = [d for d in dirs if d not in excluded]
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, workspace_dir)
            
            if any(pat in rel_path.lower() for pat in ['.env', '.pem', '.key', '.secret']):
                continue
                
            if query in f.lower():
                matches.append(f"File match: {rel_path}")
                continue
                
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read().lower()
                    if query in content:
                        count = content.count(query)
                        matches.append(f"Content match: {rel_path} ({count} occurrences)")
            except:
                pass
                
    return "\n".join(matches[:25]) if matches else "No matches found."
