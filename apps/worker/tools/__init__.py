"""
__init__.py — Tools package initializer.
Aggregates all available agent tools.
"""

from tools.code_tools import get_code_tools
from tools.github_tools import get_github_tools
from tools.search_tools import get_search_tools


def get_all_tools(
    sandbox,
    repo_full_name: str,
    github_token: str,
    base_branch: str = "main"
):
    """
    Returns a unified list of callable functions for the Gemini API.
    Also returns a mapping of tool names to functions for local execution dispatch.
    """
    tools_list = []
    
    # 1. Code / filesystem / command tools
    tools_list.extend(get_code_tools(sandbox))
    
    # 2. GitHub branch / PR tools
    if repo_full_name and github_token:
        tools_list.extend(get_github_tools(sandbox, repo_full_name, github_token, base_branch))
        
    # 3. Search codebase and Tavily web tools
    tools_list.extend(get_search_tools(sandbox, repo_full_name))

    # Build a lookup dictionary of { name: function }
    tools_map = {func.__name__: func for func in tools_list}
    
    return tools_list, tools_map
