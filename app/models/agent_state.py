from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.models.schemas import TaskStep, TaskStatus

class AgentState(BaseModel):
    task_id: str
    goal: str
    user_id: str
    current_status: TaskStatus = TaskStatus.PENDING
    current_steps: List[TaskStep] = []
    working_memory: Dict[str, Any] = {}
    last_observation: Optional[str] = None
    thoughts: Optional[str] = None
    reasoning: Optional[str] = None
    plan_graph: Optional[Dict[str, Any]] = None # For advanced planner
    critic_feedback: Optional[str] = None
    insights: Optional[str] = None
    error_message: Optional[str] = None
