import os
import aiofiles
from app.tools.registry import tool_registry
from app.utils.logger import logger

# Limited permission directory for file operations
SANDBOX_DIR = os.path.join(os.getcwd(), "sandbox")
if not os.path.exists(SANDBOX_DIR):
    os.makedirs(SANDBOX_DIR)

def _get_safe_path(filename: str) -> str:
    """
    Ensure the file path is within the sandbox directory.
    """
    safe_path = os.path.abspath(os.path.join(SANDBOX_DIR, filename))
    if not safe_path.startswith(os.path.abspath(SANDBOX_DIR)):
        raise PermissionError(f"Access to {filename} is not allowed.")
    return safe_path

@tool_registry.register(
    name="file_write",
    description="Write content to a file in the sandbox."
)
async def file_write(filename: str, content: str) -> str:
    """
    Write content to a file in the sandbox.
    """
    try:
        safe_path = _get_safe_path(filename)
        async with aiofiles.open(safe_path, mode='w') as f:
            await f.write(content)
        logger.info(f"File written: {filename}")
        return f"Successfully wrote to {filename}"
    except Exception as e:
        logger.error(f"Error writing to {filename}: {e}")
        return f"Error writing to {filename}: {str(e)}"

@tool_registry.register(
    name="file_read",
    description="Read content from a file in the sandbox."
)
async def file_read(filename: str) -> str:
    """
    Read content from a file in the sandbox.
    """
    try:
        safe_path = _get_safe_path(filename)
        if not os.path.exists(safe_path):
            return f"File {filename} not found."
        async with aiofiles.open(safe_path, mode='r') as f:
            content = await f.read()
        logger.info(f"File read: {filename}")
        return content
    except Exception as e:
        logger.error(f"Error reading from {filename}: {e}")
        return f"Error reading from {filename}: {str(e)}"

@tool_registry.register(
    name="file_list",
    description="List files in the sandbox."
)
async def file_list() -> str:
    """
    List files in the sandbox.
    """
    try:
        files = os.listdir(SANDBOX_DIR)
        return f"Files in sandbox: {', '.join(files)}"
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return f"Error listing files: {str(e)}"
