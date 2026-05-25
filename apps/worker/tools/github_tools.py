"""
github_tools.py — GitHub integration tools for pushing changes and opening PRs.
"""

from github_client import GitHubClient
from sandbox_client import SandboxClient


def get_github_tools(
    sandbox: SandboxClient,
    repo_full_name: str,
    github_token: str,
    base_branch: str = "main"
):
    """Returns GitHub tools bound to the sandbox and connection parameters."""

    async def create_pull_request(title: str, body: str, branch_name: str | None = None) -> str:
        """
        Create a new branch, commit all files modified during this session, and open a Pull Request on GitHub.
        Only call this tool when all changes are fully complete, compiled, and verified.

        Args:
            title: The title of the pull request and commit message (e.g. "feat: add user auth").
            body: A brief description of what was changed and why.
            branch_name: Optional custom branch name (e.g. "telecode/add-auth"). If not provided, a unique one is auto-generated.

        Returns:
            The URL of the created Pull Request or an error message.
        """
        if not sandbox.modified_files:
            return "Error: No files have been modified in this session. Write some files first before creating a PR."

        try:
            # 1. Fetch contents of all modified files from sandbox
            files_payload = []
            for path in sandbox.modified_files:
                content = await sandbox.read_file(path)
                files_payload.append({
                    "path": path,
                    "content": content
                })

            # 2. Determine branch name
            if not branch_name:
                import uuid
                branch_name = f"telecode/task-{str(uuid.uuid4())[:8]}"

            # 3. Connect to GitHub
            gh = GitHubClient(token=github_token)

            # Create branch
            print(f"[GitHub Tool] Creating branch {branch_name} on {repo_full_name}...")
            await gh.create_branch(
                repo_full_name=repo_full_name,
                base_branch=base_branch,
                new_branch=branch_name
            )

            # Commit files
            print(f"[GitHub Tool] Committing {len(files_payload)} file(s) to branch {branch_name}...")
            await gh.commit_files(
                repo_full_name=repo_full_name,
                branch=branch_name,
                files=files_payload,
                commit_message=title
            )

            # Create PR
            print(f"[GitHub Tool] Opening Pull Request...")
            pr_url = await gh.create_pull_request(
                repo_full_name=repo_full_name,
                title=title,
                body=f"{body}\n\n---\n*Created autonomously by Telecode v2.0.*",
                head=branch_name,
                base=base_branch
            )

            # Save PR info for main loop return values
            sandbox.pr_url = pr_url
            sandbox.branch_name = branch_name

            return f"Successfully created Pull Request: {pr_url}\nBranch: {branch_name}"

        except Exception as e:
            return f"Error creating Pull Request: {str(e)}"

    return [create_pull_request]
