"""
test_agent.py — Scratch script to manually test and verify the agent loop.
"""

import asyncio
import os
import sys

# Load .env variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# Ensure apps/worker/ is in the import path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_loop import run_agent_loop


async def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    print("=== Telecode v2.0 Autonomous Agent Engine Test ===")
    
    # We will test using a public repo (dhruv-dk17/telecode or similar) in local fallback mode
    repo = "dhruv-dk17/telecode"
    token = os.environ.get("GITHUB_TOKEN", "mock-token-not-needed-for-public-clone")
    goal = "Find the entry point of the python worker and explain how it starts up."
    
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is not set. Please set it to test the agent loop.")
        return
        
    print(f"Goal: {goal}")
    print("Starting agent loop (Local Fallback Sandboxing)...")
    
    # Let's run it with max 4 steps to keep the test rapid and verify search + explanation capabilities.
    result = await run_agent_loop(
        goal=goal,
        repo_full_name=repo,
        github_token=token,
        base_branch="master",
        max_steps=4
    )
    
    print("\n=== Agent Result ===")
    print(f"Status: {result.get('status')}")
    print(f"PR URL: {result.get('pr_url')}")
    print(f"Branch: {result.get('branch_name')}")
    print(f"Modified Files: {result.get('modified_files')}")
    print(f"Output Description:\n{result.get('result')}")


if __name__ == "__main__":
    asyncio.run(main())
