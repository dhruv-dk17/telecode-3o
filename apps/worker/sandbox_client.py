"""
sandbox_client.py — Sandbox client for executing user code.
Supports containerized cloud sandbox (E2B) and fallback local execution.
"""

import os
import shutil
import tempfile
import asyncio
from typing import Tuple, Optional


class SandboxClient:
    def __init__(self, repo_full_name: str, github_token: str, base_branch: str = "main"):
        self.repo_full_name = repo_full_name
        self.github_token = github_token
        self.base_branch = base_branch
        self.e2b_api_key = os.environ.get("E2B_API_KEY")
        self.is_e2b = bool(self.e2b_api_key)
        self.sandbox = None
        self.local_dir = None
        self.workspace_dir = None
        self.modified_files = set()  # Tracks files modified during this session

    async def initialize(self) -> None:
        """Sets up the sandbox and clones the repository."""
        if self.is_e2b:
            print("[Sandbox] Initializing E2B cloud sandbox...")
            try:
                from e2b import AsyncSandbox
                self.sandbox = await AsyncSandbox.create(template="base")
                
                # Clone repo
                repo_url = f"https://x-access-token:{self.github_token}@github.com/{self.repo_full_name}.git"
                print(f"[Sandbox] Cloning {self.repo_full_name} into E2B...")
                
                clone_res = await self.sandbox.commands.run(f"git clone {repo_url} /workspace")
                if clone_res.exit_code != 0:
                    raise Exception(f"E2B clone failed: {clone_res.stderr}")
                
                # Checkout branch
                await self.sandbox.commands.run(f"git checkout {self.base_branch}", cwd="/workspace")
                print("[Sandbox] E2B sandbox initialized successfully.")
                return
            except Exception as e:
                print(f"[Sandbox] E2B initialization failed: {e}. Falling back to local workspace.")
                self.is_e2b = False

        # Fallback Local Sandbox
        print("[Sandbox] Initializing local sandbox...")
        scratch_dir = os.path.join(os.path.dirname(__file__), "scratch", "sandbox")
        os.makedirs(scratch_dir, exist_ok=True)
        
        # Create unique directory inside scratch sandbox
        self.local_dir = tempfile.mkdtemp(dir=scratch_dir)
        repo_name = self.repo_full_name.split("/")[-1]
        self.workspace_dir = os.path.join(self.local_dir, repo_name)
        
        repo_url = f"https://x-access-token:{self.github_token}@github.com/{self.repo_full_name}.git"
        print(f"[Sandbox] Cloning {self.repo_full_name} locally...")
        
        # Run clone command securely
        cmd = f"git clone -b {self.base_branch} {repo_url} \"{self.workspace_dir}\""
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            err_str = stderr.decode(errors="replace")
            print(f"[Sandbox] Local clone failed: {err_str}")
            # Try to clone without token (public repo fallback or clean debug)
            public_url = f"https://github.com/{self.repo_full_name}.git"
            print(f"[Sandbox] Retrying public URL clone: {public_url}...")
            retry_cmd = f"git clone -b {self.base_branch} {public_url} \"{self.workspace_dir}\""
            retry_proc = await asyncio.create_subprocess_shell(
                retry_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await retry_proc.communicate()
            if retry_proc.returncode != 0:
                raise Exception(f"Failed to clone repository: {stderr.decode(errors='replace')}")
                
        print(f"[Sandbox] Local workspace ready at: {self.workspace_dir}")

    async def run_command(self, command: str) -> Tuple[str, str, int]:
        """Runs a command inside the workspace."""
        if self.is_e2b:
            res = await self.sandbox.commands.run(command, cwd="/workspace")
            return res.stdout, res.stderr, res.exit_code
        else:
            print(f"[Sandbox] Local execution: {command}")
            # Limit command injection risk, though we trust our AI model.
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.workspace_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return (
                stdout.decode(errors="replace"),
                stderr.decode(errors="replace"),
                proc.returncode
            )

    async def read_file(self, path: str) -> str:
        """Reads a file from the workspace."""
        if self.is_e2b:
            return await self.sandbox.files.read(f"/workspace/{path}")
        else:
            full_path = os.path.join(self.workspace_dir, path)
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"File not found: {path}")
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()

    async def write_file(self, path: str, content: str) -> None:
        """Writes content to a file in the workspace."""
        self.modified_files.add(path)
        if self.is_e2b:
            await self.sandbox.files.write(f"/workspace/{path}", content)
        else:
            full_path = os.path.join(self.workspace_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

    async def cleanup(self) -> None:
        """Cleans up the sandbox environment."""
        if self.is_e2b and self.sandbox:
            print("[Sandbox] Closing E2B sandbox session...")
            try:
                await self.sandbox.close()
            except Exception as e:
                print(f"[Sandbox] E2B close error: {e}")
        elif self.local_dir and os.path.exists(self.local_dir):
            print(f"[Sandbox] Removing local workspace {self.local_dir}...")
            
            # Windows permission correction loop to cleanly delete .git directories
            def _remove_readonly(func, path, excinfo):
                os.chmod(path, 0o777)
                func(path)

            try:
                shutil.rmtree(self.local_dir, onerror=_remove_readonly)
            except Exception as e:
                print(f"[Sandbox] Error cleaning up local directory: {e}")
