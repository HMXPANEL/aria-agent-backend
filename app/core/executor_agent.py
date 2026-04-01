import asyncio
import json
from typing import Dict, Any, Optional
from app.models.schemas import TaskStep, TaskStatus
from app.models.agent_state import AgentState
from app.tools.registry import tool_registry
from app.utils.logger import logger
from app.core.safety import safety_layer
from app.api.websocket import websocket_manager # Import websocket_manager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class ExecutorAgent:
    def __init__(self):
        self.tool_registry = tool_registry
        self.safety = safety_layer

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda retry_state: logger.warning(f"Retrying tool execution... Attempt {retry_state.attempt_number}")
    )
    async def execute_step(self, step: TaskStep, user_id: str, task_id: str) -> Dict[str, Any]:
        """
        Execute a single task step asynchronously.
        """
        logger.info(f"Executing step {step.id}: {step.description} using tool {step.tool}")
        
        # Safety check before execution
        if not self.safety.is_safe_to_execute(step.tool, step.args):
            logger.error(f"Safety check failed for tool {step.tool} with args {step.args}")
            return {"status": "failed", "result": "Safety check failed", "tool": step.tool, "args": step.args}

        try:
            tool_func = self.tool_registry.get_tool(step.tool)
            if not tool_func:
                raise ValueError(f"Tool {step.tool} not found in registry.")

            # Handle Android tools specifically via WebSocket
            if step.tool.startswith("android."):
                command_payload = {
                    "type": "android_command",
                    "command": step.tool.split(".")[1], # e.g., 'tap', 'swipe'
                    "args": step.args
                }
                # Send command to Android device via WebSocket
                response = await websocket_manager.send_command_to_device(user_id, command_payload)
                result = {"status": "executed", "result": response, "tool": step.tool, "args": step.args}
            else:
                # Execute other tools directly
                result = await tool_func(**step.args)
                result = {"status": "executed", "result": result, "tool": step.tool, "args": step.args}
            
            step.status = TaskStatus.COMPLETED
            return result
        except Exception as e:
            logger.error(f"Error executing step {step.id} with tool {step.tool}: {e}")
            step.status = TaskStatus.FAILED
            raise e # Re-raise for retry mechanism

executor_agent = ExecutorAgent()
