import asyncio
from typing import List, Dict, Any, Optional
from app.models.schemas import TaskStep, TaskStatus
from app.tools.registry import tool_registry
from app.core.safety import safety_layer
from app.utils.logger import logger

class Executor:
    def __init__(self):
        self.tool_registry = tool_registry
        self.safety = safety_layer

    async def execute_step(self, step: TaskStep, user_id: str = "default_user", task_id: Optional[str] = None) -> Any:
        """
        Execute a single task step using the tool registry with safety checks and retry logic.
        """
        # Check kill switch
        if task_id and self.safety.is_killed(task_id):
            step.status = TaskStatus.FAILED
            step.result = "Task terminated by kill switch."
            logger.warning(f"Execution blocked by kill switch for task {task_id}")
            return None

        # Safety checks: Permission and Action Validation
        if not self.safety.check_permission(user_id, step.tool):
            step.status = TaskStatus.FAILED
            step.result = f"Permission denied for tool: {step.tool}"
            return None
            
        if not self.safety.validate_action(step.tool, step.args):
            step.status = TaskStatus.FAILED
            step.result = f"Unsafe action blocked for tool: {step.tool}"
            return None

        step.status = TaskStatus.RUNNING
        logger.info(f"Executing step: {step.description} using tool: {step.tool}")
        
        try:
            # Execute the tool with retry logic
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    result = await self.tool_registry.execute(step.tool, **step.args)
                    step.result = result
                    step.status = TaskStatus.COMPLETED
                    logger.info(f"Step completed: {step.description}")
                    return result
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"Error executing step {step.description} (attempt {retry_count}/{max_retries}): {e}")
                    if retry_count >= max_retries:
                        raise e
                    await asyncio.sleep(1) # Wait before retry
        except Exception as e:
            step.status = TaskStatus.FAILED
            step.result = str(e)
            logger.error(f"Step failed: {step.description} - {e}")
            return None

    async def execute_plan(self, steps: List[TaskStep], user_id: str = "default_user", task_id: Optional[str] = None) -> List[TaskStep]:
        """
        Execute a series of task steps sequentially.
        """
        for step in steps:
            await self.execute_step(step, user_id, task_id)
            if step.status == TaskStatus.FAILED:
                logger.error(f"Stopping plan execution due to step failure: {step.description}")
                break
        return steps

executor = Executor()
