import asyncio
import uuid
from typing import List, Dict, Any, Optional
from enum import Enum
from app.models.schemas import TaskStatus, TaskResponse
from app.utils.logger import logger

class Priority(int, Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

class Task:
    def __init__(self, task_id: str, goal: str, user_id: str, priority: Priority = Priority.MEDIUM):
        self.task_id = task_id
        self.goal = goal
        self.user_id = user_id
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.created_at = asyncio.get_event_loop().time()

class TaskManager:
    def __init__(self):
        self.queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.active_tasks: Dict[str, Task] = {}
        self.results: Dict[str, TaskResponse] = {}
        self.running = False

    async def add_task(self, goal: str, user_id: str, priority: Priority = Priority.MEDIUM) -> str:
        task_id = str(uuid.uuid4())
        task = Task(task_id, goal, user_id, priority)
        self.active_tasks[task_id] = task
        # PriorityQueue is min-heap, so we use negative priority for max-heap behavior
        await self.queue.put((-priority.value, task.created_at, task))
        logger.info(f"Task {task_id} added to queue with priority {priority.name}")
        return task_id

    async def start(self, agent_loop_func):
        """
        Start the task manager loop to process tasks from the queue.
        """
        self.running = True
        logger.info("Task manager started.")
        while self.running:
            try:
                # Get the next task from the queue
                priority_val, created_at, task = await self.queue.get()
                logger.info(f"Processing task {task.task_id} from queue.")
                
                task.status = TaskStatus.RUNNING
                # Execute the agent loop for this task
                await agent_loop_func(task.task_id, task.goal, task.user_id)
                
                task.status = TaskStatus.COMPLETED
                self.queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in task manager loop: {e}")
                await asyncio.sleep(1)

    def stop(self):
        self.running = False
        logger.info("Task manager stopped.")

    def get_task_status(self, task_id: str) -> Optional[Task]:
        return self.active_tasks.get(task_id)

task_manager = TaskManager()
