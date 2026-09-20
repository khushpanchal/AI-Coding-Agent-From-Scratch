"""Bash tool — execute shell commands with safety guards."""

import subprocess

from agent.tools.safety import is_dangerous_command, truncate_output

BASH_TIMEOUT = 60  # seconds

BASH_SCHEMA = {
    "name": "bash",
    "description": (
        "Execute a bash command and return its output. "
        "Use this for running shell commands, installing packages, "
        "checking system state, running scripts, etc. "
        "Commands have a 60-second timeout."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute.",
            }
        },
        "required": ["command"],
    },
}


def handle_bash(command: str) -> str:
    """Execute a bash command and return stdout + stderr."""
    if is_dangerous_command(command):
        return f"Error: Command blocked for safety — '{command}' matches a dangerous pattern."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=BASH_TIMEOUT,
            cwd=None,  # Uses current working directory
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate_output(output) if output else "(no output)"

    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {BASH_TIMEOUT} seconds."
    except Exception as e:
        return f"Error: {e}"
