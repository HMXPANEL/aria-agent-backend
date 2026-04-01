"""
tasks/queue.py - Multi-task queue system.

Supports:
  - Multiple sequential tasks per session
  - Splitting compound inputs ("open youtube and send hi to aman")
  - Task status tracking (pending, running, complete, failed)
  - Getting current active task
"""
import asyncio
import logging
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tasks.queue")

_QUEUES: Dict[str, "TaskQueue"] = {}


class Task:
    """Single task unit with goal, status, and result."""

    def __init__(self, goal: str, task_id: str):
        self.goal      = goal
        self.task_id   = task_id
        self.status    = "pending"   # pending | running | complete | failed
        self.result: Optional[Dict[str, Any]] = None
        self.retries   = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id":  self.task_id,
            "goal":     self.goal,
            "status":   self.status,
            "result":   self.result,
            "retries":  self.retries,
        }


class TaskQueue:
    """
    Per-session task queue. Tasks execute sequentially.
    Supports adding multiple tasks and tracking their progress.
    """

    def __init__(self, session_id: str):
        self.session_id  = session_id
        self._queue: deque = deque()
        self._current: Optional[Task] = None
        self._completed: List[Task]   = []
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        return f"{self.session_id}_task_{self._counter}"

    def add(self, goal: str) -> Task:
        task = Task(goal, self._new_id())
        self._queue.append(task)
        logger.info(f"[QUEUE] Added: {goal!r} | queue size={len(self._queue)}")
        return task

    def add_many(self, goals: List[str]) -> List[Task]:
        return [self.add(g) for g in goals]

    def next(self) -> Optional[Task]:
        """
        Gets the next pending task. Marks it as running.
        Returns None if no tasks pending.
        """
        if self._current and self._current.status == "running":
            return self._current
        if self._queue:
            task = self._queue.popleft()
            task.status    = "running"
            self._current  = task
            logger.info(f"[QUEUE] Starting: {task.goal!r}")
            return task
        return None

    def complete_current(self, result: Dict[str, Any]) -> None:
        if self._current:
            self._current.status = "complete"
            self._current.result = result
            self._completed.append(self._current)
            logger.info(f"[QUEUE] Completed: {self._current.goal!r}")
            self._current = None

    def fail_current(self, reason: str = "") -> None:
        if self._current:
            self._current.status = "failed"
            self._current.result = {
                "action": "REPLY",
                "params": {"text": f"Task failed: {reason or 'Unknown error'}"},
            }
            self._completed.append(self._current)
            logger.warning(f"[QUEUE] Failed: {self._current.goal!r} | {reason}")
            self._current = None

    def has_more(self) -> bool:
        return bool(self._queue) or (
            self._current is not None and self._current.status == "running"
        )

    def is_empty(self) -> bool:
        return not self._queue and self._current is None

    def current_goal(self) -> Optional[str]:
        if self._current:
            return self._current.goal
        return None

    def all_tasks(self) -> List[Dict[str, Any]]:
        result = []
        if self._current:
            result.append(self._current.to_dict())
        for t in self._queue:
            result.append(t.to_dict())
        for t in self._completed[-5:]:   # last 5 completed
            result.append(t.to_dict())
        return result

    def clear(self) -> None:
        self._queue.clear()
        self._current = None
        logger.info(f"[QUEUE] Cleared session={self.session_id!r}")


def get_queue(session_id: str) -> TaskQueue:
    if session_id not in _QUEUES:
        _QUEUES[session_id] = TaskQueue(session_id)
    return _QUEUES[session_id]


def enqueue_tasks(session_id: str, goals: List[str]) -> List[Task]:
    """Add multiple task goals to a session's queue."""
    q = get_queue(session_id)
    return q.add_many(goals)


def get_next_task(session_id: str) -> Optional[Task]:
    """Get the next task to execute for a session."""
    return get_queue(session_id).next()


def complete_task(session_id: str, result: Dict[str, Any]) -> None:
    get_queue(session_id).complete_current(result)


def fail_task(session_id: str, reason: str = "") -> None:
    get_queue(session_id).fail_current(reason)


def queue_status(session_id: str) -> Dict[str, Any]:
    q = get_queue(session_id)
    return {
        "session_id":  session_id,
        "has_more":    q.has_more(),
        "current":     q.current_goal(),
        "all_tasks":   q.all_tasks(),
    }
