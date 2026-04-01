from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from enum import Enum

class Intent(str, Enum):
    INFO = "info"
    TASK = "task"
    UNKNOWN = "unknown"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default_user"

class ChatResponse(BaseModel):
    response: str
    intent: Intent = Intent.UNKNOWN
    task_id: Optional[str] = None

class TaskRequest(BaseModel):
    description: str
    user_id: str = "default_user"

class TaskStep(BaseModel):
    id: str
    description: str
    tool: str
    args: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None

class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    steps: List[TaskStep]

class VoiceRequest(BaseModel):
    audio_data: str # Base64 encoded audio

class VoiceResponse(BaseModel):
    text: str

class MemoryItem(BaseModel):
    key: str
    value: Any
    timestamp: float

class AndroidCommand(BaseModel):
    action: str
    target: Optional[Dict[str, Any]] = None
    args: Optional[Dict[str, Any]] = None
