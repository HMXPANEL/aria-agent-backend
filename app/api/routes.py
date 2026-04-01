from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from app.models.schemas import ChatRequest, ChatResponse, TaskRequest, TaskResponse, VoiceRequest, VoiceResponse, MemoryItem
from app.core.controller_agent import controller_agent
from app.core.memory_agent import memory_agent
from app.core.task_manager.task_manager import task_manager
from app.utils.logger import logger

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Handle natural language chat input.
    """
    try:
        return await controller_agent.handle_chat(request)
    except Exception as e:
        logger.error(f"Error in /chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/task", response_model=ChatResponse)
async def create_task(request: TaskRequest):
    """
    Create a new multi-agent autonomous task.
    """
    try:
        # Use task manager to queue the task
        task_id = await task_manager.add_task(request.description, request.user_id)
        return ChatResponse(response="Task queued for multi-agent execution.", intent="TASK", task_id=task_id)
    except Exception as e:
        logger.error(f"Error in /task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a specific task.
    """
    status = controller_agent.get_task_status(task_id)
    if not status:
        # Check task manager if not in controller's active states
        tm_task = task_manager.get_task_status(task_id)
        if tm_task:
            return TaskResponse(task_id=task_id, status=tm_task.status, steps=[])
        raise HTTPException(status_code=404, detail="Task not found")
    return status

@router.post("/task/{task_id}/stop")
async def stop_task(task_id: str):
    """
    Stop a running task.
    """
    controller_agent.stop_task(task_id)
    return {"message": f"Stop signal sent to task {task_id}"}

@router.get("/memory", response_model=List[MemoryItem])
async def get_memory(user_id: str = "default_user", query: Optional[str] = None):
    """
    Retrieve memory content for a user.
    """
    try:
        if query:
            results = await memory_agent.retrieve_context(user_id, query)
            # Map semantic results to MemoryItem schema
            return [MemoryItem(key="semantic_search", value=doc, timestamp=0) for doc in results.get("relevant_past_experiences", [])]
        else:
            # Return short-term memory as default
            st_memory = memory_agent.short_term_memory.get(user_id, [])
            return [MemoryItem(key="short_term", value=m, timestamp=m.get("timestamp", 0)) for m in st_memory]
    except Exception as e:
        logger.error(f"Error in /memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))
