from typing import Dict, Any, List
from app.utils.logger import logger

class SafetyLayer:
    def __init__(self):
        # List of dangerous shell commands to block
        self.dangerous_commands = [
            "rm -rf", "sudo", "format", "mkfs", "dd", ":(){ :|:& };:", 
            "mv /", "chmod 777", "chown", "shutdown", "reboot"
        ]
        # Allowed tools for specific users (simplified)
        self.user_permissions = {
            "default_user": ["chat", "action", "task", "android.*", "web.*", "file.*", "shell.*", "http.*", "memory.*"]
        }
        self.killed_tasks: Dict[str, bool] = {}

    def is_safe_to_execute(self, tool: str, args: Dict[str, Any]) -> bool:
        """
        Validates if a tool and its arguments are safe to execute.
        """
        # 1. Check for dangerous shell commands
        if tool == "shell.execute":
            command = args.get("command", "").lower()
            for dangerous in self.dangerous_commands:
                if dangerous in command:
                    logger.warning(f"Safety Violation: Dangerous shell command detected: {command}")
                    return False
        
        # 2. Action validation (e.g., preventing file access outside sandbox)
        if tool.startswith("file."):
            filename = args.get("filename", "")
            if ".." in filename or filename.startswith("/"):
                logger.warning(f"Safety Violation: Unauthorized file path access: {filename}")
                return False

        return True

    def check_permission(self, user_id: str, tool: str) -> bool:
        """
        Checks if a user has permission to use a specific tool.
        """
        allowed_tools = self.user_permissions.get(user_id, [])
        for pattern in allowed_tools:
            if pattern.endswith(".*"):
                if tool.startswith(pattern[:-2]):
                    return True
            elif tool == pattern:
                return True
        
        logger.warning(f"Permission Denied: User {user_id} attempted to use tool {tool}")
        return False

    def kill_task(self, task_id: str):
        self.killed_tasks[task_id] = True
        logger.info(f"Task {task_id} added to kill list.")

    def is_killed(self, task_id: str) -> bool:
        return self.killed_tasks.get(task_id, False)

safety_layer = SafetyLayer()
