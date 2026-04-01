import asyncio
import os
import shlex
from app.tools.registry import tool_registry
from app.utils.logger import logger

# Sandboxed shell execution with limited permissions
SANDBOX_DIR = os.path.join(os.getcwd(), "sandbox")
if not os.path.exists(SANDBOX_DIR):
    os.makedirs(SANDBOX_DIR)

@tool_registry.register(
    name="shell_execute",
    description="Execute a shell command in a sandboxed environment."
)
async def shell_execute(command: str) -> str:
    """
    Execute a shell command in a sandboxed environment.
    """
    logger.info(f"Executing shell command: {command}")
    
    # Simple command filtering for safety
    forbidden_commands = ["rm -rf /", "sudo", "chmod", "chown", "kill", "shutdown", "reboot"]
    for forbidden in forbidden_commands:
        if forbidden in command:
            return f"Error: Command '{command}' is not allowed for security reasons."

    try:
        # Use shlex to safely split the command if not using shell=True
        # For complex commands, shell=True is often needed, but we'll use create_subprocess_shell
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=SANDBOX_DIR
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            
            if process.returncode == 0:
                return stdout.decode().strip() if stdout else "Command executed successfully with no output."
            else:
                return f"Error executing command: {stderr.decode().strip()}"
        except asyncio.TimeoutError:
            process.kill()
            return "Error: Command execution timed out."
            
    except Exception as e:
        logger.error(f"Error executing shell command: {e}")
        return f"Error executing shell command: {str(e)}"
