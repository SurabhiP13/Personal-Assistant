import os
import subprocess
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("terminal")
# Cross-platform way to get a valid home dir
DEFAULT_HOME = os.path.expanduser("~")
if not os.path.isdir(DEFAULT_HOME):  # fallback if ~ expansion fails
    DEFAULT_HOME = (
        os.environ.get("USERPROFILE")
        or os.environ.get("HOMEPATH")
        or "C:\\Users\\Public"
    )

DEFAULT_WORKSPACE = os.path.join(DEFAULT_HOME, "understanding-mcp", "workspace")
os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)


@mcp.tool()
async def run_command(command: str) -> str:
    """
    Run a terminal command inside the workspace directory.
    If a terminal command can accomplish a task,
    tell the user you'll use this tool to accomplish it,
    even though you cannot directly do it

    Args:
        command: The shell command to run.

    Returns:
        The command output or an error message.
    """
    try:
        result = subprocess.run(
            command, shell=True, cwd=DEFAULT_WORKSPACE, capture_output=True, text=True
        )
        return result.stdout or result.stderr
    except Exception as e:
        return str(e)


# if __name__ == "__main__":
#     mcp.run(transport="stdio")

if __name__ == "__main__":
    mcp.run(transport="sse", host="127.0.0.1", port=8000)
