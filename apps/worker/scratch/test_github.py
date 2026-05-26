import asyncio
import os
import subprocess
from dotenv import load_dotenv
import httpx

load_dotenv(dotenv_path=".env")

async def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = "dhruv-dk17/calc"
    print(f"Token: {token[:10]}...")
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Telecode-App"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://api.github.com/repos/{repo}", headers=headers)
        print(f"Repository API response status: {resp.status_code}")
        if resp.status_code == 200:
            print("Successfully accessed repository via API.")
            data = resp.json()
            print(f"Private: {data.get('private')}")
            print(f"Default branch: {data.get('default_branch')}")
        else:
            print(f"Failed to access repository: {resp.text}")
            
    # Try local clone
    import tempfile
    import shutil
    temp_dir = tempfile.mkdtemp()
    repo_url = f"https://x-access-token:{token}@github.com/{repo}.git"
    print(f"Cloning to temp dir: {temp_dir}")
    try:
        proc = subprocess.run(
            ["git", "clone", "-b", "main", repo_url, temp_dir],
            capture_output=True,
            text=True
        )
        print(f"Clone exit code: {proc.returncode}")
        print(f"STDOUT: {proc.stdout}")
        print(f"STDERR: {proc.stderr}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

asyncio.run(main())
