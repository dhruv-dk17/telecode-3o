"""
code_tools.py — Tools for workspace filesystem and terminal execution.
"""

from sandbox_client import SandboxClient
from ai_engine import _is_sensitive


def get_code_tools(sandbox: SandboxClient):
    """Returns filesystem and execution tools bound to the given sandbox."""

    async def read_file(path: str) -> str:
        """
        Read the complete content of a file at the specified path inside the workspace.

        Args:
            path: The relative path to the file (e.g. "src/index.ts").

        Returns:
            The content of the file or an error message.
        """
        if _is_sensitive(path):
            return f"Error: Access to sensitive file '{path}' is blocked for security reasons."

        try:
            return await sandbox.read_file(path)
        except Exception as e:
            return f"Error reading file: {str(e)}"

    async def write_file(path: str, content: str) -> str:
        """
        Write or overwrite the complete content of a file at the specified path inside the workspace.
        This will create any necessary parent folders automatically.

        Args:
            path: The relative path of the file to write.
            content: The full content to write to the file.

        Returns:
            A success message or an error message.
        """
        if _is_sensitive(path):
            return f"Error: Writing to sensitive path '{path}' is blocked for security reasons."

        try:
            await sandbox.write_file(path, content)
            return f"Successfully wrote to '{path}'."
        except Exception as e:
            return f"Error writing file: {str(e)}"

    async def run_command(command: str) -> str:
        """
        Execute a shell command inside the workspace container and return stdout, stderr, and exit code.
        Use this to run compilation checks (e.g., 'npm run build'), run unit tests (e.g., 'npm test'),
        or execute shell tasks.

        Args:
            command: The command line string to run.

        Returns:
            The standard output, standard error, and exit status code formatted as a string.
        """
        try:
            stdout, stderr, exit_code = await sandbox.run_command(command)
            output = f"Command: {command}\nExit Code: {exit_code}\n"
            if stdout:
                output += f"--- stdout ---\n{stdout}\n"
            if stderr:
                output += f"--- stderr ---\n{stderr}\n"
            return output
        except Exception as e:
            return f"Error running command: {str(e)}"

    return [read_file, write_file, run_command]
